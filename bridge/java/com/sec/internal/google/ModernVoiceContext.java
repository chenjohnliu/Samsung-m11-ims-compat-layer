package com.sec.internal.google;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.RemoteException;
import android.telephony.ims.ImsCallProfile;
import android.telephony.ims.ImsReasonInfo;
import android.telephony.ims.ImsRegistrationAttributes;
import android.telephony.ims.aidl.IImsRegistration;
import android.telephony.ims.aidl.IImsRegistrationCallback;
import android.telephony.ims.stub.ImsConfigImplBase;
import android.telephony.ims.stub.ImsRegistrationImplBase;
import android.util.Log;
import com.android.ims.internal.IImsCallSession;
import com.android.ims.internal.IImsRegistrationListener;
import com.sec.ims.ImsRegistration;
import com.sec.internal.ims.registry.ImsRegistry;
import java.util.HashMap;
import java.util.Map;
import java.util.LinkedHashMap;

/** All ownership/state mutations serialize here; native callbacks carry a backend epoch. */
public final class ModernVoiceContext {
    static final String TAG = "M11ModernVoice";
    private static volatile ModernVoiceContext incomingTarget;
    // Android does not reliably replay changeEnabledCapabilities() when the same
    // feature is removed and recreated. Retention is restricted to one slot/sub pair.
    private static int retainedPhoneId = -1;
    private static int retainedSubscription = -1;
    private static volatile boolean retainedVoiceEnabled;
    private static volatile boolean retainedSmsEnabled = true;
    final int phoneId;
    final int subscription;
    final ImsRegistrationImplBase registration = new ImsRegistrationImplBase();
    final ImsConfigImplBase config = new ImsConfigImplBase();
    private final Context app;
    private final Handler handler = new Handler(Looper.getMainLooper());
    final Map<String, ModernCallSession> sessions = new HashMap<>();
    private final Map<Integer, IBinder> incoming = new LinkedHashMap<Integer, IBinder>() {
        protected boolean removeEldestEntry(Map.Entry<Integer, IBinder> entry) { return size() > 64; }
    };
    private GoogleModernMmTelFeature feature;
    GoogleImsService backend;
    private IImsRegistration nativeRegistration;
    private IImsRegistrationCallback registrationCallback;
    int serviceId = -1;
    long epoch;
    boolean disposed, voiceEnabled, smsEnabled, registered, nativeVoice;
    private boolean scheduled;
    private ImsRegistrationAttributes pendingRegistration;
    private final Runnable retry = () -> {
        synchronized (ModernVoiceContext.this) { scheduled = false; ensureBackend(); }
    };

    ModernVoiceContext(Context app, int phoneId, int subscription) {
        this.app = app; this.phoneId = phoneId; this.subscription = subscription;
        synchronized (ModernVoiceContext.class) {
            boolean samePair = retainedPhoneId == phoneId
                    && retainedSubscription == subscription;
            voiceEnabled = samePair && retainedVoiceEnabled;
            smsEnabled = samePair ? retainedSmsEnabled : true;
        }
        registration.onDeregistered(reason("Awaiting native backend"));
        if (voiceEnabled) {
            Log.i(TAG, "BQ3: Voice enablement restored across feature recreation; phoneId="
                    + phoneId);
        }
    }
    synchronized GoogleModernMmTelFeature feature() {
        if (feature == null) feature = new GoogleModernMmTelFeature(this);
        ensureBackend();
        return feature;
    }
    synchronized void ensureBackend() {
        if (disposed || feature == null) return;
        GoogleImsService current = GoogleImsService.getInstanceIfReady();
        try {
            if (backend != null && (backend != current || !backend.isOpened(serviceId))) reset("Backend context lost");
            if (backend == null && current != null) {
                backend = current;
                final long generation = ++epoch;
                PendingIntent unused = PendingIntent.getBroadcast(app, phoneId,
                    new Intent("com.sec.internal.google.BC2_UNUSED." + phoneId)
                            .setPackage(app.getPackageName()),
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                serviceId = backend.open(phoneId, 1, unused, new LegacyListener(generation));
                if (serviceId < 0) throw new IllegalStateException("Native open failed");
                nativeRegistration = backend.getRegistration(phoneId);
                if (nativeRegistration == null) throw new IllegalStateException("Native registration unavailable");
                registrationCallback = new RegistrationListener(generation);
                nativeRegistration.addRegistrationCallback(registrationCallback);
                incomingTarget = this;
                // ImsSmsImpl is owned by the Samsung backend and must be reattached
                // after radio/backend recovery; onReady() is not called a second time.
                handler.post(feature.sms::attach);
                Log.i(TAG, "Native voice context opened; phoneId=" + phoneId
                        + " subscription=" + subscription + " epoch=" + epoch);
            }
            if (!registered && pendingRegistration != null && hasNormalVoiceRegistration()) {
                registered = true;
                restoreNativeVoiceFromRegistration();
                registration.onRegistered(pendingRegistration);
                pendingRegistration = null;
            }
            // The legacy capability callback can arrive after the typed
            // onRegistered callback during SIM hot-swap and clear nativeVoice.
            // Reconcile it from Samsung's current strict normal-mmtel snapshot;
            // deregistration still clears registered before this can qualify.
            if (registered && !nativeVoice && hasNormalVoiceRegistration()) {
                restoreNativeVoiceFromRegistration();
            }
            publish();
        } catch (Exception e) {
            Log.e(TAG, "Backend unavailable", e); reset("Backend initialization failed");
        }
        if (!scheduled) { scheduled = true; handler.postDelayed(retry, 2000); }
    }
    boolean current(long generation) { return !disposed && backend != null && epoch == generation; }
    boolean activePair() {
        return GoogleModernImsService.isSingleActivePair(app, phoneId, subscription);
    }
    void setVoiceEnabled(boolean enabled) {
        voiceEnabled = enabled;
        retainEnablement();
        Log.i(TAG, "BQ3: Voice enablement remembered=" + enabled + " phoneId=" + phoneId);
    }
    void setSmsEnabled(boolean enabled) {
        smsEnabled = enabled;
        retainEnablement();
    }
    private void retainEnablement() {
        synchronized (ModernVoiceContext.class) {
            retainedPhoneId = phoneId;
            retainedSubscription = subscription;
            retainedVoiceEnabled = voiceEnabled;
            retainedSmsEnabled = smsEnabled;
        }
    }
    void requireBackend() {
        ensureBackend();
        if (backend == null || serviceId < 0 || disposed) throw new IllegalStateException("Native voice backend unavailable");
    }
    boolean voiceAvailable() { return !disposed && backend != null && serviceId >= 0 && registered && nativeVoice && voiceEnabled; }
    boolean smsAvailable() {
        return !disposed && backend != null && serviceId >= 0 && registered
                && hasNormalSmsRegistration();
    }
    void publish() { if (feature != null) feature.publish(!disposed && backend != null && serviceId >= 0, voiceAvailable()); }
    static ImsReasonInfo reason(String message) { return new ImsReasonInfo(106, 0, message); }

    // The notifier may carry RCS/CMC registrations. Only a real normal cellular VoLTE profile qualifies.
    boolean hasNormalVoiceRegistration() {
        try {
            for (ImsRegistration r : ImsRegistry.getRegistrationManager().getRegistrationInfo()) {
                if (r.getPhoneId() == phoneId && r.hasVolteService() && r.getCurrentRat() != 18
                        && !r.getImsProfile().hasEmergencySupport() && r.getImsProfile().getCmcType() == 0) return true;
            }
        } catch (RuntimeException e) { Log.e(TAG, "Registration snapshot unavailable", e); }
        return false;
    }
    boolean hasNormalSmsRegistration() {
        try {
            for (ImsRegistration r : ImsRegistry.getRegistrationManager().getRegistrationInfo()) {
                if (r.getPhoneId() == phoneId && r.hasService("smsip") && r.getCurrentRat() != 18
                        && !r.getImsProfile().hasEmergencySupport()
                        && r.getImsProfile().getCmcType() == 0) return true;
            }
        } catch (RuntimeException e) { Log.e(TAG, "SMS registration snapshot unavailable", e); }
        return false;
    }
    private void restoreNativeVoiceFromRegistration() {
        if (nativeVoice) return;
        nativeVoice = true;
        Log.i(TAG, "BQ2: Voice capability reconciled from normal Samsung mmtel registration");
    }
    synchronized IImsCallSession outgoing(ImsCallProfile profile) throws RemoteException {
        requireBackend();
        if (!voiceAvailable() || profile == null || profile.mServiceType != 1 || profile.mCallType != 2)
            throw new RemoteException("BC2 normal cellular voice unavailable or unsupported profile");
        ModernCallRelay relay = new ModernCallRelay();
        IImsCallSession nativeSession;
        ModernCallRelay.CONSTRUCTION.set(relay);
        try { nativeSession = backend.createCallSession(serviceId, profile, null); }
        finally { ModernCallRelay.CONSTRUCTION.remove(); }
        try { return wrap(nativeSession, relay); }
        catch (RemoteException | RuntimeException e) {
            cleanupUnpublished(nativeSession, relay); throw new RemoteException("Native session publication failed");
        }
    }
    private ModernCallSession wrap(IImsCallSession nativeSession, ModernCallRelay relay) throws RemoteException {
        if (!(nativeSession instanceof ImsCallSessionImpl)) throw new RemoteException("Unexpected native session implementation");
        String id = nativeSession.getCallId();
        if (id == null || id.isEmpty() || sessions.containsKey(id)) throw new RemoteException("Invalid or duplicate native session identity");
        ModernCallSession result = new ModernCallSession(this, epoch, id, nativeSession, relay);
        if (relay.hasOverflowed()) throw new RemoteException("Native events overflowed before publication");
        sessions.put(id, result);
        // Also asks the native event listener to replay its cached pre-listener event.
        try { nativeSession.setListener(relay); }
        catch (RemoteException | RuntimeException e) { sessions.remove(id); throw e; }
        return result;
    }
    private void cleanupUnpublished(IImsCallSession session, ModernCallRelay relay) {
        relay.clear();
        if (session == null) return;
        try { session.terminate(501); } catch (Exception e) { Log.w(TAG, "Unpublished session termination failed", e); }
        try { if (session instanceof ImsCallSessionImpl) ((ImsCallSessionImpl) session).releaseSessionListeners(); session.close(); }
        catch (Exception e) { Log.w(TAG, "Unpublished session cleanup failed", e); }
    }
    /** Called before Samsung's optional legacy callback; returns true only for our owned service ID. */
    public static boolean onIncoming(int phone, int callId, Bundle extras) {
        ModernVoiceContext target = incomingTarget;
        if (target == null || phone != target.phoneId) return false;
        return target.incoming(callId, extras);
    }
    private boolean incoming(int callId, Bundle extras) {
        GoogleModernMmTelFeature notifyFeature = null;
        ModernCallSession notifySession = null;
        Bundle notifyExtras = null;
        synchronized (this) {
            if (disposed || backend == null || extras == null
                    || extras.getInt("android:imsServiceId", -1) != serviceId) return false;
            ModernCallRelay relay = new ModernCallRelay();
            IImsCallSession nativeSession = null;
            ModernCallSession published = null;
            try {
                IBinder identity = backend.getModernIncomingIdentity(callId);
                if (identity == null) return true; // Already-ended native notification.
                if (identity.equals(incoming.get(callId))) return true;
                ModernCallRelay.CONSTRUCTION.set(relay);
                try { nativeSession = backend.getPendingCallSession(serviceId, Integer.toString(callId)); }
                finally { ModernCallRelay.CONSTRUCTION.remove(); }
                ModernCallSession session = wrap(nativeSession, relay);
                published = session;
                incoming.put(callId, identity);
                ImsCallProfile profile = nativeSession.getCallProfile();
                boolean normalVoice = profile != null && profile.mServiceType == ImsCallProfile.SERVICE_TYPE_NORMAL
                        && profile.mCallType == ImsCallProfile.CALL_TYPE_VOICE;
                if (feature == null || !feature.listenerReady || !voiceAvailable() || !normalVoice) {
                    session.reject(504);
                    session.close();
                    Log.w(TAG, "Incoming call rejected: modern listener/voice unavailable");
                } else {
                    notifyFeature = feature;
                    notifySession = session;
                    notifyExtras = new Bundle(extras);
                }
            } catch (Exception e) {
                Log.e(TAG, "Incoming delivery failed", e);
                cleanupUnpublished(nativeSession, relay);
                if (published != null) published.close();
            }
        }
        // IImsMmTelListener.onIncomingCall is synchronous on Android 13. Telephony
        // immediately re-enters notifySession for its profile/state, and those calls
        // validate ownership under this monitor. Never hold it across the callback.
        if (notifySession != null) {
            try {
                notifyFeature.notifyIncomingCallSession(notifySession, notifyExtras);
                Log.i(TAG, "Incoming call delivered to Android; callId=" + callId);
            } catch (Exception e) {
                Log.e(TAG, "Incoming Android notification failed", e);
                try { notifySession.reject(504); } catch (Exception ignored) {}
                notifySession.close();
            }
        }
        return true;
    }
    synchronized void sessionClosed(ModernCallSession session) {
        if (sessions.get(session.id) == session) sessions.remove(session.id);
        // Tombstones contain actual native Binder identity, not only a reusable integer call ID.
    }
    void sessionOverflow(ModernCallSession session) {
        handler.post(() -> {
            synchronized (ModernVoiceContext.this) {
                if (sessions.get(session.id) == session) session.invalidate("Native event queue overflow");
            }
        });
    }
    synchronized void removeFeature(GoogleModernMmTelFeature removed) {
        if (feature != removed) return;
        removed.listenerReady = false;
        reset("Feature removed");
        feature = null;
        handler.removeCallbacks(retry); scheduled = false;
    }
    synchronized void dispose() {
        if (disposed) return;
        reset("Subscription/service removed"); disposed = true;
        if (feature != null) feature.publish(false, false);
        feature = null; handler.removeCallbacks(retry); scheduled = false;
    }
    private void reset(String cause) {
        ++epoch;
        if (incomingTarget == this) incomingTarget = null;
        if (feature != null) feature.sms.backendInvalidated(backend);
        registered = nativeVoice = false; pendingRegistration = null;
        publish();
        registration.onDeregistered(reason(cause));
        registration.onSubscriberAssociatedUriChanged(new Uri[0]);
        if (nativeRegistration != null && registrationCallback != null) {
            try { nativeRegistration.removeRegistrationCallback(registrationCallback); }
            catch (Exception e) { Log.w(TAG, "Registration detach failed", e); }
        }
        nativeRegistration = null; registrationCallback = null;
        for (ModernCallSession s : sessions.values().toArray(new ModernCallSession[0])) s.invalidate(cause);
        sessions.clear(); incoming.clear();
        if (backend != null && serviceId >= 0) {
            try { backend.close(serviceId); } catch (Exception e) { Log.w(TAG, "Native close failed", e); }
        }
        backend = null; serviceId = -1; publish();
    }
    private final class RegistrationListener extends IImsRegistrationCallback.Stub {
        final long generation;
        RegistrationListener(long generation) { this.generation = generation; }
        public void onRegistered(ImsRegistrationAttributes a) {
            handler.post(() -> {
            synchronized (ModernVoiceContext.this) {
                if (!current(generation)) return;
                pendingRegistration = a.getRegistrationTechnology() == 0 ? a : null;
                registered = pendingRegistration != null && hasNormalVoiceRegistration();
                if (registered) restoreNativeVoiceFromRegistration();
                publish();
                if (registered) registration.onRegistered(a);
                else registration.onDeregistered(reason("No normal cellular VoLTE registration"));
                publish();
            }
            });
        }
        public void onRegistering(ImsRegistrationAttributes a) {
            handler.post(() -> {
            synchronized (ModernVoiceContext.this) {
                if (!current(generation)) return;
                registered = nativeVoice = false; pendingRegistration = null; publish();
                if (a.getRegistrationTechnology() == 0) registration.onRegistering(a);
                else registration.onDeregistered(reason("Unsupported registration transport"));
            }
            });
        }
        public void onDeregistered(ImsReasonInfo reason) {
            handler.post(() -> {
            synchronized (ModernVoiceContext.this) {
                if (!current(generation)) return;
                registered = nativeVoice = false; pendingRegistration = null; publish(); registration.onDeregistered(reason);
                registration.onSubscriberAssociatedUriChanged(new Uri[0]);
            }
            });
        }
        public void onTechnologyChangeFailed(int tech, ImsReasonInfo reason) {
            handler.post(() -> {
            synchronized (ModernVoiceContext.this) { if (current(generation)) registration.onTechnologyChangeFailed(tech, reason); }
            });
        }
        public void onSubscriberAssociatedUriChanged(Uri[] uris) {
            final Uri[] copy = uris == null ? new Uri[0] : uris.clone();
            handler.post(() -> {
                synchronized (ModernVoiceContext.this) { if (current(generation) && registered) registration.onSubscriberAssociatedUriChanged(copy); }
            });
        }
    }
    private final class LegacyListener extends IImsRegistrationListener.Stub {
        final long generation;
        LegacyListener(long generation) { this.generation = generation; }
        public void registrationFeatureCapabilityChanged(int serviceClass, int[] enabled, int[] disabled) {
            final int[] copy = enabled == null ? new int[0] : enabled.clone();
            handler.post(() -> {
            synchronized (ModernVoiceContext.this) {
                if (!current(generation)) return;
                nativeVoice = false;
                if (serviceClass == 1) for (int value : copy) if (value == 0) nativeVoice = true;
                publish();
            }
            });
        }
        public void voiceMessageCountUpdate(int count) {
            handler.post(() -> {
            synchronized (ModernVoiceContext.this) { if (current(generation) && feature != null && feature.listenerReady) feature.notifyVoiceMessageCountUpdate(count); }
            });
        }
        // Registration state is exclusively owned by the typed notifier adapter above.
        public void registrationConnected() {}
        public void registrationProgressing() {}
        public void registrationConnectedWithRadioTech(int tech) {}
        public void registrationProgressingWithRadioTech(int tech) {}
        public void registrationDisconnected(ImsReasonInfo reason) {}
        public void registrationResumed() {}
        public void registrationSuspended() {}
        public void registrationServiceCapabilityChanged(int a, int b) {}
        public void registrationAssociatedUriChanged(Uri[] uris) {}
        public void registrationChangeFailed(int tech, ImsReasonInfo reason) {}
    }
}
