/* SPDX-License-Identifier: Apache-2.0 */
package com.android.server.telecom;

/** Call-scoped stock audio transition policy. No Android, Binder, timers or network operations. */
final class SamsungImsAudioTransition {
    private Object call;
    private boolean eligible, wifi, sawLte;
    private int selectedMode;
    private long generation, attempted = -1;

    static boolean singleSimOperator(String value) {
        if (value == null) return false;
        String[] slots = value.split(",", -1);
        // Identity sanity check, not a carrier allowlist. Keep the existing slot-0 scope.
        if (!slots[0].matches("[0-9]{5,6}")) return false;
        for (int i = 1; i < slots.length; i++) if (!slots[i].isEmpty()) return false;
        return true;
    }

    synchronized void observe(Object identity, boolean allowed, boolean onWifi) {
        if (!allowed || identity == null) {
            call = null;
            eligible = sawLte = false;
            selectedMode = 0;
            generation++;
            return;
        }
        if (call != identity) {
            call = identity;
            sawLte = false;
            selectedMode = 0;
            generation++;
        }
        if (!eligible || wifi != onWifi) generation++;
        eligible = true;
        wifi = onWifi;
        // Initial IWLAN calls stay on their existing path, including BT1/MT handling.
        if (!wifi && !sawLte) {
            sawLte = true;
            selectedMode = 2;
        }
    }

    synchronized boolean isVoip(Object identity) {
        return eligible && call == identity && sawLte && wifi;
    }

    synchronized boolean owns(Object identity) { return eligible && sawLte && call == identity; }

    static boolean normalRegistration(int phone, int rat, boolean mmtel, boolean emergency, int cmc) {
        // Stock selects the engine from the CALL's new transport, before IMS registration
        // necessarily finishes changing RAT/ePDG status. A normal source registration is valid.
        return phone == 0 && (rat == 13 || rat == 18) && mmtel && !emergency && cmc == 0;
    }

    synchronized Plan take(int targetMode, int currentMode) {
        int desired = wifi ? 3 : 2;
        if (!eligible || !sawLte || targetMode != desired || selectedMode == desired
                || selectedMode != currentMode || attempted == generation) return null;
        attempted = generation;
        return new Plan(call, generation, wifi);
    }

    synchronized boolean current(Plan plan) {
        return eligible && call == plan.call && generation == plan.generation
                && wifi == plan.toWifi;
    }

    synchronized void complete(Plan plan) {
        if (current(plan)) selectedMode = plan.toWifi ? 3 : 2;
    }

    static final class Plan {
        final Object call;
        final long generation;
        final boolean toWifi;
        Plan(Object call, long generation, boolean toWifi) {
            this.call = call; this.generation = generation; this.toWifi = toWifi;
        }
    }

    interface Operations {
        void simSlot() throws Exception;
        void audioPath(int direction) throws Exception;
        void parameter(int value) throws Exception;
        void mode(int mode) throws Exception;
    }

    /** Order derived from stock Samsung Telecom; integer parameters are g_call_state values. */
    static void run(boolean toWifi, Operations ops) throws Exception {
        if (toWifi) {
            ops.audioPath(2);  // STOP current engine before changing MODE_IN_CALL.
            ops.parameter(1); // CP voice/video OFF.
            ops.mode(0);
            ops.parameter(32); // SEC_WIFI_CALL_ON.
            ops.mode(3);
            ops.audioPath(0);  // SAE, after communication mode is set.
            ops.audioPath(7);  // Stock INFORM maps to DELAYED_MEDIA in IMS.
        } else {
            ops.simSlot(); // Stock setAudioParametersForVsid(MODE_IN_CALL), slot 0.
            ops.audioPath(1);  // CPVE before turning off the Wi-Fi audio mode.
            ops.parameter(16); // SEC_WIFI_CALL_OFF.
            ops.mode(0);
            ops.parameter(2); // CP_VOICE_CALL_ON.
            ops.mode(2);
        }
    }
}
