package android.os;

public interface IHwBinder {
    interface DeathRecipient { void serviceDied(long cookie); }
    void transact(int code, HwParcel request, HwParcel reply, int flags) throws RemoteException;
    boolean linkToDeath(DeathRecipient recipient, long cookie) throws RemoteException;
    boolean unlinkToDeath(DeathRecipient recipient);
    IHwInterface queryLocalInterface(String descriptor);
}
