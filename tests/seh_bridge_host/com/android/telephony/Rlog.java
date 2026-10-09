package com.android.telephony;

import java.util.ArrayList;
import java.util.List;

public final class Rlog {
    private static final List<String> LINES = new ArrayList<>();
    private Rlog() {}
    public static int i(String tag, String message) { LINES.add("I:" + message); return 0; }
    public static int w(String tag, String message) { LINES.add("W:" + message); return 0; }
    public static int e(String tag, String message) { LINES.add("E:" + message); return 0; }
    public static List<String> lines() { return new ArrayList<>(LINES); }
    public static void clear() { LINES.clear(); }
}
