package android.provider;

import android.content.ContentResolver;
import java.util.HashMap;
import java.util.Map;

public final class Settings {
    private Settings() {}
    private static final Map<String, Integer> GLOBAL = new HashMap<>();
    private static final Map<String, Integer> SYSTEM = new HashMap<>();
    private static final Map<String, Integer> SECURE = new HashMap<>();
    private static int reads;
    public static void reset() { GLOBAL.clear(); SYSTEM.clear(); SECURE.clear(); reads = 0; }
    public static void seed(String table, String key, int value) { map(table).put(key, value); }
    public static int reads() { return reads; }
    private static int read(Map<String, Integer> values, String key, int fallback) {
        reads++;
        return values.getOrDefault(key, fallback);
    }
    private static Map<String, Integer> map(String table) {
        if ("global".equals(table)) return GLOBAL;
        if ("system".equals(table)) return SYSTEM;
        if ("secure".equals(table)) return SECURE;
        throw new IllegalArgumentException(table);
    }
    public static final class Global {
        public static int getInt(ContentResolver resolver, String key, int fallback) {
            return read(GLOBAL, key, fallback);
        }
    }
    public static final class System {
        public static int getInt(ContentResolver resolver, String key, int fallback) {
            return read(SYSTEM, key, fallback);
        }
    }
    public static final class Secure {
        public static int getInt(ContentResolver resolver, String key, int fallback) {
            return read(SECURE, key, fallback);
        }
    }
}
