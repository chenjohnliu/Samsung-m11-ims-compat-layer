package com.android.settingslib;

import java.util.HashMap;
import java.util.Map;

public final class PhoneNumberDisplayHarness {
    private static int checks;
    private static void check(boolean value) {
        if (!value) throw new AssertionError("check " + (checks + 1));
        checks++;
    }
    public static void main(String[] args) {
        SubscriptionManager sm = new SubscriptionManager();
        TelephonyManager tm = new TelephonyManager();
        sm.numbers.put(1, "+15555550123");
        check("+15555550123".equals(DeviceInfoUtils.getPhoneNumber(sm, tm, 1)));
        check(tm.calls == 0 && sm.lastSub == 1);
        sm.numbers.put(7, "");
        tm.numbers.put(7, "+15555550124");
        check("+15555550124".equals(DeviceInfoUtils.getPhoneNumber(sm, tm, 7)));
        check(tm.lastSub == 7);
        sm.failure = new SecurityException();
        check("+15555550124".equals(DeviceInfoUtils.getPhoneNumber(sm, tm, 7)));
        sm.failure = new IllegalStateException();
        check("+15555550124".equals(DeviceInfoUtils.getPhoneNumber(sm, tm, 7)));
        int modernCalls = sm.calls, legacyCalls = tm.calls;
        check(DeviceInfoUtils.getPhoneNumber(sm, tm, -1) == null);
        check(DeviceInfoUtils.getPhoneNumber(sm, tm, Integer.MAX_VALUE) == null);
        check(sm.calls == modernCalls && tm.calls == legacyCalls);
        check(DeviceInfoUtils.getPhoneNumber(null, null, 1) == null);
        check("+15555550124".equals(DeviceInfoUtils.getPhoneNumber(null, tm, 7)));
        sm.failure = null;
        check(DeviceInfoUtils.getPhoneNumber(sm, tm, 2) == null);
        tm.failure = new SecurityException();
        check(DeviceInfoUtils.getPhoneNumber(null, tm, 1) == null);
        tm.failure = new IllegalStateException();
        check(DeviceInfoUtils.getPhoneNumber(null, tm, 1) == null);
        check("+15555550123".equals(DeviceInfoUtils.getPhoneNumber(sm, null, 1)));
        check(DeviceInfoUtils.getPhoneNumber(sm, null, 2) == null);
        System.out.println("PASS: " + checks + " source-selection and fallback assertions");
    }
}

// Host-only API doubles; never shipped to Android.
class SubscriptionManager {
    final Map<Integer, String> numbers = new HashMap<>();
    RuntimeException failure;
    int calls, lastSub = -1;
    static boolean isUsableSubscriptionId(int id) {
        return id > -1 && id < Integer.MAX_VALUE;
    }
    String getPhoneNumber(int id) {
        calls++; lastSub = id;
        if (failure != null) throw failure;
        return numbers.get(id);
    }
}
class TelephonyManager {
    final Map<Integer, String> numbers = new HashMap<>();
    RuntimeException failure;
    int calls, lastSub = -1;
    TelephonyManager createForSubscriptionId(int id) {
        calls++; lastSub = id;
        return this;
    }
    String getLine1Number() {
        if (failure != null) throw failure;
        return numbers.get(lastSub);
    }
}
class TextUtils {
    static boolean isEmpty(String text) { return text == null || text.isEmpty(); }
}
