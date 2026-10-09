package android.os;

public abstract class HwBinder implements IHwBinder {
    private static IHwBinder service;
    private static int lookupCount;
    private static int failuresRemaining;
    private static String lastDescriptor;
    private static String lastInstance;
    private static boolean lastRetry;
    private static int instrumentationCalls;

    public static IHwBinder getService(String descriptor, String instance, boolean retry)
            throws RemoteException {
        lookupCount++;
        lastDescriptor = descriptor;
        lastInstance = instance;
        lastRetry = retry;
        if (failuresRemaining > 0) {
            failuresRemaining--;
            throw new RemoteException("injected lookup failure");
        }
        if (service == null) throw new RemoteException("service unavailable");
        return service;
    }

    public static void setService(IHwBinder value) { service = value; }
    public static void failNextLookups(int count) { failuresRemaining = count; }
    public static int lookupCount() { return lookupCount; }
    public static String lastDescriptor() { return lastDescriptor; }
    public static String lastInstance() { return lastInstance; }
    public static boolean lastRetry() { return lastRetry; }
    public static void resetServiceRegistry() {
        service = null;
        lookupCount = 0;
        failuresRemaining = 0;
        lastDescriptor = null;
        lastInstance = null;
        lastRetry = true;
    }

    public static void enableInstrumentation() { instrumentationCalls++; }
    public static int instrumentationCalls() { return instrumentationCalls; }
    public static void resetInstrumentationCalls() { instrumentationCalls = 0; }

    @Override public final void transact(int code, HwParcel request, HwParcel reply, int flags)
            throws RemoteException { onTransact(code, request, reply, flags); }
    public void onTransact(int code, HwParcel request, HwParcel reply, int flags)
            throws RemoteException {}
    @Override public boolean linkToDeath(DeathRecipient recipient, long cookie) { return true; }
    @Override public boolean unlinkToDeath(DeathRecipient recipient) { return true; }
    @Override public IHwInterface queryLocalInterface(String descriptor) { return null; }
}
