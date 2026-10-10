/* SPDX-License-Identifier: Apache-2.0 */
package com.android.server.telecom;
import java.util.Arrays;

/** Call-scoped stock audio transition policy. No Android, Binder, timers or network operations. */
final class SamsungImsAudioTransition {
    private Object call;
    private int phoneId = -1, subscriptionId = -1;
    private boolean eligible, wifi, sawLte;
    private int selectedMode;
    private long generation, attempted = -1;

    static int singleSimPhone(String value) {
        if (value == null) return -1;
        String[] slots = value.split(",", -1);
        if (slots.length > 2) return -1;
        int phone = -1;
        for (int i = 0; i < slots.length; i++) {
            if (slots[i].isEmpty()) continue;
            if (!slots[i].matches("[0-9]{5,6}") || phone != -1) return -1;
            phone = i;
        }
        return phone;
    }

    static boolean supportedPhone(int phone) { return phone == 0 || phone == 1; }

    static String simSlotParameter(int phone) {
        if (phone == 0) return "g_call_sim_slot=0x01";
        if (phone == 1) return "g_call_sim_slot=0x02";
        throw new IllegalArgumentException("Unsupported SIM slot");
    }

    static boolean ordinaryCounts(int phone, int[] selected, int[] other) {
        return supportedPhone(phone) && Arrays.equals(selected, new int[] {1, 0, 0, 0})
                && Arrays.equals(other, new int[] {0, 0, 0, 0});
    }

    synchronized void observe(Object identity, boolean allowed, boolean onWifi, int phone, int subId) {
        if (!allowed || identity == null || !supportedPhone(phone) || subId < 0) {
            call = null;
            phoneId = subscriptionId = -1;
            eligible = sawLte = false;
            selectedMode = 0;
            generation++;
            return;
        }
        if (call != identity || phoneId != phone || subscriptionId != subId) {
            call = identity;
            phoneId = phone;
            subscriptionId = subId;
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

    synchronized boolean owns(Object identity, int phone, int subId) {
        return eligible && sawLte && call == identity && phoneId == phone && subscriptionId == subId;
    }

    static boolean normalRegistration(int expectedPhone, int phone, int rat,
            boolean mmtel, boolean emergency, int cmc) {
        // Stock selects the engine from the CALL's new transport, before IMS registration
        // necessarily finishes changing RAT/ePDG status. A normal source registration is valid.
        return supportedPhone(expectedPhone) && phone == expectedPhone
                && (rat == 13 || rat == 18) && mmtel && !emergency && cmc == 0;
    }

    synchronized Plan take(int targetMode, int currentMode) {
        int desired = wifi ? 3 : 2;
        if (!eligible || !sawLte || targetMode != desired || selectedMode == desired
                || selectedMode != currentMode || attempted == generation) return null;
        attempted = generation;
        return new Plan(call, generation, wifi, phoneId, subscriptionId);
    }

    synchronized boolean current(Plan plan) {
        return eligible && call == plan.call && generation == plan.generation
                && wifi == plan.toWifi && phoneId == plan.phoneId && subscriptionId == plan.subscriptionId;
    }

    synchronized void complete(Plan plan) {
        if (current(plan)) selectedMode = plan.toWifi ? 3 : 2;
    }

    static final class Plan {
        final Object call;
        final long generation;
        final boolean toWifi;
        final int phoneId, subscriptionId;
        Plan(Object call, long generation, boolean toWifi, int phoneId, int subId) {
            this.call = call; this.generation = generation; this.toWifi = toWifi;
            this.phoneId = phoneId; this.subscriptionId = subId;
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
            ops.simSlot(); // Stock setAudioParametersForVsid(MODE_IN_CALL), selected slot.
            ops.audioPath(1);  // CPVE before turning off the Wi-Fi audio mode.
            ops.parameter(16); // SEC_WIFI_CALL_OFF.
            ops.mode(0);
            ops.parameter(2); // CP_VOICE_CALL_ON.
            ops.mode(2);
        }
    }
}
