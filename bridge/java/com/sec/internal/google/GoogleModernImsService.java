package com.sec.internal.google;

import android.telephony.ims.ImsService;
import android.telephony.SubscriptionManager;
import android.telephony.ims.feature.MmTelFeature;
import android.telephony.ims.stub.ImsConfigImplBase;
import android.telephony.ims.stub.ImsRegistrationImplBase;
import android.telephony.ims.stub.ImsFeatureConfiguration;

/** SIM1 only. The Android subscription is never interpreted as the Samsung service ID. */
public final class GoogleModernImsService extends ImsService {
    private ModernVoiceContext context;
    private synchronized ModernVoiceContext context(int slot, int subscription) {
        if (slot != 0 || !SubscriptionManager.isUsableSubscriptionId(subscription)) return null;
        if (context == null || context.subscription != subscription) {
            if (context != null) context.dispose();
            context = new ModernVoiceContext(this, subscription);
        }
        return context;
    }
    @Override public ImsFeatureConfiguration querySupportedImsFeatures() {
        return new ImsFeatureConfiguration.Builder().addFeature(0, 1).build();
    }
    @Override public MmTelFeature createMmTelFeatureForSubscription(int slot, int sub) {
        ModernVoiceContext c = context(slot, sub);
        return c == null ? null : c.feature();
    }
    @Override public ImsRegistrationImplBase getRegistrationForSubscription(int slot, int sub) {
        ModernVoiceContext c = context(slot, sub);
        return c == null ? null : c.registration;
    }
    @Override public ImsConfigImplBase getConfigForSubscription(int slot, int sub) {
        ModernVoiceContext c = context(slot, sub);
        return c == null ? null : c.config;
    }
    // Unknown-subscription compatibility calls cannot inherit SIM1 state.
    @Override public MmTelFeature createMmTelFeature(int slot) { return null; }
    @Override public ImsRegistrationImplBase getRegistration(int slot) { return null; }
    @Override public ImsConfigImplBase getConfig(int slot) { return null; }
    @Override public synchronized void onDestroy() {
        if (context != null) context.dispose();
        context = null;
        super.onDestroy();
    }
}
