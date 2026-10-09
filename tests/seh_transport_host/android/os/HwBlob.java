package android.os;

import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

public final class HwBlob {
    private final int size;
    private final Map<Long, Object> values = new HashMap<>();

    public HwBlob(int size) {
        if (size < 0) throw new IllegalArgumentException("negative blob size");
        this.size = size;
    }

    public int size() { return size; }
    public void putInt32(long offset, int value) { values.put(offset, Integer.valueOf(value)); }
    public int getInt32(long offset) { return ((Integer) required(offset, Integer.class)).intValue(); }
    public void putInt64(long offset, long value) { values.put(offset, Long.valueOf(value)); }
    public long getInt64(long offset) { return ((Long) required(offset, Long.class)).longValue(); }
    public void putBool(long offset, boolean value) { values.put(offset, Boolean.valueOf(value)); }
    public boolean getBool(long offset) {
        return ((Boolean) required(offset, Boolean.class)).booleanValue();
    }
    public void putString(long offset, String value) { values.put(offset, value); }
    public String getString(long offset) { return (String) required(offset, String.class); }
    public void putInt8Array(long offset, byte[] value) {
        values.put(offset, value == null ? null : value.clone());
    }
    public byte[] getInt8Array(long offset) {
        byte[] value = (byte[]) required(offset, byte[].class);
        return value.clone();
    }
    public void putBlob(long offset, HwBlob value) { values.put(offset, value); }
    public HwBlob getBlob(long offset) { return (HwBlob) required(offset, HwBlob.class); }

    private Object required(long offset, Class<?> type) {
        Object value = values.get(offset);
        if (value == null || !type.isInstance(value)) {
            throw new AssertionError("missing " + type.getSimpleName() + " at " + offset
                    + "; offsets=" + Arrays.toString(values.keySet().toArray()));
        }
        return value;
    }
}
