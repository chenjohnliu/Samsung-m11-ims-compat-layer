package com.android.internal.telephony;

import android.content.ContentResolver;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.HwBinder;
import android.os.HwBlob;
import android.os.HwParcel;
import android.os.IHwBinder;
import android.os.IHwInterface;
import android.os.SystemProperties;
import android.provider.Settings;
import android.telephony.SubscriptionInfo;
import android.telephony.SubscriptionManager;
import android.telephony.TelephonyManager;
import android.telephony.data.ApnSetting;
import android.telephony.data.DataProfile;
import com.android.telephony.Rlog;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class M11SehBridgeHostHarness {
    private static final String SELECTION = M11SehApnPolicy.IMS_SELECTION;
    private static final byte[] RESPONSE_HASH = hex(
            "939e27ee9b2db9d044f3425f6dbde5896bc561155126551f257a0e06de01e092");
    private static final byte[] INDICATION_HASH = hex(
            "780fa0f585c25754cc6343bf00dee5157efcf6f8526bc1797aacb87e8d375fa4");
    private static final byte[] BASE_HASH = hex(
            "ec7fd79ed02dfa85bc499426adae3ebe23ef0524f3cd6957139324b83b18ca4c");
    private static int tests;
    private static State state;

    private interface CheckedRunnable { void run() throws Exception; }

    public static void main(String[] args) throws Exception {
        run("boot gate and one owner", M11SehBridgeHostHarness::testBootGateAndOwner);
        run("registration service and reviewed hashes", M11SehBridgeHostHarness::testRegistrationHashes);
        run("settings defaults CID and no writes", M11SehBridgeHostHarness::testSettings);
        run("provider precedence projection and fields", M11SehBridgeHostHarness::testProviderPrecedence);
        run("provider zero-row fallback only", M11SehBridgeHostHarness::testFallbackScope);
        run("all carriers preserve provider and identity boundary", M11SehBridgeHostHarness::testAllCarriers);
        run("provider null and exception fail closed", M11SehBridgeHostHarness::testProviderFailures);
        run("changed identity and close failures fail closed",
                M11SehBridgeHostHarness::testChangedIdentityAndClose);
        run("profile publisher scope and stale clearing", M11SehBridgeHostHarness::testPublisher);
        run("death invalidates stale epoch and retries", M11SehBridgeHostHarness::testDeathRetry);
        run("SIM2 registration provider and snapshot isolation", M11SehBridgeHostHarness::testSecondSlot);
        System.out.println("PASS: " + tests + " M11 SEH bridge host tests");
    }

    private static void testBootGateAndOwner() {
        Handler.clear();
        HandlerThread.resetStarts();
        HwBinder.resetServiceRegistry();
        SystemProperties.clear();
        Rlog.clear();
        Settings.reset();
        Build.DEVICE = "m11q";
        SystemProperties.set("ro.telephony.iwlan_operation_mode", "legacy");

        FakeResolver resolver = new FakeResolver();
        SubscriptionManager subscriptions = new SubscriptionManager();
        subscriptions.setActive(new SubscriptionInfo(7, 0));
        TelephonyManager telephony = new TelephonyManager();
        telephony.setSimOperator(7, "46697");
        FakeContext context = new FakeContext(resolver, subscriptions, telephony);
        RecordingService service = new RecordingService();
        HwBinder.setService(service);

        M11SehRadioBridge.maybeStart(new RIL(), context, 0);
        assertEquals("gate-off lookup", 0, HwBinder.lookupCount());
        assertEquals("gate-off thread", 0, HandlerThread.starts());
        assertEquals("gate-off tasks", 0, Handler.pending());

        SystemProperties.set("ro.m11q.ims_seh_apn_bridge", "true");
        RIL owner = new RIL();
        M11SehRadioBridge.maybeStart(owner, context, 0);
        Handler.runAll();
        assertEquals("one bridge thread", 1, HandlerThread.starts());
        assertEquals("one lookup", 1, HwBinder.lookupCount());
        assertEquals("one registration", 1, service.registrations);

        M11SehRadioBridge.maybeStart(new RIL(), context, 0);
        Handler.runAll();
        assertEquals("duplicate has no thread", 1, HandlerThread.starts());
        assertEquals("duplicate has no lookup", 1, HwBinder.lookupCount());
        assertTrue("duplicate rejected", containsLog("second owner"));
        state = new State(context, resolver, subscriptions, telephony, service);
    }

    private static void testRegistrationHashes() throws Exception {
        assertEquals("service descriptor", M11SehRadioTransport.RADIO,
                HwBinder.lastDescriptor());
        assertEquals("service instance", "slot1", HwBinder.lastInstance());
        assertFalse("nonblocking service lookup", HwBinder.lastRetry());
        assertNotNull("response callback", state.service.response);
        assertNotNull("indication callback", state.service.indication);
        assertHashChain(state.service.response, RESPONSE_HASH);
        assertHashChain(state.service.indication, INDICATION_HASH);
    }

    private static void testSettings() throws Exception {
        Settings.reset();
        assertEquals("missing global defaults zero", 0,
                setting(state.service.indication, "missing", "global"));
        Settings.seed("system", "wifi_call_enable1", 17);
        assertEquals("system value", 17,
                setting(state.service.indication, "wifi_call_enable1", "system"));
        int reads = Settings.reads();
        assertEquals("allocate unsupported", -1,
                setting(state.service.indication, "ignored", "allocateCid"));
        assertEquals("release unsupported", -1,
                setting(state.service.indication, "ignored", "releaseCid"));
        assertEquals("CID does not read settings", reads, Settings.reads());
        assertEquals("settings do not mutate provider", 0, state.resolver.mutations);
    }

    private static void testProviderPrecedence() throws Exception {
        state.resolver.mode = FakeResolver.Mode.ROWS;
        state.resolver.rows = new String[][] {
                {"ims-live", "IPV4V6", "alice", "secret", null, "IP"}
        };
        M11SehApnPolicy.Profile cached = new M11SehApnPolicy.Profile(
                "ims-cache", "IP", "IP", "", "", "0");
        M11SehRadioBridge.publishSnapshot(
                new M11SehApnPolicy.Snapshot(0, 7, "46697", cached));
        HwBlob profile = apn(state.service.indication, SELECTION);
        assertArrayEquals("provider profile", new String[] {
                "ims-live", "IPV4V6", "IP", "alice", "secret", ""
        }, profileFields(profile));
        assertEquals("provider URI",
                "content://telephony/carriers/sim_apn_list/filtered/subId/7",
                state.resolver.lastUri);
        assertArrayEquals("projection unchanged", new String[] {
                "apn", "protocol", "user", "password", "authtype", "roaming_protocol"
        }, state.resolver.lastProjection);
        assertEquals("selection unchanged", SELECTION, state.resolver.lastSelection);
        assertEquals("selection args null", null, state.resolver.lastSelectionArgs);
        assertEquals("sort null", null, state.resolver.lastSortOrder);
    }

    private static void testFallbackScope() throws Exception {
        M11SehApnPolicy.Profile cached = new M11SehApnPolicy.Profile(
                "ims-cache", "IPV4V6", "IPV4V6", "u", "p", "0");
        M11SehRadioBridge.publishSnapshot(
                new M11SehApnPolicy.Snapshot(0, 7, "46697", cached));
        state.resolver.mode = FakeResolver.Mode.EMPTY;
        assertArrayEquals("zero rows use sole cached profile", cached.wireFields(),
                profileFields(apn(state.service.indication, SELECTION)));
        assertEmpty("nonexact selection cannot fall back",
                apn(state.service.indication, SELECTION + " "));
    }

    private static void testAllCarriers() throws Exception {
        M11SehApnPolicy.Profile cached = new M11SehApnPolicy.Profile(
                "ims-carrier", "IPV4V6", "IPV4V6", "", "", "0");
        for (String operator : new String[] {"46601", "46605", "46689", "46692", "46697", "310260"}) {
            state.telephony.setSimOperator(7, operator);
            M11SehRadioBridge.publishSnapshot(new M11SehApnPolicy.Snapshot(0, 7, operator, cached));
            state.resolver.mode = FakeResolver.Mode.EMPTY;
            assertArrayEquals("carrier fallback " + operator, cached.wireFields(),
                    profileFields(apn(state.service.indication, SELECTION)));
            assertTrue("valid operator " + operator, M11SehApnPolicy.validOperator(operator));
            assertTrue("stale carrier snapshot " + operator,
                    M11SehApnPolicy.fallback(new M11SehApnPolicy.Snapshot(0, 7, "00000", cached),
                            0, 7, operator, SELECTION, true) == M11SehApnPolicy.EMPTY);
        }
        for (String invalid : new String[] {"", "4669", "4669700", "abcde"}) {
            state.telephony.setSimOperator(7, invalid);
            assertEmpty("invalid operator " + invalid, apn(state.service.indication, SELECTION));
        }
        assertFalse("null operator", M11SehApnPolicy.validOperator(null));
        state.telephony.setSimOperator(7, "46697");
    }

    private static void testProviderFailures() throws Exception {
        state.resolver.mode = FakeResolver.Mode.NULL;
        assertEmpty("null cursor", apn(state.service.indication, SELECTION));
        state.resolver.mode = FakeResolver.Mode.THROW;
        assertEmpty("query exception", apn(state.service.indication, SELECTION));
        assertEquals("provider still never mutated", 0, state.resolver.mutations);
    }

    private static void testChangedIdentityAndClose() throws Exception {
        state.resolver.mode = FakeResolver.Mode.ROWS;
        state.resolver.rows = new String[][] {
                {"ims-race", "IPV4V6", "", "", "0", "IPV4V6"}
        };
        state.resolver.afterQuery = () -> state.telephony.setSimOperator(7, "46692");
        assertEmpty("operator changed after query",
                apn(state.service.indication, SELECTION));
        state.resolver.afterQuery = null;
        state.telephony.setSimOperator(7, "46697");

        int closes = state.resolver.closes;
        state.resolver.onClose = () -> state.telephony.setSimOperator(7, "46692");
        assertEmpty("operator changed during cursor close",
                apn(state.service.indication, SELECTION));
        assertEquals("cursor closed before identity rejection", closes + 1,
                state.resolver.closes);
        state.resolver.onClose = null;
        state.telephony.setSimOperator(7, "46697");

        state.resolver.throwOnClose = true;
        assertEmpty("cursor close exception", apn(state.service.indication, SELECTION));
        state.resolver.throwOnClose = false;
    }

    private static void testPublisher() throws Exception {
        Phone phone = new Phone(state.context, 0, 7);
        state.resolver.mode = FakeResolver.Mode.EMPTY;
        DataProfile valid = dataProfile("ims-published", ApnSetting.TYPE_IMS,
                true, true, 2, 1, "actual-user", "actual-password", 3);
        M11SehProfilePublisher.publish(phone, Arrays.asList(valid));
        assertArrayEquals("sole IMS publishes actual fields", new String[] {
                "ims-published", "IPV4V6", "IPV6", "actual-user", "actual-password", "3"
        }, profileFields(apn(state.service.indication, SELECTION)));

        DataProfile second = dataProfile("ims-second", ApnSetting.TYPE_IMS,
                true, true, 0, 0, "", "", 0);
        M11SehProfilePublisher.publish(phone, Arrays.asList(valid, second));
        assertEmpty("multiple IMS clears stale snapshot",
                apn(state.service.indication, SELECTION));

        M11SehProfilePublisher.publish(phone, Arrays.asList(dataProfile("ims-mixed",
                ApnSetting.TYPE_IMS | ApnSetting.TYPE_DEFAULT, true, true, 2, 2, "", "", 0)));
        assertEmpty("mixed APN type rejected", apn(state.service.indication, SELECTION));
        M11SehProfilePublisher.publish(phone, Arrays.asList(dataProfile("ims-disabled",
                ApnSetting.TYPE_IMS, false, true, 2, 2, "", "", 0)));
        assertEmpty("disabled APN rejected", apn(state.service.indication, SELECTION));
        M11SehProfilePublisher.publish(phone, Arrays.asList(dataProfile("ims-non-lte",
                ApnSetting.TYPE_IMS, true, false, 2, 2, "", "", 0)));
        assertEmpty("non-LTE APN rejected", apn(state.service.indication, SELECTION));

        SystemProperties.set("ro.m11q.ims_seh_apn_bridge", "false");
        Phone gateOff = new Phone(state.context, 0, 7);
        M11SehProfilePublisher.publish(gateOff, Arrays.asList(valid));
        assertEquals("gate false avoids phone context", 0, gateOff.contextReads());
        SystemProperties.set("ro.m11q.ims_seh_apn_bridge", "true");
    }

    private static void testDeathRetry() throws Exception {
        state.resolver.mode = FakeResolver.Mode.ROWS;
        state.resolver.rows = new String[][] {
                {"ims-live", "IPV4V6", "", "", "0", "IPV4V6"}
        };
        RecordingService replacement = new RecordingService();
        HwBinder.setService(replacement);
        HwBinder.failNextLookups(1);
        int queries = state.resolver.queries;
        int lookups = HwBinder.lookupCount();
        IHwBinder staleIndication = state.service.indication;
        state.service.die();

        assertEmpty("death synchronously invalidates old callback",
                apn(staleIndication, SELECTION));
        assertEquals("stale callback skips provider", queries, state.resolver.queries);
        Handler.runAll();
        assertEquals("one failed and one successful retry", lookups + 2,
                HwBinder.lookupCount());
        assertEquals("replacement registered", 1, replacement.registrations);
        assertArrayEquals("replacement callback active", state.resolver.rows[0],
                providerOrder(profileFields(apn(replacement.indication, SELECTION))));
        state.service = replacement;
    }

    private static int setting(IHwBinder indication, String key, String table) throws Exception {
        HwParcel request = request(M11SehRadioTransport.INDICATION);
        request.writeString(key);
        request.writeString(table);
        HwParcel reply = call(indication, 23, request);
        assertReply(reply);
        return reply.readInt32();
    }

    private static void testSecondSlot() throws Exception {
        assertTrue("SIM2 product scope", M11SehRadioBridge.isEnabledForPhone(1));
        assertFalse("invalid negative phone", M11SehRadioBridge.isEnabledForPhone(-1));
        assertFalse("invalid third phone", M11SehRadioBridge.isEnabledForPhone(2));
        RecordingService second = new RecordingService();
        HwBinder.setService(second);
        M11SehRadioBridge.maybeStart(new RIL(), state.context, 1);
        Handler.runAll();
        assertEquals("SIM2 service", "slot2", HwBinder.lastInstance());
        assertEquals("SIM2 registration", 1, second.registrations);
        assertHashChain(second.indication, INDICATION_HASH);
        int queries = state.resolver.queries;
        assertEmpty("inactive SIM2 no APN", apn(second.indication, SELECTION));
        assertEquals("inactive SIM2 skips provider", queries, state.resolver.queries);
        state.subscriptions.setActive(new SubscriptionInfo(9, 1));
        state.telephony.setSimOperator(9, "46697");
        assertEmpty("old SIM1 callback rejected after move", apn(state.service.indication, SELECTION));
        state.resolver.mode = FakeResolver.Mode.ROWS;
        state.resolver.rows = new String[][] {{"ims-slot2", "IPV4V6", "", "", "0", "IPV4V6"}};
        assertArrayEquals("SIM2 provider fields", state.resolver.rows[0],
                providerOrder(profileFields(apn(second.indication, SELECTION))));
        assertEquals("SIM2 uses its own subId",
                "content://telephony/carriers/sim_apn_list/filtered/subId/9", state.resolver.lastUri);
        state.resolver.mode = FakeResolver.Mode.EMPTY;
        M11SehProfilePublisher.publish(new Phone(state.context, 1, 9), Arrays.asList(
                dataProfile("ims-slot2-cache", ApnSetting.TYPE_IMS, true, true, 2, 2, "", "", 0)));
        assertEquals("SIM2 publisher fallback", "ims-slot2-cache",
                profileFields(apn(second.indication, SELECTION))[0]);
        M11SehApnPolicy.Profile profile = new M11SehApnPolicy.Profile("ims", "IP", "IP", "", "", "0");
        assertTrue("wrong slot snapshot rejected", M11SehApnPolicy.fallback(
                new M11SehApnPolicy.Snapshot(0, 9, "46697", profile), 1, 9, "46697",
                SELECTION, true) == M11SehApnPolicy.EMPTY);
        state.resolver.mode = FakeResolver.Mode.ROWS;
        state.resolver.afterQuery = () -> state.subscriptions.setActive(new SubscriptionInfo(10, 1));
        assertEmpty("SIM2 subscription changed mid-query", apn(second.indication, SELECTION));
        state.resolver.afterQuery = null;
        state.subscriptions.setActive(new SubscriptionInfo(7, 0), new SubscriptionInfo(9, 1));
        queries = state.resolver.queries;
        assertEmpty("dual-active SIM1 rejected", apn(state.service.indication, SELECTION));
        assertEmpty("dual-active SIM2 rejected", apn(second.indication, SELECTION));
        assertEquals("dual-active skips both queries", queries, state.resolver.queries);
        state.subscriptions.setActive(new SubscriptionInfo(7, 0));
        state.telephony.setSimOperator(7, "46697");
    }

    private static DataProfile dataProfile(String apn, int types, boolean enabled, boolean lte,
            int protocol, int roaming, String user, String password, int auth) {
        return new DataProfile(new ApnSetting(apn, types, enabled, lte, protocol, roaming,
                user, password, auth));
    }

    private static HwBlob apn(IHwBinder indication, String selection) throws Exception {
        HwParcel request = request(M11SehRadioTransport.INDICATION);
        request.writeString(selection);
        HwParcel reply = call(indication, 22, request);
        assertReply(reply);
        return reply.readBuffer();
    }

    private static void assertHashChain(IHwBinder binder, byte[] own) throws Exception {
        HwParcel reply = call(binder, 256398152, request(M11SehRadioTransport.BASE));
        assertReply(reply);
        HwBlob vector = reply.readBuffer();
        assertEquals("hash count", 2, vector.getInt32(8));
        HwBlob hashes = vector.getBlob(0);
        assertArrayEquals("interface hash", own, hashes.getInt8Array(0));
        assertArrayEquals("IBase hash", BASE_HASH, hashes.getInt8Array(32));
    }

    private static HwParcel request(String descriptor) {
        HwParcel request = new HwParcel();
        request.writeInterfaceToken(descriptor);
        return request;
    }

    private static HwParcel call(IHwBinder binder, int code, HwParcel request) throws Exception {
        HwParcel reply = new HwParcel();
        binder.transact(code, request, reply, 0);
        return reply;
    }

    private static void assertReply(HwParcel reply) {
        assertEquals("reply status", Integer.valueOf(0), reply.status());
        assertTrue("reply sent", reply.sent());
    }

    private static String[] profileFields(HwBlob profile) {
        String[] result = new String[6];
        for (int i = 0; i < result.length; i++) result[i] = profile.getString(i * 16);
        return result;
    }

    private static String[] providerOrder(String[] wire) {
        return new String[] {wire[0], wire[1], wire[3], wire[4], wire[5], wire[2]};
    }

    private static void assertEmpty(String message, HwBlob profile) {
        assertArrayEquals(message, new String[] {"", "", "", "", "", ""},
                profileFields(profile));
    }

    private static boolean containsLog(String text) {
        for (String line : Rlog.lines()) if (line.contains(text)) return true;
        return false;
    }

    private static void run(String name, CheckedRunnable test) throws Exception {
        try {
            test.run();
            tests++;
            System.out.println("ok " + tests + " - " + name);
        } catch (Throwable failure) {
            System.err.println("not ok " + (tests + 1) + " - " + name);
            failure.printStackTrace(System.err);
            if (failure instanceof Exception) throw (Exception) failure;
            throw (Error) failure;
        }
    }

    private static void assertTrue(String message, boolean value) {
        if (!value) throw new AssertionError(message);
    }
    private static void assertFalse(String message, boolean value) { assertTrue(message, !value); }
    private static void assertNotNull(String message, Object value) {
        if (value == null) throw new AssertionError(message);
    }
    private static void assertEquals(String message, Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(message + ": expected=" + expected + " actual=" + actual);
        }
    }
    private static void assertEquals(String message, int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(message + ": expected=" + expected + " actual=" + actual);
        }
    }
    private static void assertArrayEquals(String message, byte[] expected, byte[] actual) {
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(message + ": expected=" + Arrays.toString(expected)
                    + " actual=" + Arrays.toString(actual));
        }
    }
    private static void assertArrayEquals(String message, String[] expected, String[] actual) {
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(message + ": expected=" + Arrays.toString(expected)
                    + " actual=" + Arrays.toString(actual));
        }
    }
    private static byte[] hex(String value) {
        byte[] result = new byte[value.length() / 2];
        for (int i = 0; i < result.length; i++) {
            result[i] = (byte) Integer.parseInt(value.substring(i * 2, i * 2 + 2), 16);
        }
        return result;
    }

    private static final class State {
        final FakeContext context;
        final FakeResolver resolver;
        final SubscriptionManager subscriptions;
        final TelephonyManager telephony;
        RecordingService service;
        State(FakeContext context, FakeResolver resolver, SubscriptionManager subscriptions,
                TelephonyManager telephony, RecordingService service) {
            this.context = context;
            this.resolver = resolver;
            this.subscriptions = subscriptions;
            this.telephony = telephony;
            this.service = service;
        }
    }

    private static final class FakeContext extends Context {
        final FakeResolver resolver;
        final SubscriptionManager subscriptions;
        final TelephonyManager telephony;
        FakeContext(FakeResolver resolver, SubscriptionManager subscriptions,
                TelephonyManager telephony) {
            this.resolver = resolver;
            this.subscriptions = subscriptions;
            this.telephony = telephony;
        }
        @Override public ContentResolver getContentResolver() { return resolver; }
        @Override @SuppressWarnings("unchecked")
        public <T> T getSystemService(Class<T> type) {
            if (type == SubscriptionManager.class) return (T) subscriptions;
            if (type == TelephonyManager.class) return (T) telephony;
            return null;
        }
    }

    private static final class FakeResolver extends ContentResolver {
        enum Mode { ROWS, EMPTY, NULL, THROW }
        Mode mode = Mode.EMPTY;
        String[][] rows = new String[0][];
        String lastUri, lastSelection, lastSortOrder;
        String[] lastProjection, lastSelectionArgs;
        int queries, mutations, closes;
        Runnable afterQuery, onClose;
        boolean throwOnClose;
        @Override public Cursor query(Uri uri, String[] projection, String selection,
                String[] selectionArgs, String sortOrder) {
            queries++;
            lastUri = uri.toString();
            lastProjection = projection.clone();
            lastSelection = selection;
            lastSelectionArgs = selectionArgs;
            lastSortOrder = sortOrder;
            if (mode == Mode.THROW) throw new IllegalStateException("injected query failure");
            if (afterQuery != null) afterQuery.run();
            if (mode == Mode.NULL) return null;
            return new FakeCursor(mode == Mode.EMPTY ? new String[0][] : rows, this);
        }
    }

    private static final class FakeCursor implements Cursor {
        private final String[][] rows;
        private final FakeResolver owner;
        private int index = -1;
        FakeCursor(String[][] rows, FakeResolver owner) { this.rows = rows; this.owner = owner; }
        @Override public boolean moveToFirst() { index = rows.length == 0 ? -1 : 0; return index == 0; }
        @Override public boolean moveToNext() { index++; return index < rows.length; }
        @Override public String getString(int column) { return rows[index][column]; }
        @Override public int getInt(int column) { return Integer.parseInt(rows[index][column]); }
        @Override public boolean isNull(int column) { return rows[index][column] == null; }
        @Override public void close() {
            owner.closes++;
            if (owner.onClose != null) owner.onClose.run();
            if (owner.throwOnClose) throw new IllegalStateException("injected close failure");
        }
    }

    private static final class RecordingService implements IHwBinder {
        DeathRecipient deathRecipient;
        long deathCookie;
        IHwBinder response, indication;
        int registrations;
        @Override public void transact(int code, HwParcel request, HwParcel reply, int flags) {
            if (code != 1 || flags != 0) throw new AssertionError("bad registration transaction");
            request.enforceInterface(M11SehRadioTransport.RADIO);
            response = request.readStrongBinder();
            indication = request.readStrongBinder();
            registrations++;
            reply.writeStatus(0);
            reply.send();
        }
        @Override public boolean linkToDeath(DeathRecipient recipient, long cookie) {
            deathRecipient = recipient;
            deathCookie = cookie;
            return true;
        }
        @Override public boolean unlinkToDeath(DeathRecipient recipient) {
            if (deathRecipient == recipient) deathRecipient = null;
            return true;
        }
        @Override public IHwInterface queryLocalInterface(String descriptor) { return null; }
        void die() {
            DeathRecipient recipient = deathRecipient;
            if (recipient == null) throw new AssertionError("no death recipient");
            recipient.serviceDied(deathCookie);
        }
    }
}
