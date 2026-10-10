/* SPDX-License-Identifier: Apache-2.0 */
package com.android.internal.telephony;

import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.TrafficStats;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.HwBinder;
import android.os.IHwBinder;
import android.os.RemoteException;
import android.os.SystemProperties;
import android.provider.Settings;
import android.telephony.SubscriptionInfo;
import android.telephony.SubscriptionManager;
import android.telephony.TelephonyManager;

import com.android.telephony.Rlog;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReferenceArray;

/**
 * Product-configured owner for the legacy Samsung base-2.0 radio callbacks used by m11q.
 *
 * <p>This class does not issue radio requests or mutate telephony state. It only answers the
 * reviewed synchronous callbacks, and fails closed whenever subscription identity changes or the
 * vendor service connection becomes stale.</p>
 */
public final class M11SehRadioBridge {
    private static final String TAG = "M11SehRadioBridge";
    private static final String ENABLE_PROPERTY = "ro.m11q.ims_seh_apn_bridge";
    private static final String IWLAN_MODE_PROPERTY = "ro.telephony.iwlan_operation_mode";
    private static final String DEVICE = "m11q";
    private static final String SERVICE_PREFIX = "slot";
    private static final String APN_URI_PREFIX =
            "content://telephony/carriers/sim_apn_list/filtered/subId/";
    private static final String[] APN_PROJECTION = {
            "apn", "protocol", "user", "password", "authtype", "roaming_protocol"
    };

    private static final int SLOT_COUNT = 2;
    private static final long INITIAL_RETRY_MILLIS = 250L;
    private static final long MAX_RETRY_MILLIS = 10_000L;
    private static final int PACKET_ERROR_UNSUPPORTED = 44;

    /* Reviewed stock base-2.0 ABI hashes. Each callback chain is interface then IBase. */
    private static final byte[] RESPONSE_HASH = hex(
            "939e27ee9b2db9d044f3425f6dbde5896bc561155126551f257a0e06de01e092");
    private static final byte[] INDICATION_HASH = hex(
            "780fa0f585c25754cc6343bf00dee5157efcf6f8526bc1797aacb87e8d375fa4");
    private static final byte[] BASE_HASH = hex(
            "ec7fd79ed02dfa85bc499426adae3ebe23ef0524f3cd6957139324b83b18ca4c");
    private static final byte[][] RESPONSE_HASH_CHAIN = {RESPONSE_HASH, BASE_HASH};
    private static final byte[][] INDICATION_HASH_CHAIN = {INDICATION_HASH, BASE_HASH};

    private static final Object OWNER_LOCK = new Object();
    private static final M11SehRadioBridge[] OWNERS = new M11SehRadioBridge[SLOT_COUNT];
    private static final AtomicReferenceArray<M11SehApnPolicy.Snapshot> SNAPSHOTS =
            new AtomicReferenceArray<>(SLOT_COUNT);

    private final RIL mOwner;
    private final Context mContext;
    private final int mPhoneId;
    private final HandlerThread mThread;
    private final Handler mHandler;

    /* Accessed by Binder callback threads; these references deliberately remain strong. */
    private volatile long mActiveEpoch;
    private volatile IHwBinder mService;
    private volatile IHwBinder.DeathRecipient mDeathRecipient;
    private volatile M11SehRadioTransport mTransport;

    /* Handler-thread state. */
    private long mNextEpoch;
    private int mRetryExponent;
    private int mRetryAttempts;
    private boolean mConnectScheduled;
    private final AtomicBoolean mLoggedAllocateCid = new AtomicBoolean();
    private final AtomicBoolean mLoggedReleaseCid = new AtomicBoolean();
    private final AtomicBoolean mLoggedUnexpectedResponse = new AtomicBoolean();

    private M11SehRadioBridge(RIL owner, Context context, int phoneId) {
        mOwner = owner;
        Context applicationContext = context.getApplicationContext();
        mContext = applicationContext != null ? applicationContext : context;
        mPhoneId = phoneId;
        mThread = new HandlerThread(TAG + "-" + phoneId);
        mThread.start();
        mHandler = new Handler(mThread.getLooper());
    }

    /** Starts the one permitted owner without affecting configurations where the gate is false. */
    public static void maybeStart(RIL owner, Context context, int phoneId) {
        if (owner == null || context == null || !isEnabledForPhone(phoneId)) {
            return;
        }

        synchronized (OWNER_LOCK) {
            M11SehRadioBridge existing = OWNERS[phoneId];
            if (existing != null) {
                if (existing.mOwner != owner) {
                    Rlog.e(TAG, "Refusing a second owner for phone " + phoneId);
                }
                return;
            }
            M11SehRadioBridge bridge = new M11SehRadioBridge(owner, context, phoneId);
            OWNERS[phoneId] = bridge;
            bridge.mHandler.post(() -> bridge.scheduleConnect(0L));
        }
    }

    public static boolean isEnabledForPhone(int phoneId) {
        return M11SehApnPolicy.supportedPhone(phoneId) && DEVICE.equals(Build.DEVICE)
                && SystemProperties.getBoolean(ENABLE_PROPERTY, false)
                && "legacy".equals(SystemProperties.get(IWLAN_MODE_PROPERTY));
    }

    /** Publishes immutable DataProfileManager state; no profile field is logged or exported. */
    public static void publishSnapshot(M11SehApnPolicy.Snapshot snapshot) {
        if (snapshot == null || snapshot.phoneId < 0 || snapshot.phoneId >= SLOT_COUNT) return;
        SNAPSHOTS.set(snapshot.phoneId, snapshot);
    }

    private void scheduleConnect(long delayMillis) {
        if (mConnectScheduled) return;
        mConnectScheduled = true;
        mHandler.postDelayed(() -> {
            mConnectScheduled = false;
            connect();
        }, delayMillis);
    }

    private void connect() {
        if (mService != null) return;

        final long epoch = ++mNextEpoch;
        IHwBinder candidate = null;
        IHwBinder.DeathRecipient deathRecipient = null;
        try {
            candidate = HwBinder.getService(M11SehRadioTransport.RADIO,
                    SERVICE_PREFIX + (mPhoneId + 1), false);
            final IHwBinder serviceForEpoch = candidate;
            deathRecipient = cookie -> {
                // Invalidate Binder callbacks immediately; handler cleanup may run later.
                if (cookie == epoch && mActiveEpoch == epoch && mService == serviceForEpoch) {
                    mActiveEpoch = 0L;
                    mHandler.post(() -> handleDeath(epoch, serviceForEpoch, cookie));
                }
            };
            if (!candidate.linkToDeath(deathRecipient, epoch)) {
                throw new RemoteException("linkToDeath rejected");
            }

            M11SehRadioTransport transport = new M11SehRadioTransport(
                    new EpochBackend(epoch), RESPONSE_HASH_CHAIN, INDICATION_HASH_CHAIN);
            mService = candidate;
            mDeathRecipient = deathRecipient;
            mTransport = transport;
            mActiveEpoch = epoch;
            transport.register(candidate);
            mRetryExponent = 0;
            mRetryAttempts = 0;
            Rlog.i(TAG, "Registered reviewed SEH callbacks for phone " + mPhoneId);
        } catch (Exception e) {
            clearConnection(epoch, candidate, deathRecipient);
            if (shouldLogRetry()) {
                Rlog.w(TAG, "SEH callback registration unavailable for phone " + mPhoneId);
            }
            retry();
        }
    }

    private void handleDeath(long epoch, IHwBinder service, long cookie) {
        if (cookie != epoch || mActiveEpoch != 0L || mService != service) return;
        Rlog.w(TAG, "SEH service died for phone " + mPhoneId);
        clearConnection(epoch, service, mDeathRecipient);
        retry();
    }

    private void clearConnection(long epoch, IHwBinder service,
            IHwBinder.DeathRecipient deathRecipient) {
        if ((mActiveEpoch == epoch || mActiveEpoch == 0L)
                && (mService == service || mService == null)) {
            mActiveEpoch = 0L;
            mService = null;
            mDeathRecipient = null;
            mTransport = null;
        }
        if (service != null && deathRecipient != null) {
            try {
                service.unlinkToDeath(deathRecipient);
            } catch (RuntimeException ignored) {
                // A dead service is already detached.
            }
        }
    }

    private void retry() {
        long delay = INITIAL_RETRY_MILLIS << Math.min(mRetryExponent, 16);
        if (delay < MAX_RETRY_MILLIS) mRetryExponent++;
        scheduleConnect(Math.min(delay, MAX_RETRY_MILLIS));
    }

    private boolean shouldLogRetry() {
        int attempt = ++mRetryAttempts;
        return attempt == 1 || (attempt & (attempt - 1)) == 0;
    }

    private boolean isCurrent(long epoch) {
        return epoch != 0L && mActiveEpoch == epoch && mService != null && mTransport != null;
    }

    private Identity currentIdentity() {
        try {
            SubscriptionManager subscriptions = SubscriptionManager.from(mContext);
            List<SubscriptionInfo> active = subscriptions.getActiveSubscriptionInfoList();
            if (active == null || active.size() != 1) return null;
            SubscriptionInfo info = active.get(0);
            int subId = info.getSubscriptionId();
            if (info.getSimSlotIndex() != mPhoneId
                    || SubscriptionManager.getPhoneId(subId) != mPhoneId
                    || !SubscriptionManager.isValidSubscriptionId(subId)) return null;
            TelephonyManager telephony = mContext.getSystemService(TelephonyManager.class);
            if (telephony == null) return null;
            String operator = telephony.createForSubscriptionId(subId).getSimOperator();
            return M11SehApnPolicy.validOperator(operator) ? new Identity(subId, operator) : null;
        } catch (RuntimeException e) {
            Rlog.w(TAG, "Unable to verify active subscription identity");
            return null;
        }
    }

    private M11SehApnPolicy.Profile readApn(long epoch, String selection) {
        if (!isCurrent(epoch)) return M11SehApnPolicy.EMPTY;
        Identity before = currentIdentity();
        if (before == null) return M11SehApnPolicy.EMPTY;

        M11SehApnPolicy.Profile profile = M11SehApnPolicy.EMPTY;
        boolean zeroRows;
        ContentResolver resolver = mContext.getContentResolver();
        Uri uri = Uri.parse(APN_URI_PREFIX + before.subId);
        try (Cursor cursor = resolver.query(uri, APN_PROJECTION, selection, null, null)) {
            if (cursor == null) return M11SehApnPolicy.EMPTY;
            zeroRows = !cursor.moveToFirst();
            while (!zeroRows) {
                String apn = stringAt(cursor, 0);
                if ("cinet.spcs".equals(apn) || "cdma".equals(apn)) {
                    if (!cursor.moveToNext()) break;
                    continue;
                }
                String authentication = cursor.isNull(4)
                        ? "" : Integer.toString(cursor.getInt(4));
                profile = new M11SehApnPolicy.Profile(apn,
                        stringAt(cursor, 1), stringAt(cursor, 5), stringAt(cursor, 2),
                        stringAt(cursor, 3), authentication);
                // Provider rows are the stock source of truth, including empty authentication.
                break;
            }
        } catch (RuntimeException e) {
            Rlog.w(TAG, "APN provider read failed");
            return M11SehApnPolicy.EMPTY;
        }
        // Cursor.close() can also race SIM removal/service death; recheck only after it finishes.
        if (!isCurrent(epoch) || !before.equals(currentIdentity())) return M11SehApnPolicy.EMPTY;
        if (zeroRows) profile = M11SehApnPolicy.fallback(SNAPSHOTS.get(mPhoneId), mPhoneId,
                before.subId, before.operator, selection, true);
        Rlog.i(TAG, "APN callback phone " + mPhoneId + ": "
                + (profile == M11SehApnPolicy.EMPTY ? "empty"
                        : zeroRows ? "immutable IMS snapshot" : "provider"));
        return profile;
    }

    private int readSetting(long epoch, String key, String table) {
        Identity before = currentIdentity();
        if (!isCurrent(epoch) || before == null || key == null || table == null) {
            return -1;
        }
        if ("allocateCid".equals(table)) {
            if (mLoggedAllocateCid.compareAndSet(false, true)) {
                Rlog.w(TAG, "allocateCid is unsupported");
            }
            return -1;
        }
        if ("releaseCid".equals(table)) {
            if (mLoggedReleaseCid.compareAndSet(false, true)) {
                Rlog.w(TAG, "releaseCid is unsupported");
            }
            return -1;
        }
        try {
            ContentResolver resolver = mContext.getContentResolver();
            final int value;
            if ("global".equals(table)) {
                value = Settings.Global.getInt(resolver, key, 0);
            } else if ("system".equals(table)) {
                value = Settings.System.getInt(resolver, key, 0);
            } else if ("secure".equals(table)) {
                value = Settings.Secure.getInt(resolver, key, 0);
            } else {
                return -1;
            }
            return isCurrent(epoch) && before.equals(currentIdentity()) ? value : -1;
        } catch (RuntimeException e) {
            Rlog.w(TAG, "Settings read failed");
        }
        return -1;
    }

    private M11SehRadioTransport.PacketUsage readPacketUsage(long epoch, String iface) {
        Identity before = currentIdentity();
        if (!isCurrent(epoch) || before == null || iface == null
                || !iface.startsWith("rmnet")) {
            return unsupportedPacketUsage();
        }
        try {
            long receiveBytes = TrafficStats.getRxBytes(iface);
            long transmitBytes = TrafficStats.getTxBytes(iface);
            if (!isCurrent(epoch) || !before.equals(currentIdentity())) {
                return unsupportedPacketUsage();
            }
            return new M11SehRadioTransport.PacketUsage(0, receiveBytes, transmitBytes);
        } catch (RuntimeException e) {
            Rlog.w(TAG, "TrafficStats read failed");
            return unsupportedPacketUsage();
        }
    }

    private static M11SehRadioTransport.PacketUsage unsupportedPacketUsage() {
        return new M11SehRadioTransport.PacketUsage(PACKET_ERROR_UNSUPPORTED, 0L, 0L);
    }

    private static String stringAt(Cursor cursor, int column) {
        String value = cursor.getString(column);
        return value == null ? "" : value;
    }

    private final class EpochBackend implements M11SehRadioTransport.Backend {
        private final long mEpoch;

        EpochBackend(long epoch) {
            mEpoch = epoch;
        }

        @Override public boolean current() {
            return isCurrent(mEpoch);
        }

        @Override public M11SehApnPolicy.Profile apn(String selection) {
            try {
                return readApn(mEpoch, selection);
            } catch (RuntimeException e) {
                Rlog.w(TAG, "APN callback failed closed");
                return M11SehApnPolicy.EMPTY;
            }
        }

        @Override public int setting(String key, String table) {
            try {
                return readSetting(mEpoch, key, table);
            } catch (RuntimeException e) {
                Rlog.w(TAG, "Settings callback failed closed");
                return -1;
            }
        }

        @Override public M11SehRadioTransport.PacketUsage packetUsage(String iface) {
            try {
                return readPacketUsage(mEpoch, iface);
            } catch (RuntimeException e) {
                Rlog.w(TAG, "Packet callback failed closed");
                return unsupportedPacketUsage();
            }
        }

        @Override public void ignoredIndication(int indicationType) {
            // Intentionally no radio ACK: stock SemRIL.sendAck() is empty.
        }

        @Override public void unexpectedResponse() {
            if (mLoggedUnexpectedResponse.compareAndSet(false, true)) {
                Rlog.w(TAG, "Ignoring unexpected SEH solicited response");
            }
        }
    }

    private static final class Identity {
        final int subId;
        final String operator;

        Identity(int subId, String operator) {
            this.subId = subId;
            this.operator = operator;
        }

        @Override public boolean equals(Object object) {
            if (!(object instanceof Identity)) return false;
            Identity other = (Identity) object;
            return subId == other.subId && operator.equals(other.operator);
        }

        @Override public int hashCode() {
            return 31 * subId + operator.hashCode();
        }
    }

    private static byte[] hex(String value) {
        if (value.length() != 64) throw new IllegalArgumentException("Expected SHA-256");
        byte[] result = new byte[32];
        for (int i = 0; i < result.length; i++) {
            int high = Character.digit(value.charAt(i * 2), 16);
            int low = Character.digit(value.charAt(i * 2 + 1), 16);
            if (high < 0 || low < 0) throw new IllegalArgumentException("Invalid hash");
            result[i] = (byte) ((high << 4) | low);
        }
        return result;
    }
}
