package android.os;

import java.util.HashMap;
import java.util.Map;

public final class SystemProperties {
    private static final Map<String, String> VALUES = new HashMap<>();
    private SystemProperties() {}
    public static String get(String key) { return VALUES.getOrDefault(key, ""); }
    public static boolean getBoolean(String key, boolean fallback) {
        String value = VALUES.get(key);
        if (value == null) return fallback;
        return "1".equals(value) || "true".equalsIgnoreCase(value)
                || "y".equalsIgnoreCase(value) || "yes".equalsIgnoreCase(value);
    }
    public static void set(String key, String value) { VALUES.put(key, value); }
    public static void clear() { VALUES.clear(); }
}
