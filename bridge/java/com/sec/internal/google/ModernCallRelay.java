package com.sec.internal.google;
import android.os.RemoteException;
import android.telephony.ims.aidl.IImsCallSessionListener;
import java.util.ArrayDeque;

/** Serial pre-publication relay; a terminal event is retained even under event overload. */
public final class ModernCallRelay extends IImsCallSessionListener.Stub {
    static final ThreadLocal<ModernCallRelay> CONSTRUCTION = new ThreadLocal<>();
    public static IImsCallSessionListener constructionListener(IImsCallSessionListener original) {
        ModernCallRelay relay = CONSTRUCTION.get();
        return original == null && relay != null ? relay : original;
    }
    private final ModernEventQueue<IImsCallSessionListener> queue = new ModernEventQueue<>(
        l -> l.callSessionTerminated(ModernVoiceContext.reason("Native event queue overflow")));
    void attach(IImsCallSessionListener next) { queue.attach(next); }
    void clear() { queue.clear(); }
    void onOverflow(Runnable action) { queue.onOverflow(action); }
    boolean hasOverflowed() { return queue.hasOverflowed(); }
    private void emit(ModernEventQueue.Event<IImsCallSessionListener> event, boolean end) { queue.emit(event, end); }
    void fail(String message, boolean start) {
        if (start) callSessionInitiatingFailed(ModernVoiceContext.reason(message));
        else callSessionTerminated(ModernVoiceContext.reason(message));
    }
    @Override public void callSessionInitiating(android.telephony.ims.ImsCallProfile p0) { emit(l -> l.callSessionInitiating(p0), false); }
    @Override public void callSessionInitiatingFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionInitiatingFailed(p0), true); }
    @Override public void callSessionProgressing(android.telephony.ims.ImsStreamMediaProfile p0) { emit(l -> l.callSessionProgressing(p0), false); }
    @Override public void callSessionInitiated(android.telephony.ims.ImsCallProfile p0) { emit(l -> l.callSessionInitiated(p0), false); }
    @Override public void callSessionInitiatedFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionInitiatedFailed(p0), true); }
    @Override public void callSessionTerminated(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionTerminated(p0), true); }
    @Override public void callSessionHeld(android.telephony.ims.ImsCallProfile p0) { emit(l -> l.callSessionHeld(p0), false); }
    @Override public void callSessionHoldFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionHoldFailed(p0), false); }
    @Override public void callSessionHoldReceived(android.telephony.ims.ImsCallProfile p0) { emit(l -> l.callSessionHoldReceived(p0), false); }
    @Override public void callSessionResumed(android.telephony.ims.ImsCallProfile p0) { emit(l -> l.callSessionResumed(p0), false); }
    @Override public void callSessionResumeFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionResumeFailed(p0), false); }
    @Override public void callSessionResumeReceived(android.telephony.ims.ImsCallProfile p0) { emit(l -> l.callSessionResumeReceived(p0), false); }
    @Override public void callSessionMergeStarted(com.android.ims.internal.IImsCallSession p0, android.telephony.ims.ImsCallProfile p1) { emit(l -> l.callSessionMergeStarted(p0, p1), false); }
    @Override public void callSessionMergeComplete(com.android.ims.internal.IImsCallSession p0) { emit(l -> l.callSessionMergeComplete(p0), false); }
    @Override public void callSessionMergeFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionMergeFailed(p0), false); }
    @Override public void callSessionUpdated(android.telephony.ims.ImsCallProfile p0) { emit(l -> l.callSessionUpdated(p0), false); }
    @Override public void callSessionUpdateFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionUpdateFailed(p0), false); }
    @Override public void callSessionUpdateReceived(android.telephony.ims.ImsCallProfile p0) { emit(l -> l.callSessionUpdateReceived(p0), false); }
    @Override public void callSessionConferenceExtended(com.android.ims.internal.IImsCallSession p0, android.telephony.ims.ImsCallProfile p1) { emit(l -> l.callSessionConferenceExtended(p0, p1), false); }
    @Override public void callSessionConferenceExtendFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionConferenceExtendFailed(p0), false); }
    @Override public void callSessionConferenceExtendReceived(com.android.ims.internal.IImsCallSession p0, android.telephony.ims.ImsCallProfile p1) { emit(l -> l.callSessionConferenceExtendReceived(p0, p1), false); }
    @Override public void callSessionInviteParticipantsRequestDelivered() { emit(l -> l.callSessionInviteParticipantsRequestDelivered(), false); }
    @Override public void callSessionInviteParticipantsRequestFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionInviteParticipantsRequestFailed(p0), false); }
    @Override public void callSessionRemoveParticipantsRequestDelivered() { emit(l -> l.callSessionRemoveParticipantsRequestDelivered(), false); }
    @Override public void callSessionRemoveParticipantsRequestFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionRemoveParticipantsRequestFailed(p0), false); }
    @Override public void callSessionConferenceStateUpdated(android.telephony.ims.ImsConferenceState p0) { emit(l -> l.callSessionConferenceStateUpdated(p0), false); }
    @Override public void callSessionUssdMessageReceived(int p0, java.lang.String p1) { emit(l -> l.callSessionUssdMessageReceived(p0, p1), false); }
    @Override public void callSessionHandover(int p0, int p1, android.telephony.ims.ImsReasonInfo p2) { emit(l -> l.callSessionHandover(p0, p1, p2), false); }
    @Override public void callSessionHandoverFailed(int p0, int p1, android.telephony.ims.ImsReasonInfo p2) { emit(l -> l.callSessionHandoverFailed(p0, p1, p2), false); }
    @Override public void callSessionMayHandover(int p0, int p1) { emit(l -> l.callSessionMayHandover(p0, p1), false); }
    @Override public void callSessionTtyModeReceived(int p0) { emit(l -> l.callSessionTtyModeReceived(p0), false); }
    @Override public void callSessionMultipartyStateChanged(boolean p0) { emit(l -> l.callSessionMultipartyStateChanged(p0), false); }
    @Override public void callSessionSuppServiceReceived(android.telephony.ims.ImsSuppServiceNotification p0) { emit(l -> l.callSessionSuppServiceReceived(p0), false); }
    @Override public void callSessionRttModifyRequestReceived(android.telephony.ims.ImsCallProfile p0) { emit(l -> l.callSessionRttModifyRequestReceived(p0), false); }
    @Override public void callSessionRttModifyResponseReceived(int p0) { emit(l -> l.callSessionRttModifyResponseReceived(p0), false); }
    @Override public void callSessionRttMessageReceived(java.lang.String p0) { emit(l -> l.callSessionRttMessageReceived(p0), false); }
    @Override public void callSessionRttAudioIndicatorChanged(android.telephony.ims.ImsStreamMediaProfile p0) { emit(l -> l.callSessionRttAudioIndicatorChanged(p0), false); }
    @Override public void callSessionTransferred() { emit(l -> l.callSessionTransferred(), false); }
    @Override public void callSessionTransferFailed(android.telephony.ims.ImsReasonInfo p0) { emit(l -> l.callSessionTransferFailed(p0), false); }
    @Override public void callSessionDtmfReceived(char p0) { emit(l -> l.callSessionDtmfReceived(p0), false); }
    @Override public void callQualityChanged(android.telephony.CallQuality p0) { emit(l -> l.callQualityChanged(p0), false); }
    @Override public void callSessionRtpHeaderExtensionsReceived(java.util.List<android.telephony.ims.RtpHeaderExtension> p0) { emit(l -> l.callSessionRtpHeaderExtensionsReceived(p0), false); }
}
