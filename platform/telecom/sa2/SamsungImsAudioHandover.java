/* SPDX-License-Identifier: Apache-2.0 */
package com.android.server.telecom;

import android.media.AudioManager;
import android.os.IBinder;
import android.os.ServiceManager;
import android.os.SystemProperties;
import android.util.Log;
import dalvik.system.PathClassLoader;
import java.io.File;
import java.lang.reflect.Array;
import java.lang.reflect.Method;
import java.util.Arrays;

/** Stock-derived Telecom audio adapter; M11 single-SIM scope, independent of carrier. */
final class SamsungImsAudioHandover {
    private static final String TAG = "M11StockAudioPort";
    private final SamsungImsAudioTransition policy = new SamsungImsAudioTransition();
    private int lastCallState; // Only state actually written by this adapter, not another call's state.

    static boolean enabled() {
        return "stock1".equals(SystemProperties.get("persist.sys.m11_ims_audio_port"))
                && "m11q".equals(SystemProperties.get("ro.product.device"))
                && "legacy".equals(SystemProperties.get("ro.telephony.iwlan_operation_mode"))
                && SamsungImsAudioTransition.singleSimOperator(
                        SystemProperties.get("gsm.sim.operator.numeric"));
    }

    void observe(Object call, boolean allowed, boolean wifi) {
        policy.observe(call, allowed && enabled(), wifi);
    }

    boolean isVoip(Object call) { return enabled() && policy.isVoip(call); }
    boolean owns(Object call) { return enabled() && policy.owns(call); }

    void finish(AudioManager audio) {
        // Stock enterUnfocusedState -> resetAudioMode -> setOffAudioParam.
        // Cleanup remains necessary even if the trial gate was disabled after our write.
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

    boolean setMode(AudioManager audio, int mode) {
        if (!enabled()) return false;
        boolean[] modeWritten = {false};
        String[] stage = {"preflight"};
        try {
            SamsungImsAudioTransition.Plan plan = policy.take(mode, audio.getMode());
            if (plan == null) return false;
            Log.i(TAG, "SA2 carrier-neutral slot0 scope");
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
            requireCounts(service, counts);
            Object regs = api.getMethod("getRegistrationInfoByPhoneId", int.class)
                    .invoke(service, 0);
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
                        (Integer) getter(reg, "getPhoneId"), rat, mmtel,
                        (Boolean) getter(profile, "hasEmergencySupport"),
                        (Integer) getter(profile, "getCmcType"));
                matched |= normal;
                if (normal) Log.i(TAG, "SA2 normal registration rat=" + rat + " epdg=" + epdg
                        + " (call transport drives selection)");
            }
            if (!matched) throw new IllegalStateException("No normal LTE/IWLAN IMS registration");
            requireCounts(service, counts);
            SamsungImsAudioTransition.run(plan.toWifi, new SamsungImsAudioTransition.Operations() {
                private void check(String next) {
                    stage[0] = next;
                    if (!enabled() || !policy.current(plan))
                        throw new IllegalStateException("Call/transport changed; no further audio writes");
                }
                public void audioPath(int direction) throws Exception {
                    check("audioPath=" + direction);
                    requireCounts(service, counts);
                    audioPath.invoke(service, 0, direction);
                    Log.i(TAG, "SA2 audioPath=" + direction + " phone=0 generation=" + plan.generation);
                }
                public void simSlot() {
                    check("simSlot=0");
                    audio.setParameters("g_call_sim_slot=0x01");
                    Log.i(TAG, "SA2 g_call_sim_slot=0x01");
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

    private static void requireCounts(Object service, Method method) throws Exception {
        if (!Arrays.equals((int[]) method.invoke(service, 0), new int[] {1, 0, 0, 0})
                || !Arrays.equals((int[]) method.invoke(service, 1), new int[] {0, 0, 0, 0}))
            throw new IllegalStateException("Outside single ordinary slot-0 voice scope");
    }
}
