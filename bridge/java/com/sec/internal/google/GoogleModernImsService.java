package com.sec.internal.google;

import android.content.Context;
import android.telephony.ims.ImsService;
import android.telephony.SubscriptionInfo;
import android.telephony.SubscriptionManager;
import android.telephony.ims.feature.MmTelFeature;
import android.telephony.ims.stub.ImsConfigImplBase;
import android.telephony.ims.stub.ImsRegistrationImplBase;
import android.telephony.ims.stub.ImsFeatureConfiguration;

/** One active cellular subscription on either physical slot. */
public final class GoogleModernImsService extends ImsService {
    private ModernVoiceContext context;
    static boolean isSingleActivePair(Context app, int slot, int subscription) {
        if (app == null || (slot != 0 && slot != 1)
                || !SubscriptionManager.isUsableSubscriptionId(subscription)
                || SubscriptionManager.getPhoneId(subscription) != slot
                || SubscriptionManager.getSlotIndex(subscription) != slot) return false;
        try {
            SubscriptionManager subscriptions = app.getSystemService(SubscriptionManager.class);
            if (subscriptions == null
                    || subscriptions.getActiveSubscriptionInfoCount() != 1) return false;
            SubscriptionInfo active = subscriptions.getActiveSubscriptionInfo(subscription);
            return active != null && active.getSubscriptionId() == subscription
                    && active.getSimSlotIndex() == slot;
        } catch (RuntimeException unavailable) {
            return false;
        }
    }
    private synchronized ModernVoiceContext context(int slot, int subscription) {
        // Subscription changes can deliver an old-slot request before the new active
        // pair is requested. Do not leave the old Binder ready during that interval.
        if (context != null
                && !isSingleActivePair(this, context.phoneId, context.subscription)) {
            context.dispose();
            context = null;
        }
        // An absent-slot or stale request must not tear down the one valid context.
        if (!isSingleActivePair(this, slot, subscription)) return null;
        if (context == null || context.phoneId != slot || context.subscription != subscription) {
            if (context != null) context.dispose();
            context = new ModernVoiceContext(this, slot, subscription);
        }
        return context;
    }
    @Override public ImsFeatureConfiguration querySupportedImsFeatures() {
        return new ImsFeatureConfiguration.Builder()
                .addFeature(0, 1)
                .addFeature(1, 1)
                .build();
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
    // Unknown-subscription compatibility calls cannot inherit another SIM's state.
    @Override public MmTelFeature createMmTelFeature(int slot) { return null; }
    @Override public ImsRegistrationImplBase getRegistration(int slot) { return null; }
    @Override public ImsConfigImplBase getConfig(int slot) { return null; }
    @Override public synchronized void onDestroy() {
        if (context != null) context.dispose();
        context = null;
        super.onDestroy();
    }
}
