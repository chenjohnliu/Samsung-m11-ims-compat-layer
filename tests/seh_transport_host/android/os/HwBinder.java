package android.os;

public abstract class HwBinder implements IHwBinder {
    private static int instrumentationCalls;

    public static void enableInstrumentation() { instrumentationCalls++; }
    public static int instrumentationCalls() { return instrumentationCalls; }
    public static void resetInstrumentationCalls() { instrumentationCalls = 0; }

    @Override
    public final void transact(int code, HwParcel request, HwParcel reply, int flags)
            throws RemoteException {
        onTransact(code, request, reply, flags);
    }

    public void onTransact(int code, HwParcel request, HwParcel reply, int flags)
            throws RemoteException {}

    @Override public boolean linkToDeath(DeathRecipient recipient, long cookie) { return true; }
    @Override public boolean unlinkToDeath(DeathRecipient recipient) { return true; }
    @Override public IHwInterface queryLocalInterface(String descriptor) { return null; }
}
