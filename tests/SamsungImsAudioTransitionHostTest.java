/* SPDX-License-Identifier: Apache-2.0 */
package com.android.server.telecom;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Host policy and stock order checks; never calls Android/Binder/device APIs. */
public final class SamsungImsAudioTransitionHostTest {
    static int checks;
    static void check(boolean value) { checks++; if (!value) throw new AssertionError(checks); }
    static List<String> sequence(boolean wifi) throws Exception {
        List<String> result = new ArrayList<>();
        SamsungImsAudioTransition.run(wifi, new SamsungImsAudioTransition.Operations() {
            public void simSlot() { result.add("slot0"); }
            public void audioPath(int v) { result.add("path" + v); }
            public void parameter(int v) { result.add("param" + v); }
            public void mode(int v) { result.add("mode" + v); }
        });
        return result;
    }
    public static void main(String[] args) throws Exception {
        for (String operator : new String[] {"46601", "46605", "46689", "46692", "46697", "310260"}) {
            check(SamsungImsAudioTransition.singleSimOperator(operator));
            check(SamsungImsAudioTransition.singleSimOperator(operator + ","));
        }
        for (String invalid : new String[] {"", ",", "4669", "4669700", "abcde", ",46697", "46697,46692"})
            check(!SamsungImsAudioTransition.singleSimOperator(invalid));
        check(!SamsungImsAudioTransition.singleSimOperator(null));
        Object call = new Object(), other = new Object();
        SamsungImsAudioTransition p = new SamsungImsAudioTransition();
        p.observe(call, true, true);
        check(!p.isVoip(call)); // Initial IWLAN must not invent a handover.
        check(p.take(3, 2) == null);
        p.observe(call, true, false);
        check(!p.isVoip(call));
        check(p.take(2, 2) == null);
        p.observe(call, true, true);
        check(p.isVoip(call));
        check(!p.isVoip(other));
        check(p.take(3, 0) == null); // Focus/actual mode must match source.
        check(p.take(2, 2) == null);
        SamsungImsAudioTransition.Plan first = p.take(3, 2);
        check(first != null && first.toWifi && p.current(first));
        check(p.take(3, 2) == null);
        p.observe(call, true, true); // Duplicate update neither retries nor invalidates.
        check(p.current(first));
        check(p.take(3, 2) == null);
        p.complete(first);
        check(p.take(3, 3) == null);
        p.observe(call, true, false);
        check(!p.current(first));
        SamsungImsAudioTransition.Plan reverse = p.take(2, 3);
        check(reverse != null && !reverse.toWifi);
        p.complete(reverse);
        p.observe(call, true, true);
        SamsungImsAudioTransition.Plan second = p.take(3, 2);
        check(second != null && second.generation != first.generation);
        p.observe(call, false, true); // Hangup, hold, second call, emergency or disabled gate.
        check(!p.current(second) && !p.isVoip(call));
        check(p.take(3, 2) == null);
        p.complete(second); // Stale completion cannot restore ownership.
        p.observe(other, true, true);
        check(!p.isVoip(other));
        check(p.take(3, 2) == null);
        p.observe(other, true, false);
        p.observe(other, true, true);
        SamsungImsAudioTransition.Plan replacement = p.take(3, 2);
        check(replacement != null && p.current(replacement));
        p.observe(call, true, false);
        check(!p.current(replacement));
        p.observe(call, true, true);
        SamsungImsAudioTransition.Plan rapid = p.take(3, 2);
        p.observe(call, true, false);
        check(!p.current(rapid));
        check(sequence(true).equals(Arrays.asList("path2", "param1", "mode0", "param32",
                "mode3", "path0", "path7")));
        check(sequence(false).equals(Arrays.asList("slot0", "path1", "param16", "mode0", "param2", "mode2")));
        List<Integer> attempted = new ArrayList<>();
        try {
            SamsungImsAudioTransition.run(true, new SamsungImsAudioTransition.Operations() {
                public void simSlot() { throw new AssertionError("L2W selected a SIM slot"); }
                public void audioPath(int v) throws Exception { attempted.add(v); throw new Exception("blocked"); }
                public void parameter(int v) { throw new AssertionError("Continued after failure"); }
                public void mode(int v) { throw new AssertionError("Continued after failure"); }
            });
            throw new AssertionError("Ignored failure");
        } catch (Exception expected) { check(attempted.equals(Arrays.asList(2))); }
        check(SamsungImsAudioTransition.normalRegistration(0, 13, true, false, 0));
        check(SamsungImsAudioTransition.normalRegistration(0, 18, true, false, 0));
        check(!SamsungImsAudioTransition.normalRegistration(1, 18, true, false, 0));
        check(!SamsungImsAudioTransition.normalRegistration(0, 11, true, false, 0));
        check(!SamsungImsAudioTransition.normalRegistration(0, 0, true, false, 0));
        check(!SamsungImsAudioTransition.normalRegistration(0, 18, false, false, 0));
        check(!SamsungImsAudioTransition.normalRegistration(0, 18, true, true, 0));
        check(!SamsungImsAudioTransition.normalRegistration(0, 18, true, false, 1));
        System.out.println("PASS: " + checks + " SA2 ownership, transition and stock-order checks");
    }
}
