package com.sec.internal.google;
import android.os.RemoteException;
import com.android.ims.internal.IImsCallSession;

/** Typed A13 binder facade. Samsung owns call/media policy and the actual native session. */
final class ModernCallSession extends IImsCallSession.Stub {
    final ModernVoiceContext owner;
    final long epoch;
    final String id;
    private final IImsCallSession nativeSession;
    private final ModernCallRelay relay;
    private boolean closed;
    ModernCallSession(ModernVoiceContext owner, long epoch, String id,
            IImsCallSession nativeSession, ModernCallRelay relay) {
        this.owner = owner; this.epoch = epoch; this.id = id;
        this.nativeSession = nativeSession; this.relay = relay;
        relay.onOverflow(() -> owner.sessionOverflow(this));
    }
    private void check() throws RemoteException {
        synchronized (owner) {
            if (closed || !owner.current(epoch)) throw new RemoteException("Native session no longer owned");
        }
    }
    void invalidate(String reason) {
        synchronized (owner) { if (closed) return; }
        relay.fail(reason, false);
        try { nativeSession.terminate(501); } catch (Exception ignored) {}
        cleanup(false);
    }
    private void cleanup(boolean clear) {
        if (clear) relay.clear();
        synchronized (owner) { if (closed) return; closed = true; owner.sessionClosed(this); }
        try { ((ImsCallSessionImpl)nativeSession).releaseSessionListeners(); } catch (Exception ignored) {}
        try { nativeSession.close(); } catch (Exception ignored) {}
    }
    @Override public void close() { cleanup(true); }
    @Override public void setListener(android.telephony.ims.aidl.IImsCallSessionListener listener) {
        relay.attach(listener);
    }
    @Override public java.lang.String getCallId() throws RemoteException {
        check();
        return nativeSession.getCallId();
    }
    @Override public android.telephony.ims.ImsCallProfile getCallProfile() throws RemoteException {
        check();
        return nativeSession.getCallProfile();
    }
    @Override public android.telephony.ims.ImsCallProfile getLocalCallProfile() throws RemoteException {
        check();
        return nativeSession.getLocalCallProfile();
    }
    @Override public android.telephony.ims.ImsCallProfile getRemoteCallProfile() throws RemoteException {
        check();
        return nativeSession.getRemoteCallProfile();
    }
    @Override public java.lang.String getProperty(java.lang.String p0) throws RemoteException {
        check();
        return nativeSession.getProperty(p0);
    }
    @Override public int getState() throws RemoteException {
        check();
        return nativeSession.getState();
    }
    @Override public boolean isInCall() throws RemoteException {
        check();
        return nativeSession.isInCall();
    }
    @Override public void setMute(boolean p0) throws RemoteException {
        check();
        nativeSession.setMute(p0);
    }
    @Override public void start(java.lang.String p0, android.telephony.ims.ImsCallProfile p1) throws RemoteException {
        check();
        try { nativeSession.start(p0, p1); }
        catch (RemoteException | RuntimeException e) { relay.fail("Native start failed", true); throw new RemoteException("Native start failed"); }
    }
    @Override public void startConference(java.lang.String[] p0, android.telephony.ims.ImsCallProfile p1) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void accept(int p0, android.telephony.ims.ImsStreamMediaProfile p1) throws RemoteException {
        check();
        try { nativeSession.accept(p0, p1); }
        catch (RemoteException | RuntimeException e) { relay.fail("Native accept failed", false); throw new RemoteException("Native accept failed"); }
    }
    @Override public void deflect(java.lang.String p0) throws RemoteException {
        check();
        nativeSession.deflect(p0);
    }
    @Override public void reject(int p0) throws RemoteException {
        check();
        try { nativeSession.reject(p0); }
        catch (RemoteException | RuntimeException e) { relay.fail("Native reject failed", false); throw new RemoteException("Native reject failed"); }
    }
    @Override public void transfer(java.lang.String p0, boolean p1) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void consultativeTransfer(com.android.ims.internal.IImsCallSession p0) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void terminate(int p0) throws RemoteException {
        check();
        try { nativeSession.terminate(p0); }
        catch (RemoteException | RuntimeException e) { relay.fail("Native terminate failed", false); throw new RemoteException("Native terminate failed"); }
    }
    @Override public void hold(android.telephony.ims.ImsStreamMediaProfile p0) throws RemoteException {
        check();
        nativeSession.hold(p0);
    }
    @Override public void resume(android.telephony.ims.ImsStreamMediaProfile p0) throws RemoteException {
        check();
        nativeSession.resume(p0);
    }
    @Override public void merge() throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void update(int p0, android.telephony.ims.ImsStreamMediaProfile p1) throws RemoteException {
        check();
        nativeSession.update(p0, p1);
    }
    @Override public void extendToConference(java.lang.String[] p0) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void inviteParticipants(java.lang.String[] p0) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void removeParticipants(java.lang.String[] p0) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void sendDtmf(char p0, android.os.Message p1) throws RemoteException {
        check();
        nativeSession.sendDtmf(p0, p1);
    }
    @Override public void startDtmf(char p0) throws RemoteException {
        check();
        nativeSession.startDtmf(p0);
    }
    @Override public void stopDtmf() throws RemoteException {
        check();
        nativeSession.stopDtmf();
    }
    @Override public void sendUssd(java.lang.String p0) throws RemoteException {
        check();
        nativeSession.sendUssd(p0);
    }
    @Override public com.android.ims.internal.IImsVideoCallProvider getVideoCallProvider() throws RemoteException {
        check();
        return nativeSession.getVideoCallProvider();
    }
    @Override public boolean isMultiparty() throws RemoteException {
        check();
        return nativeSession.isMultiparty();
    }
    @Override public void sendRttModifyRequest(android.telephony.ims.ImsCallProfile p0) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void sendRttModifyResponse(boolean p0) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void sendRttMessage(java.lang.String p0) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
    @Override public void sendRtpHeaderExtensions(java.util.List<android.telephony.ims.RtpHeaderExtension> p0) throws RemoteException {
        throw new RemoteException("Operation outside BC2 normal voice scope");
    }
}
