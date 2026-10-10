/* SPDX-License-Identifier: Apache-2.0 */
package com.android.server.telecom;

import android.media.AudioManager;
import android.content.Context;
import android.os.IBinder;
import android.os.ServiceManager;
import android.os.SystemProperties;
import android.util.Log;
import android.telephony.SubscriptionInfo;
import android.telephony.SubscriptionManager;
import dalvik.system.PathClassLoader;
import java.io.File;
import java.lang.reflect.Array;
import java.lang.reflect.Method;
import java.util.List;

/** Stock-derived Telecom audio adapter; M11 single-SIM scope, independent of carrier. */
final class SamsungImsAudioHandover {
    private static final String TAG = "M11StockAudioPort";
    private final SamsungImsAudioTransition policy = new SamsungImsAudioTransition();
    private int lastCallState; // Only state actually written by this adapter, not another call's state.

    static boolean enabled() {
        return "m11q".equals(SystemProperties.get("ro.product.device"))
                && "legacy".equals(SystemProperties.get("ro.telephony.iwlan_operation_mode"))
                && SamsungImsAudioTransition.singleSimPhone(
                        SystemProperties.get("gsm.sim.operator.numeric")) >= 0;
    }

    static boolean singleSubscriptionMatches(Context context, int phoneId, int subId) {
        try {
            if (!SamsungImsAudioTransition.supportedPhone(phoneId)
                    || !SubscriptionManager.isValidSubscriptionId(subId)
                    || SamsungImsAudioTransition.singleSimPhone(
                            SystemProperties.get("gsm.sim.operator.numeric")) != phoneId) return false;
            SubscriptionManager manager = context.getSystemService(SubscriptionManager.class);
            List<SubscriptionInfo> active = manager == null ? null : manager.getActiveSubscriptionInfoList();
            return active != null && active.size() == 1
                    && active.get(0).getSubscriptionId() == subId
                    && active.get(0).getSimSlotIndex() == phoneId
                    && SubscriptionManager.getPhoneId(subId) == phoneId;
        } catch (RuntimeException e) { return false; }
    }

    void observe(Object call, boolean allowed, boolean wifi, int phoneId, int subId) {
        policy.observe(call, allowed && enabled(), wifi, phoneId, subId);
    }

    boolean isVoip(Object call) { return enabled() && policy.isVoip(call); }
    boolean owns(Object call, int phoneId, int subId) { return enabled() && policy.owns(call, phoneId, subId); }

    void finish(AudioManager audio) {
        // Stock enterUnfocusedState -> resetAudioMode -> setOffAudioParam.
        // Cleanup remains necessary even if applicability changes after our write.
        int off = lastCallState == 32 ? 16 : lastCallState == 2 ? 1 : 0;
        if (off != 0) {
            lastCallState = 0;
            try {
                audio.setParameters("g_call_state=" + off);
                Log.i(TAG, "SA2 unfocused g_call_state=" + off);
            } catch (RuntimeException e) {
                Log.e(TAG, "SA2 parameter cleanup failed; Telecom still resets its mode", e);
            }
        }
    }

    private static Object getter(Object value, String name) throws Exception {
        return value.getClass().getMethod(name).invoke(value);
    }

    boolean setMode(AudioManager audio, int mode, Context context) {
        if (!enabled()) return false;
        boolean[] modeWritten = {false};
        String[] stage = {"preflight"};
        try {
            SamsungImsAudioTransition.Plan plan = policy.take(mode, audio.getMode());
            if (plan == null) return false;
            if (!singleSubscriptionMatches(context, plan.phoneId, plan.subscriptionId))
                throw new IllegalStateException("Subscription changed before audio transition");
            Log.i(TAG, "SA2 integrated stock audio");
            Log.i(TAG, "SA2 single-SIM either-slot scope phone=" + plan.phoneId);
            // Use the phone's typed client, as in the successful one-shot test.
            IBinder binder = ServiceManager.checkService("secims");
            if (binder == null || !"com.sec.ims.IImsService".equals(binder.getInterfaceDescriptor()))
                throw new IllegalStateException("Unexpected secims descriptor");
            String jar = null;
            for (String path : new String[] {"/system_ext/framework/imsmanager.jar",
                    "/system/system_ext/framework/imsmanager.jar", "/system/framework/imsmanager.jar"})
                if (new File(path).isFile()) { jar = path; break; }
            if (jar == null) throw new IllegalStateException("No installed imsmanager client");
            ClassLoader loader = new PathClassLoader(jar, getClass().getClassLoader());
            Class<?> api = loader.loadClass("com.sec.ims.IImsService");
            Object service = loader.loadClass("com.sec.ims.IImsService$Stub")
                    .getMethod("asInterface", IBinder.class).invoke(null, binder);
            Method counts = api.getMethod("getCallCount", int.class);
            Method audioPath = api.getMethod("changeAudioPathForSlot", int.class, int.class);
            requireCounts(service, counts, plan.phoneId);
            Object regs = api.getMethod("getRegistrationInfoByPhoneId", int.class)
                    .invoke(service, plan.phoneId);
            boolean matched = false;
            if (regs != null) for (int i = 0; i < Array.getLength(regs); i++) {
                Object reg = Array.get(regs, i);
                if (reg == null) continue;
                Object profile = getter(reg, "getImsProfile");
                if (profile == null) continue;
                int rat = (Integer) getter(reg, "getCurrentRat");
                boolean epdg = (Boolean) getter(reg, "getEpdgStatus");
                boolean mmtel = (Boolean) reg.getClass().getMethod("hasService", String.class)
                        .invoke(reg, "mmtel");
                boolean normal = SamsungImsAudioTransition.normalRegistration(
                        plan.phoneId,
                        (Integer) getter(reg, "getPhoneId"), rat, mmtel,
                        (Boolean) getter(profile, "hasEmergencySupport"),
                        (Integer) getter(profile, "getCmcType"));
                matched |= normal;
                if (normal) Log.i(TAG, "SA2 normal registration rat=" + rat + " epdg=" + epdg
                        + " (call transport drives selection)");
            }
            if (!matched) throw new IllegalStateException("No normal LTE/IWLAN IMS registration");
            requireCounts(service, counts, plan.phoneId);
            SamsungImsAudioTransition.run(plan.toWifi, new SamsungImsAudioTransition.Operations() {
                private void check(String next) {
                    stage[0] = next;
                    if (!enabled() || !policy.current(plan)
                            || !singleSubscriptionMatches(context, plan.phoneId, plan.subscriptionId))
                        throw new IllegalStateException("Call/transport changed; no further audio writes");
                }
                public void audioPath(int direction) throws Exception {
                    check("audioPath=" + direction);
                    requireCounts(service, counts, plan.phoneId);
                    audioPath.invoke(service, plan.phoneId, direction);
                    Log.i(TAG, "SA2 audioPath=" + direction + " phone=" + plan.phoneId + " generation=" + plan.generation);
                }
                public void simSlot() {
                    check("simSlot=" + plan.phoneId);
                    String parameter = SamsungImsAudioTransition.simSlotParameter(plan.phoneId);
                    audio.setParameters(parameter);
                    Log.i(TAG, "SA2 " + parameter);
                }
                public void parameter(int value) {
                    check("g_call_state=" + value);
                    audio.setParameters("g_call_state=" + value);
                    lastCallState = value == 32 || value == 2 ? value : 0;
                    Log.i(TAG, "SA2 g_call_state=" + value);
                }
                public void mode(int value) {
                    check("mode=" + value);
                    audio.setMode(value);
                    modeWritten[0] = true;
                    Log.i(TAG, "SA2 mode=" + value);
                }
            });
            policy.complete(plan);
            Log.i(TAG, "SA2 sequence returned " + (plan.toWifi ? "L2W" : "W2L")
                    + " (not proof of audible continuity)");
            return true;
        } catch (Exception | LinkageError e) {
            Log.e(TAG, "SA2 aborted at " + stage[0] + "; no automatic retry", e);
            // If a partial stock reset wrote NORMAL, let Telecom finish its requested mode.
            // No invented audio-engine rollback or retry is issued.
            try { return modeWritten[0] && audio.getMode() == mode; }
            catch (RuntimeException ignored) { return false; }
        }
    }

    private static void requireCounts(Object service, Method method, int phoneId) throws Exception {
        if (!SamsungImsAudioTransition.ordinaryCounts(phoneId,
                (int[]) method.invoke(service, phoneId), (int[]) method.invoke(service, 1 - phoneId)))
            throw new IllegalStateException("Outside single ordinary selected-slot voice scope");
    }
}
