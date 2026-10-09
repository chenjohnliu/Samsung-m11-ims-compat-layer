package android.os;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class HwParcel {
    public static final class Event {
        public final String kind;
        public final Object value;
        Event(String kind, Object value) { this.kind = kind; this.value = value; }
        @Override public String toString() { return kind + "=" + value; }
    }

    private final ArrayList<Event> events = new ArrayList<>();
    private int readIndex;
    private Integer status;
    private boolean sent;
    private boolean temporaryStorageReleased;
    private boolean released;

    public List<Event> events() { return Collections.unmodifiableList(events); }
    public Integer status() { return status; }
    public boolean sent() { return sent; }
    public boolean temporaryStorageReleased() { return temporaryStorageReleased; }
    public boolean released() { return released; }

    public void writeInterfaceToken(String value) { events.add(new Event("token", value)); }
    public void enforceInterface(String expected) {
        Event event = next("token");
        if (!expected.equals(event.value)) {
            throw new SecurityException("expected token " + expected + " but got " + event.value);
        }
    }
    public void writeStrongBinder(IHwBinder value) { events.add(new Event("binder", value)); }
    public IHwBinder readStrongBinder() { return (IHwBinder) next("binder").value; }
    public void writeString(String value) { events.add(new Event("string", value)); }
    public String readString() { return (String) next("string").value; }
    public void writeInt32(int value) { events.add(new Event("int32", Integer.valueOf(value))); }
    public int readInt32() { return ((Integer) next("int32").value).intValue(); }
    public void writeStringVector(ArrayList<String> value) {
        events.add(new Event("strings", new ArrayList<>(value)));
    }
    @SuppressWarnings("unchecked")
    public ArrayList<String> readStringVector() {
        return new ArrayList<>((ArrayList<String>) next("strings").value);
    }
    public void writeNativeHandle(NativeHandle value) { events.add(new Event("handle", value)); }
    public NativeHandle readNativeHandle() { return (NativeHandle) next("handle").value; }
    public void writeBuffer(HwBlob value) { events.add(new Event("blob", value)); }
    public HwBlob readBuffer() { return (HwBlob) next("blob").value; }
    public void writeStatus(int value) { status = Integer.valueOf(value); }
    public void verifySuccess() throws RemoteException {
        if (status == null || status.intValue() != 0) {
            throw new RemoteException("transaction status=" + status);
        }
    }
    public void send() { sent = true; }
    public void releaseTemporaryStorage() { temporaryStorageReleased = true; }
    public void release() { released = true; }

    private Event next(String kind) {
        if (readIndex >= events.size()) throw new AssertionError("missing " + kind);
        Event event = events.get(readIndex++);
        if (!kind.equals(event.kind)) {
            throw new AssertionError("expected " + kind + " but got " + event.kind
                    + " at event " + (readIndex - 1));
        }
        return event;
    }
}
