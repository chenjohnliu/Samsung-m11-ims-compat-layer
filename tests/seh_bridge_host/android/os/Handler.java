package android.os;

import java.util.ArrayDeque;

public final class Handler {
    private static final ArrayDeque<Runnable> TASKS = new ArrayDeque<>();
    public Handler(Looper looper) {}
    public boolean post(Runnable task) { TASKS.add(task); return true; }
    public boolean postDelayed(Runnable task, long delayMillis) { TASKS.add(task); return true; }
    public static int pending() { return TASKS.size(); }
    public static void runAll() {
        int count = 0;
        while (!TASKS.isEmpty()) {
            if (++count > 1000) throw new AssertionError("handler task loop");
            TASKS.remove().run();
        }
    }
    public static void clear() { TASKS.clear(); }
}
