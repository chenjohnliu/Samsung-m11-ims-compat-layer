package com.sec.internal.google;

import android.os.RemoteException;
import android.telephony.ims.ImsCallProfile;
import android.telephony.ims.feature.CapabilityChangeRequest;
import android.telephony.ims.feature.MmTelFeature;
import android.telephony.ims.stub.ImsSmsImplBase;
import com.android.ims.internal.IImsCallSession;

public final class GoogleModernMmTelFeature extends MmTelFeature {
    final ModernVoiceContext owner;
    final ModernSmsBridge sms;
    boolean listenerReady;
    GoogleModernMmTelFeature(ModernVoiceContext owner) {
        this.owner = owner;
        this.sms = new ModernSmsBridge(owner);
    }
    void publish(boolean ready, boolean voice) {
        setFeatureState(ready ? STATE_READY : STATE_UNAVAILABLE);
        MmTelCapabilities c = new MmTelCapabilities();
        if (voice) c.addCapabilities(MmTelCapabilities.CAPABILITY_TYPE_VOICE);
        if (sms.available()) c.addCapabilities(MmTelCapabilities.CAPABILITY_TYPE_SMS);
        notifyCapabilitiesStatusChanged(c);
    }
    @Override public void onFeatureReady() {
        synchronized (owner) { listenerReady = true; owner.ensureBackend(); }
    }
    @Override public void onFeatureRemoved() {
        sms.dispose();
        owner.removeFeature(this);
    }
    @Override public boolean queryCapabilityConfiguration(int capability, int tech) {
        synchronized (owner) {
            if (tech != 0) return false;
            if (capability == MmTelCapabilities.CAPABILITY_TYPE_VOICE) return owner.voiceEnabled;
            if (capability == MmTelCapabilities.CAPABILITY_TYPE_SMS) return owner.smsEnabled;
            return false;
        }
    }
    @Override public void changeEnabledCapabilities(CapabilityChangeRequest request,
            CapabilityCallbackProxy callback) {
        synchronized (owner) {
            for (CapabilityChangeRequest.CapabilityPair pair : request.getCapabilitiesToDisable()) {
                change(pair, false, callback);
            }
            for (CapabilityChangeRequest.CapabilityPair pair : request.getCapabilitiesToEnable()) {
                change(pair, true, callback);
            }
            owner.publish();
        }
    }
    private void change(CapabilityChangeRequest.CapabilityPair pair, boolean enabled,
            CapabilityCallbackProxy callback) {
        if (pair.getCapability() == MmTelCapabilities.CAPABILITY_TYPE_VOICE
                && pair.getRadioTech() == 0) owner.setVoiceEnabled(enabled);
        else if (pair.getCapability() == MmTelCapabilities.CAPABILITY_TYPE_SMS
                && pair.getRadioTech() == 0) owner.setSmsEnabled(enabled);
        else callback.onChangeCapabilityConfigurationError(pair.getCapability(), pair.getRadioTech(), -1);
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
