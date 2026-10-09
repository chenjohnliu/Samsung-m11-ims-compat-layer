package android.os;

public final class HandlerThread {
    private static int starts;
    private final Looper looper = new Looper();
    public HandlerThread(String name) {}
    public void start() { starts++; }
    public Looper getLooper() { return looper; }
    public static int starts() { return starts; }
    public static void resetStarts() { starts = 0; }
}
