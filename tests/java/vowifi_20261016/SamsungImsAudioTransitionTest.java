/* SPDX-License-Identifier: Apache-2.0 */
package com.android.server.telecom;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Standalone pure-Java policy tests; run with javac/java and no Android framework classes. */
public final class SamsungImsAudioTransitionTest {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static void equal(Object expected, Object actual, String message) {
        if (!expected.equals(actual))
            throw new AssertionError(message + ": expected=" + expected + " actual=" + actual);
    }

    private static final class Recorder implements SamsungImsAudioTransition.Operations {
        final List<String> events = new ArrayList<>();
        public void simSlot() { events.add("slot"); }
        public void audioPath(int direction) { events.add("audio:" + direction); }
        public void parameter(int value) { events.add("param:" + value); }
        public void mode(int mode) { events.add("mode:" + mode); }
    }

    private static SamsungImsAudioTransition.Plan initial(Object call, int mode) {
        SamsungImsAudioTransition policy = new SamsungImsAudioTransition();
        policy.observe(call, true, true, 0, 1, true);
        check(policy.isVoip(call), "eligible initial Wi-Fi call selects VoIP focus");
        check(!policy.owns(call, 0, 1), "initial Wi-Fi must not claim LTE origin");
        SamsungImsAudioTransition.Plan plan = policy.take(3, mode);
        check(plan != null && plan.initial && plan.fromMode == mode,
                "initial plan records its starting mode");
        check(policy.current(plan), "new initial plan is current");
        return plan;
    }

    private static void testInitialInformFromModesZeroAndOne() throws Exception {
        for (int from : new int[] {0, 1}) {
            SamsungImsAudioTransition.Plan plan = initial(new Object(), from);
            Recorder recorder = new Recorder();
            SamsungImsAudioTransition.run(plan, recorder);
            equal(Arrays.asList("param:32", "mode:3", "audio:7"), recorder.events,
                    "initial Wi-Fi must use parameter/mode/INFORM only");
        }
    }

    private static void testInitialModeTwoUsesExistingStockOrder() throws Exception {
        SamsungImsAudioTransition.Plan plan = initial(new Object(), 2);
        Recorder recorder = new Recorder();
        SamsungImsAudioTransition.run(plan, recorder);
        equal(Arrays.asList("audio:2", "param:1", "mode:0", "param:32", "mode:3",
                "audio:0", "audio:7"), recorder.events,
                "late initial entry from MODE_IN_CALL must use existing handover order");
    }

    private static void testInitialWifiToLteToWifi() throws Exception {
        Object call = new Object();
        SamsungImsAudioTransition policy = new SamsungImsAudioTransition();
        policy.observe(call, true, true, 1, 22, true);
        SamsungImsAudioTransition.Plan first = policy.take(3, 1);
        check(first != null && first.initial, "initial Wi-Fi transition planned");
        policy.complete(first);
        policy.observe(call, true, false, 1, 22, false);
        check(policy.owns(call, 1, 22), "valid LTE observation establishes LTE origin");
        check(!policy.isVoip(call), "LTE is not Wi-Fi VoIP focus");
        SamsungImsAudioTransition.Plan toLte = policy.take(2, 3);
        check(toLte != null && !toLte.initial && !toLte.toWifi,
                "Wi-Fi to LTE after initial call is ordinary handover");
        policy.complete(toLte);
        policy.observe(call, true, true, 1, 22, false);
        SamsungImsAudioTransition.Plan toWifi = policy.take(3, 2);
        check(toWifi != null && !toWifi.initial && toWifi.toWifi,
                "subsequent LTE to Wi-Fi is ordinary handover");
        Recorder recorder = new Recorder();
        SamsungImsAudioTransition.run(toWifi, recorder);
        equal(Arrays.asList("audio:2", "param:1", "mode:0", "param:32", "mode:3",
                "audio:0", "audio:7"), recorder.events,
                "ordinary L2W sequence remains unchanged");
    }

    private static void testOldLteOriginHandover() throws Exception {
        Object call = new Object();
        SamsungImsAudioTransition policy = new SamsungImsAudioTransition();
        policy.observe(call, true, false, 0, 10);
        check(policy.owns(call, 0, 10), "old caller still explicitly observes LTE");
        check(policy.take(2, 2) == null, "no-op LTE mode is idempotent");
        policy.observe(call, true, true, 0, 10);
        SamsungImsAudioTransition.Plan plan = policy.take(3, 2);
        check(plan != null && !plan.initial, "old LTE-origin call uses ordinary L2W plan");
        Recorder recorder = new Recorder();
        SamsungImsAudioTransition.run(plan, recorder);
        equal(Arrays.asList("audio:2", "param:1", "mode:0", "param:32", "mode:3",
                "audio:0", "audio:7"), recorder.events,
                "old L2W operation ordering remains unchanged");
    }

    private static void testRepeatAndGenerationInvalidation() {
        Object call = new Object();
        SamsungImsAudioTransition policy = new SamsungImsAudioTransition();
        policy.observe(call, true, true, 0, 1, true);
        SamsungImsAudioTransition.Plan first = policy.take(3, 0);
        check(first != null, "first attempt accepted");
        check(policy.take(3, 0) == null, "same generation cannot retry");
        policy.observe(call, true, true, 0, 1, true);
        check(policy.take(3, 0) == null, "identical observation does not permit retry");
        policy.observe(call, true, true, 0, 1, false);
        check(!policy.current(first), "removing initial eligibility invalidates stale plan");
        check(policy.take(3, 0) == null, "unmarked initial Wi-Fi has no plan");
        policy.observe(call, true, true, 0, 1, true);
        SamsungImsAudioTransition.Plan second = policy.take(3, 0);
        check(second != null && second.generation != first.generation,
                "new eligible generation can make a fresh plan");
        policy.observe(new Object(), true, true, 0, 1, true);
        check(!policy.current(second), "new call identity invalidates old plan");
        check(policy.take(3, 0) != null, "new call identity receives its own plan");
        policy.observe(call, false, true, 0, 1, true);
        check(!policy.current(second), "invalid scope clears plan");
    }

    private static void testInitialOwnershipEligibilityAcrossScopeChanges() {
        Object initialCall = new Object();
        SamsungImsAudioTransition policy = new SamsungImsAudioTransition();
        policy.observe(initialCall, true, true, 0, 7, true);
        SamsungImsAudioTransition.Plan initialPlan = policy.take(3, 1);
        check(initialPlan != null, "initial call plan exists");
        policy.complete(initialPlan);
        check(policy.matchesEligibleIdentity(initialCall, 0, 7),
                "adapter's initial owner remains eligible for same call");
        check(!policy.owns(initialCall, 0, 7),
                "cleanup identity must not imply LTE-origin ownership");

        // A new call replaces the active policy identity; the old adapter owner is now stale.
        Object nextCall = new Object();
        policy.observe(nextCall, true, true, 0, 7, false);
        check(!policy.matchesEligibleIdentity(initialCall, 0, 7),
                "new call identity invalidates initial cleanup owner");
        check(!policy.matchesEligibleIdentity(nextCall, 0, 7),
                "unmarked Wi-Fi call is not an initial-cleanup context");
        check(!policy.isVoip(nextCall), "unmarked Wi-Fi call does not retain VoIP focus");

        // Re-enabling initial eligibility for the same call creates the supported context again.
        policy.observe(nextCall, true, true, 0, 7, true);
        check(policy.matchesEligibleIdentity(nextCall, 0, 7),
                "freshly eligible initial Wi-Fi call matches cleanup context");
        SamsungImsAudioTransition.Plan nextPlan = policy.take(3, 0);
        check(nextPlan != null, "fresh initial generation can plan audio setup");
        policy.complete(nextPlan);

        // Withdrawing the opt-in for this still-active Wi-Fi call must release the old parameter.
        policy.observe(nextCall, true, true, 0, 7, false);
        check(!policy.matchesEligibleIdentity(nextCall, 0, 7),
                "withdrawing initial eligibility invalidates cleanup identity");

        // Lost CAM scope clears policy eligibility and therefore authorizes cleanup of the
        // adapter-owned initial parameter, without changing LTE-origin ownership semantics.
        policy.observe(nextCall, false, true, 0, 7, false);
        check(!policy.matchesEligibleIdentity(nextCall, 0, 7),
                "lost eligibility invalidates cleanup identity");
        check(!policy.owns(nextCall, 0, 7), "lost scope is not LTE ownership");

        Object lteCall = new Object();
        policy.observe(lteCall, true, false, 0, 7, false);
        check(policy.matchesEligibleIdentity(lteCall, 0, 7),
                "eligible LTE call matches cleanup predicate");
        check(policy.owns(lteCall, 0, 7), "LTE provenance remains independently owned");
        policy.observe(lteCall, false, false, 0, 7, false);
        check(!policy.matchesEligibleIdentity(lteCall, 0, 7),
                "loss of LTE call scope invalidates cleanup identity");
        check(!policy.owns(lteCall, 0, 7), "loss of LTE scope clears provenance");
    }

    private static void testInvalidModesAndScope() {
        Object call = new Object();
        SamsungImsAudioTransition policy = new SamsungImsAudioTransition();
        policy.observe(call, true, true, 0, 1, true);
        for (int mode : new int[] {-1, 3, 4})
            check(policy.take(3, mode) == null, "initial plan rejects unsupported mode " + mode);
        check(policy.take(2, 1) == null, "initial plan requires target mode 3");
        policy.observe(call, true, true, 2, 1, true);
        check(!policy.isVoip(call) && policy.take(3, 0) == null,
                "unsupported phone slot invalidates eligibility");
        policy.observe(call, true, true, 0, -1, true);
        check(policy.take(3, 0) == null, "invalid subscription invalidates eligibility");
        check(!policy.owns(call, 0, 1), "invalid/initial state never owns LTE origin");
        check(!SamsungImsAudioTransition.normalRegistration(0, 0, 20, true, false, 0),
                "unsupported RAT is outside registration scope");
        check(!SamsungImsAudioTransition.normalRegistration(0, 0, 18, true, true, 0),
                "emergency registration is outside scope");
    }

    public static void main(String[] args) throws Exception {
        testInitialInformFromModesZeroAndOne();
        testInitialModeTwoUsesExistingStockOrder();
        testInitialWifiToLteToWifi();
        testOldLteOriginHandover();
        testRepeatAndGenerationInvalidation();
        testInitialOwnershipEligibilityAcrossScopeChanges();
        testInvalidModesAndScope();
        System.out.println("SamsungImsAudioTransition pure-Java tests: PASS");
    }
}
