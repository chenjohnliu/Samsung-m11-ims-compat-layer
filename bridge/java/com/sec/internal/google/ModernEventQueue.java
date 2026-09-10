package com.sec.internal.google;

import java.util.ArrayDeque;

/** Host-testable serialized delivery. No application callback runs while its monitor is held. */
final class ModernEventQueue<T> {
    interface Event<T> { void send(T target) throws Exception; }
    private final ArrayDeque<Event<T>> events = new ArrayDeque<>();
    private final Event<T> overflowEvent;
    private T target;
    private boolean terminal, draining, closed, overflowed;
    private long version;
    private Runnable overflow;
    ModernEventQueue(Event<T> overflowEvent) { this.overflowEvent = overflowEvent; }
    void onOverflow(Runnable action) { synchronized (this) { overflow = action; } }
    synchronized boolean hasOverflowed() { return overflowed; }
    void attach(T next) { synchronized (this) { target = next; } drain(); }
    void clear() { synchronized (this) { closed = true; version++; events.clear(); target = null; } }
    void emit(Event<T> event, boolean end) {
        Runnable failure = null;
        synchronized (this) {
            if (closed || terminal) return;
            if (events.size() >= 64) {
                version++; events.clear(); terminal = true; overflowed = true; events.add(overflowEvent); failure = overflow;
            } else { terminal = end; events.add(event); }
        }
        try { if (failure != null) failure.run(); }
        finally { drain(); }
    }
    private void drain() {
        synchronized (this) { if (draining) return; draining = true; }
        for (;;) {
            Event<T> event;
            T recipient;
            long snapshot;
            synchronized (this) {
                if (closed || target == null || events.isEmpty()) { draining = false; return; }
                event = events.remove(); recipient = target; snapshot = version;
            }
            try { event.send(recipient); }
            catch (Exception error) {
                synchronized (this) {
                    if (!closed && snapshot == version) { events.addFirst(event); if (target == recipient) target = null; }
                    // A reentrant attach may already have supplied a replacement listener.
                    // Continue with it; otherwise the earlier attach has no future wakeup.
                    if (!closed && target != null && !events.isEmpty()) continue;
                    draining = false;
                }
                return;
            }
        }
    }
}
