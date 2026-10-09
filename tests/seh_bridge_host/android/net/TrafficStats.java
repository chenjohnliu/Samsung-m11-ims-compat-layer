package android.net;

import java.util.HashMap;
import java.util.Map;

public final class TrafficStats {
    private static final Map<String, Long> RX = new HashMap<>();
    private static final Map<String, Long> TX = new HashMap<>();
    private TrafficStats() {}
    public static long getRxBytes(String iface) { return RX.getOrDefault(iface, -1L); }
    public static long getTxBytes(String iface) { return TX.getOrDefault(iface, -1L); }
    public static void set(String iface, long rx, long tx) { RX.put(iface, rx); TX.put(iface, tx); }
}
