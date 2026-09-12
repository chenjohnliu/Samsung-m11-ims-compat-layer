package com.sec.internal.google;

import android.os.RemoteException;
import android.telephony.SmsManager;
import android.telephony.SmsMessage;
import android.telephony.ims.aidl.IImsSmsListener;
import android.telephony.ims.stub.ImsSmsImplBase;
import android.util.Log;
import com.sec.ims.ImsRegistration;
import com.sec.internal.ims.registry.ImsRegistry;

/** Single-active-SIM adapter from Android 13 ImsSmsImplBase to Samsung's stock SMS backend. */
public final class ModernSmsBridge extends ImsSmsImplBase {
    private final ModernVoiceContext owner;
    private volatile boolean ready;
    private volatile boolean disposed;
    private volatile GoogleImsService attachedBackend;

    private final IImsSmsListener samsungListener = new IImsSmsListener.Stub() {
        @Override public void onSendSmsResult(int token, int messageRef, int status,
                int reason, int networkErrorCode) {
            if (!callbackCurrent()) return;
            try {
                if (status == SEND_STATUS_OK) onSendSmsResultSuccess(token, messageRef);
                else onSendSmsResultError(token, messageRef, status, reason, networkErrorCode);
            } catch (RuntimeException e) {
                Log.e(ModernVoiceContext.TAG, "SMS send result delivery failed", e);
            }
        }

        @Override public void onSmsStatusReportReceived(int token, String format, byte[] pdu) {
            if (!callbackCurrent()) return;
            try { ModernSmsBridge.this.onSmsStatusReportReceived(token, format, pdu); }
            catch (RuntimeException e) {
                Log.e(ModernVoiceContext.TAG, "SMS status report delivery failed", e);
            }
        }

        @Override public void onSmsReceived(int token, String format, byte[] pdu) {
            if (!callbackCurrent()) return;
            try { ModernSmsBridge.this.onSmsReceived(token, format, pdu); }
            catch (RuntimeException e) {
                Log.e(ModernVoiceContext.TAG, "Incoming SMS delivery failed", e);
            }
        }
    };

    ModernSmsBridge(ModernVoiceContext owner) { this.owner = owner; }

    private boolean supportsPhone() {
        return (owner.phoneId == 0 || owner.phoneId == 1) && owner.activePair();
    }

    boolean available() {
        return supportsPhone() && ready && !disposed && attachedBackend != null
                && owner.smsEnabled && owner.smsAvailable();
    }

    private boolean callbackCurrent() {
        synchronized (owner) {
            return ready && !disposed && attachedBackend != null
                    && attachedBackend == owner.backend && supportsPhone();
        }
    }

    private GoogleImsService requireSmsBackend() {
        synchronized (owner) {
            owner.requireBackend();
            if (!available()) throw new IllegalStateException("IMS SMS unavailable for phoneId="
                    + owner.phoneId);
            return attachedBackend;
        }
    }

    @Override public void onReady() {
        synchronized (owner) {
            if (disposed) return;
            ready = true;
            if (!supportsPhone()) {
                owner.publish();
                return;
            }
            owner.ensureBackend();
        }
        attach();
    }

    void attach() {
        GoogleImsService backend;
        synchronized (owner) {
            if (!supportsPhone() || !ready || disposed || owner.backend == null) return;
            backend = owner.backend;
            if (attachedBackend == backend) {
                owner.publish();
                return;
            }
        }
        try {
            backend.setSmsListener(owner.phoneId, samsungListener);
            backend.onSmsReady(owner.phoneId);
            synchronized (owner) {
                if (!disposed && owner.backend == backend) attachedBackend = backend;
                owner.publish();
            }
            Log.i(ModernVoiceContext.TAG, "Samsung IMS SMS backend attached; phoneId="
                    + owner.phoneId);
        } catch (RemoteException | RuntimeException e) {
            Log.e(ModernVoiceContext.TAG, "Samsung IMS SMS backend unavailable", e);
            synchronized (owner) {
                if (attachedBackend == backend) attachedBackend = null;
                owner.publish();
            }
        }
    }

    void backendInvalidated(GoogleImsService staleBackend) {
        synchronized (owner) {
            if (attachedBackend == staleBackend) attachedBackend = null;
        }
    }

    void dispose() {
        GoogleImsService backend;
        synchronized (owner) {
            disposed = true;
            ready = false;
            backend = attachedBackend;
            attachedBackend = null;
        }
        if (backend != null) {
            try { backend.setSmsListener(owner.phoneId, null); }
            catch (Exception e) { Log.w(ModernVoiceContext.TAG, "SMS listener detach failed", e); }
        }
    }

    @Override public String getSmsFormat() { return SmsMessage.FORMAT_3GPP; }

    private static String scaHex(String address) {
        if (address == null) return null;
        String raw = address.trim();
        int scheme = raw.indexOf(':');
        if (scheme >= 0 && (raw.regionMatches(true, 0, "sip:", 0, 4)
                || raw.regionMatches(true, 0, "tel:", 0, 4))) raw = raw.substring(scheme + 1);
        int end = raw.length();
        int at = raw.indexOf('@');
        int semicolon = raw.indexOf(';');
        int comma = raw.indexOf(',');
        if (at >= 0 && at < end) end = at;
        if (semicolon >= 0 && semicolon < end) end = semicolon;
        if (comma >= 0 && comma < end) end = comma;
        raw = raw.substring(0, end).trim();
        if (raw.length() >= 2
                && ((raw.charAt(0) == '"' && raw.charAt(raw.length() - 1) == '"')
                || (raw.charAt(0) == '\'' && raw.charAt(raw.length() - 1) == '\''))) {
            raw = raw.substring(1, raw.length() - 1).trim();
        }
        boolean international = raw.startsWith("+");
        StringBuilder digits = new StringBuilder();
        for (int i = 0; i < raw.length(); i++) {
            char value = raw.charAt(i);
            if (value >= '0' && value <= '9') digits.append(value);
        }
        if (digits.length() < 3 || digits.length() > 20) return null;
        StringBuilder hex = new StringBuilder();
        int bytes = 1 + (digits.length() + 1) / 2;
        hex.append(String.format("%02X%02X", bytes, international ? 0x91 : 0x81));
        for (int i = 0; i < digits.length(); i += 2) {
            char first = digits.charAt(i);
            char second = i + 1 < digits.length() ? digits.charAt(i + 1) : 'F';
            hex.append(second).append(first);
        }
        return hex.toString();
    }

    private String simSmsc() {
        try {
            String encoded = scaHex(SmsManager.getSmsManagerForSubscriptionId(
                    owner.subscription).getSmscAddress());
            if (encoded != null) Log.i(ModernVoiceContext.TAG,
                    "SMSC resolved from active subscription; phoneId=" + owner.phoneId);
            return encoded;
        } catch (RuntimeException e) {
            Log.w(ModernVoiceContext.TAG, "Active-subscription SMSC lookup failed; phoneId="
                    + owner.phoneId, e);
            return null;
        }
    }

    private String profileSmsc() {
        try {
            for (ImsRegistration registration
                    : ImsRegistry.getRegistrationManager().getRegistrationInfo()) {
                if (registration.getPhoneId() != owner.phoneId
                        || !registration.hasService("smsip")
                        || registration.getCurrentRat() == 18
                        || registration.getImsProfile().hasEmergencySupport()
                        || registration.getImsProfile().getCmcType() != 0) continue;
                String encoded = scaHex(registration.getImsProfile().getSmsPsi());
                if (encoded != null) {
                    Log.i(ModernVoiceContext.TAG, "SMSC resolved from Samsung IMS profile");
                    return encoded;
                }
            }
        } catch (RuntimeException e) {
            Log.w(ModernVoiceContext.TAG, "Samsung IMS profile SMSC lookup failed", e);
        }
        return null;
    }

    private String resolveSmsc(String supplied) {
        if (supplied != null && supplied.length() > 2 && !"00".equalsIgnoreCase(supplied)) {
            Log.i(ModernVoiceContext.TAG, "SMSC supplied by Android framework");
            return supplied;
        }
        String encoded = simSmsc();
        if (encoded == null) encoded = profileSmsc();
        if (encoded == null) Log.e(ModernVoiceContext.TAG,
                "Active-subscription SMSC unavailable; phoneId=" + owner.phoneId);
        return encoded;
    }

    @Override public void sendSms(int token, int messageRef, String format, String smsc,
            boolean isRetry, byte[] pdu) {
        if (!SmsMessage.FORMAT_3GPP.equals(format) || pdu == null) {
            onSendSmsResultError(token, messageRef, SEND_STATUS_ERROR,
                    SmsManager.RESULT_ERROR_GENERIC_FAILURE, RESULT_NO_NETWORK_ERROR);
            return;
        }
        try {
            GoogleImsService backend = requireSmsBackend();
            String samsungSmsc = resolveSmsc(smsc);
            if (samsungSmsc == null) {
                onSendSmsResultError(token, messageRef, SEND_STATUS_ERROR,
                        SmsManager.RESULT_INVALID_SMSC_ADDRESS, RESULT_NO_NETWORK_ERROR);
                return;
            }
            backend.setRetryCount(owner.phoneId, token, isRetry ? 1 : 0);
            backend.sendSms(owner.phoneId, token, messageRef, format, samsungSmsc, isRetry, pdu);
            Log.i(ModernVoiceContext.TAG, "Samsung IMS SMS delegated; token=" + token
                    + " retry=" + isRetry + " bytes=" + pdu.length);
        } catch (RemoteException | RuntimeException e) {
            Log.e(ModernVoiceContext.TAG, "Samsung IMS SMS send failed", e);
            onSendSmsResultError(token, messageRef, SEND_STATUS_ERROR,
                    SmsManager.RESULT_ERROR_GENERIC_FAILURE, RESULT_NO_NETWORK_ERROR);
        }
    }

    @Override public void acknowledgeSms(int token, int messageRef, int result) {
        try { requireSmsBackend().acknowledgeSms(
                owner.phoneId, token, messageRef, result); }
        catch (RemoteException | RuntimeException e) {
            Log.e(ModernVoiceContext.TAG, "Samsung IMS SMS acknowledge failed", e);
        }
    }

    @Override public void acknowledgeSmsReport(int token, int messageRef, int result) {
        try { requireSmsBackend().acknowledgeSmsReport(
                owner.phoneId, token, messageRef, result); }
        catch (RemoteException | RuntimeException e) {
            Log.e(ModernVoiceContext.TAG, "Samsung IMS SMS report acknowledge failed", e);
        }
    }
}
