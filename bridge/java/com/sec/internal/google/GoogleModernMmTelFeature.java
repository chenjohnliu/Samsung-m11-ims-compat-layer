package com.sec.internal.google;

import android.os.RemoteException;
import android.telephony.ims.ImsCallProfile;
import android.telephony.ims.feature.CapabilityChangeRequest;
import android.telephony.ims.feature.MmTelFeature;
import android.telephony.ims.stub.ImsSmsImplBase;
import android.telephony.ims.stub.ImsRegistrationImplBase;
import com.android.ims.internal.IImsCallSession;
import java.util.ArrayList;
import java.util.List;

public final class GoogleModernMmTelFeature extends MmTelFeature {
    final ModernVoiceContext owner;
    final ModernSmsBridge sms;
    volatile boolean listenerReady;
    GoogleModernMmTelFeature(ModernVoiceContext owner) {
        this.owner = owner;
        this.sms = new ModernSmsBridge(owner);
    }
    void publish(boolean ready, boolean voice, boolean smsReady) {
        setFeatureState(ready ? STATE_READY : STATE_UNAVAILABLE);
        MmTelCapabilities c = new MmTelCapabilities();
        if (voice) c.addCapabilities(MmTelCapabilities.CAPABILITY_TYPE_VOICE);
        if (smsReady) c.addCapabilities(MmTelCapabilities.CAPABILITY_TYPE_SMS);
        notifyCapabilitiesStatusChanged(c);
    }
    @Override public void onFeatureReady() {
        owner.featureReady(this);
    }
    @Override public void onFeatureRemoved() {
        owner.featureRemoved(this);
    }
    @Override public boolean queryCapabilityConfiguration(int capability, int tech) {
        synchronized (owner) {
            if (capability == MmTelCapabilities.CAPABILITY_TYPE_VOICE)
                return owner.voiceEnabledForTech(tech);
            if (capability == MmTelCapabilities.CAPABILITY_TYPE_SMS
                    && tech == ImsRegistrationImplBase.REGISTRATION_TECH_LTE)
                return owner.smsEnabled;
            return false;
        }
    }
    @Override public void changeEnabledCapabilities(CapabilityChangeRequest request,
            CapabilityCallbackProxy callback) {
        List<CapabilityChangeRequest.CapabilityPair> unsupported = new ArrayList<>();
        synchronized (owner) {
            for (CapabilityChangeRequest.CapabilityPair pair : request.getCapabilitiesToDisable()) {
                if (!change(pair, false)) unsupported.add(pair);
            }
            for (CapabilityChangeRequest.CapabilityPair pair : request.getCapabilitiesToEnable()) {
                if (!change(pair, true)) unsupported.add(pair);
            }
            owner.publish();
        }
        for (CapabilityChangeRequest.CapabilityPair pair : unsupported) {
            callback.onChangeCapabilityConfigurationError(
                    pair.getCapability(), pair.getRadioTech(), -1);
        }
    }
    private boolean change(CapabilityChangeRequest.CapabilityPair pair, boolean enabled) {
        if (pair.getCapability() == MmTelCapabilities.CAPABILITY_TYPE_VOICE
                && (pair.getRadioTech() == ImsRegistrationImplBase.REGISTRATION_TECH_LTE
                || pair.getRadioTech() == ImsRegistrationImplBase.REGISTRATION_TECH_IWLAN)) {
            owner.setVoiceEnabled(pair.getRadioTech(), enabled);
            return true;
        }
        if (pair.getCapability() == MmTelCapabilities.CAPABILITY_TYPE_SMS
                && pair.getRadioTech() == ImsRegistrationImplBase.REGISTRATION_TECH_LTE) {
            owner.setSmsEnabled(enabled);
            return true;
        }
        return false;
    }
    @Override public ImsSmsImplBase getSmsImplementation() { return sms; }
    @Override public int shouldProcessCall(String[] numbers) {
        synchronized (owner) { return owner.voiceAvailable() ? PROCESS_CALL_IMS : PROCESS_CALL_CSFB; }
    }
    @Override public ImsCallProfile createCallProfile(int serviceType, int callType) {
        synchronized (owner) {
            if (serviceType != ImsCallProfile.SERVICE_TYPE_NORMAL || callType != ImsCallProfile.CALL_TYPE_VOICE)
                throw new IllegalArgumentException("BC2 supports normal voice only");
            owner.requireBackend();
            try { return owner.backend.createCallProfile(owner.serviceId, serviceType, callType); }
            catch (RemoteException e) { throw new IllegalStateException("Native profile creation failed", e); }
        }
    }
    @Override public IImsCallSession createCallSessionInterface(ImsCallProfile profile) throws RemoteException {
        return owner.outgoing(profile);
    }
}
