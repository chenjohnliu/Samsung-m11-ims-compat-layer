package com.android.internal.telephony;

import android.os.HwBinder;
import android.os.HwBlob;
import android.os.HwParcel;
import android.os.IHwBinder;
import android.os.IHwInterface;
import android.os.NativeHandle;
import android.os.RemoteException;
import java.util.ArrayList;
import java.util.Arrays;

public final class M11SehTransportHostHarness {
    private static final byte[] RESPONSE_HASH = hex(
            "939e27ee9b2db9d044f3425f6dbde5896bc561155126551f257a0e06de01e092");
    private static final byte[] INDICATION_HASH = hex(
            "780fa0f585c25754cc6343bf00dee5157efcf6f8526bc1797aacb87e8d375fa4");
    private static final byte[] BASE_HASH = hex(
            "ec7fd79ed02dfa85bc499426adae3ebe23ef0524f3cd6957139324b83b18ca4c");

    private interface CheckedRunnable { void run() throws Exception; }
    private static int tests;

    public static void main(String[] args) throws Exception {
        run("policy exact IMS fallback scope", M11SehTransportHostHarness::testPolicyScope);
        run("policy profile validation and matching", M11SehTransportHostHarness::testPolicyProfile);
        run("registration binder order and lifecycle", M11SehTransportHostHarness::testRegister);
        run("tx22 APN wire order and flags", M11SehTransportHostHarness::testApnTransaction);
        run("tx23 setting argument and reply order", M11SehTransportHostHarness::testSettingTransaction);
        run("tx27 packet primitive/blob order", M11SehTransportHostHarness::testPacketTransaction);
        run("sync void 25/26 and no ACK", M11SehTransportHostHarness::testSyncVoidAndNoAck);
        run("stale and exception-safe synchronous replies", M11SehTransportHostHarness::testStaleAndExceptions);
        run("IBase descriptor chain hashes ping debug", M11SehTransportHostHarness::testBaseTransactions);
        run("local death links and interface lookup", M11SehTransportHostHarness::testLocalBinderContract);
        run("unknown transaction bounds", M11SehTransportHostHarness::testUnknownBounds);
        run("response bounds and callback policy", M11SehTransportHostHarness::testResponseBounds);
        run("reviewed hash input validation and cloning", M11SehTransportHostHarness::testHashValidation);
        System.out.println("PASS: " + tests + " M11 SEH policy/transport host tests");
    }

    private static void testPolicyScope() {
        M11SehApnPolicy.Profile ims = profile();
        M11SehApnPolicy.Snapshot snapshot =
                new M11SehApnPolicy.Snapshot(0, 7, "46697", ims);
        assertEquals("selection literal", "carrier_enabled=1 and (bearer=14 or bearer=0)"
                + " and bearer_bitmask!=131072 and type LIKE '%ims%'",
                M11SehApnPolicy.IMS_SELECTION);
        assertSame("exact match", ims, M11SehApnPolicy.fallback(snapshot, 0, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertEmpty("inactive", M11SehApnPolicy.fallback(snapshot, 0, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, false));
        assertEmpty("other slot snapshot", M11SehApnPolicy.fallback(snapshot, 1, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertSame("SIM2 matching snapshot", ims, M11SehApnPolicy.fallback(
                new M11SehApnPolicy.Snapshot(1, 7, "46697", ims), 1, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertEmpty("invalid third slot", M11SehApnPolicy.fallback(snapshot, 2, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertEmpty("invalid sub", M11SehApnPolicy.fallback(snapshot, 0, -1, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertEmpty("other operator", M11SehApnPolicy.fallback(snapshot, 0, 7, "46692",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertEmpty("selection suffix", M11SehApnPolicy.fallback(snapshot, 0, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION + " ", true));
        assertEmpty("default query", M11SehApnPolicy.fallback(snapshot, 0, 7, "46697",
                "carrier_enabled=1 and type LIKE '%default%'", true));
        assertEmpty("null snapshot", M11SehApnPolicy.fallback(null, 0, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertEmpty("stale phone", M11SehApnPolicy.fallback(
                new M11SehApnPolicy.Snapshot(1, 7, "46697", ims), 0, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertEmpty("stale sub", M11SehApnPolicy.fallback(
                new M11SehApnPolicy.Snapshot(0, 8, "46697", ims), 0, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertEmpty("stale operator", M11SehApnPolicy.fallback(
                new M11SehApnPolicy.Snapshot(0, 7, "46692", ims), 0, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
    }

    private static void testPolicyProfile() {
        M11SehApnPolicy.Profile normalized =
                new M11SehApnPolicy.Profile(null, null, null, null, null, null);
        assertArrayEquals("null normalization", new String[] {"", "", "", "", "", ""},
                normalized.wireFields());
        assertFalse("empty unusable", normalized.usable());
        for (String protocol : new String[] {"IP", "IPV6", "IPV4V6"}) {
            for (String auth : new String[] {"-1", "0", "1", "2", "3"}) {
                assertTrue("accepted profile " + protocol + "/" + auth,
                        new M11SehApnPolicy.Profile("ims", protocol, protocol, "", "", auth)
                                .usable());
            }
        }
        assertFalse("bad protocol", new M11SehApnPolicy.Profile(
                "ims", "PPP", "IPV4V6", "", "", "0").usable());
        assertFalse("bad roaming protocol", new M11SehApnPolicy.Profile(
                "ims", "IPV4V6", "PPP", "", "", "0").usable());
        assertFalse("bad auth", new M11SehApnPolicy.Profile(
                "ims", "IPV4V6", "IPV4V6", "", "", "4").usable());
        assertFalse("empty APN", new M11SehApnPolicy.Profile(
                "", "IPV4V6", "IPV4V6", "", "", "0").usable());
        assertEmpty("null snapshot profile", M11SehApnPolicy.fallback(
                new M11SehApnPolicy.Snapshot(0, 7, "46697", null), 0, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
        assertEmpty("unusable snapshot profile", M11SehApnPolicy.fallback(
                new M11SehApnPolicy.Snapshot(0, 7, "46697", normalized), 0, 7, "46697",
                M11SehApnPolicy.IMS_SELECTION, true));
    }

    private static void testRegister() throws Exception {
        FakeBackend backend = new FakeBackend();
        M11SehRadioTransport transport = transport(backend);
        RecordingService service = new RecordingService();
        transport.register(service);
        assertEquals("register code", 1, service.code);
        assertEquals("register flags", 0, service.flags);
        assertEquals("register token", M11SehRadioTransport.RADIO,
                service.request.events().get(0).value);
        assertEquals("event count", 3, service.request.events().size());
        assertEquals("response binder kind", "binder", service.request.events().get(1).kind);
        assertSame("response first", transport.response, service.request.events().get(1).value);
        assertSame("indication second", transport.indication, service.request.events().get(2).value);
        assertNotNull("response non-null", service.response);
        assertNotNull("indication non-null", service.indication);
        assertTrue("request temp released", service.request.temporaryStorageReleased());
        assertTrue("reply released", service.reply.released());
    }

    private static void testApnTransaction() throws Exception {
        FakeBackend backend = new FakeBackend();
        backend.apnResult = new M11SehApnPolicy.Profile(
                "ims", "IPV4V6", "IP", "alice", "secret", "3");
        M11SehRadioTransport transport = transport(backend);
        HwParcel request = request(M11SehRadioTransport.INDICATION);
        request.writeString("selection-value");
        HwParcel reply = call(transport.indication, 22, request, 0);
        assertEquals("APN selection", "selection-value", backend.lastSelection);
        assertEquals("APN calls", 1, backend.apnCalls);
        assertReplyOk(reply);
        HwBlob blob = reply.readBuffer();
        assertEquals("APN blob size", 96, blob.size());
        assertEquals("apn@0", "ims", blob.getString(0));
        assertEquals("protocol@16", "IPV4V6", blob.getString(16));
        assertEquals("roaming@32", "IP", blob.getString(32));
        assertEquals("user@48", "alice", blob.getString(48));
        assertEquals("password@64", "secret", blob.getString(64));
        assertEquals("auth@80", "3", blob.getString(80));

        HwParcel wrong = request(M11SehRadioTransport.INDICATION);
        wrong.writeString("ignored");
        HwParcel wrongReply = call(transport.indication, 22, wrong, 1);
        assertEquals("wrong APN flag status", Integer.MIN_VALUE, wrongReply.status().intValue());
        assertTrue("wrong APN flag sent", wrongReply.sent());
        assertEquals("wrong APN flag did not call backend", 1, backend.apnCalls);
    }

    private static void testSettingTransaction() throws Exception {
        FakeBackend backend = new FakeBackend();
        backend.settingResult = 73;
        M11SehRadioTransport transport = transport(backend);
        HwParcel request = request(M11SehRadioTransport.INDICATION);
        request.writeString("wifi_call_enable1");
        request.writeString("system");
        HwParcel reply = call(transport.indication, 23, request, 0);
        assertEquals("key first", "wifi_call_enable1", backend.lastKey);
        assertEquals("table second", "system", backend.lastTable);
        assertReplyOk(reply);
        assertEquals("setting reply int32", 73, reply.readInt32());
        assertEquals("setting has one payload", 1, reply.events().size());
    }

    private static void testPacketTransaction() throws Exception {
        FakeBackend backend = new FakeBackend();
        backend.packetResult = new M11SehRadioTransport.PacketUsage(9, 0x1122334455667788L,
                0x7766554433221100L);
        M11SehRadioTransport transport = transport(backend);
        HwParcel request = request(M11SehRadioTransport.INDICATION);
        request.writeString("rmnet_data1");
        HwParcel reply = call(transport.indication, 27, request, 0);
        assertEquals("packet iface", "rmnet_data1", backend.lastIface);
        assertReplyOk(reply);
        assertEquals("packet error precedes blob", "int32", reply.events().get(0).kind);
        assertEquals("packet blob second", "blob", reply.events().get(1).kind);
        assertEquals("packet error", 9, reply.readInt32());
        HwBlob blob = reply.readBuffer();
        assertEquals("packet blob size", 16, blob.size());
        assertEquals("rx@0", 0x1122334455667788L, blob.getInt64(0));
        assertEquals("tx@8", 0x7766554433221100L, blob.getInt64(8));
    }

    private static void testSyncVoidAndNoAck() throws Exception {
        FakeBackend backend = new FakeBackend();
        M11SehRadioTransport transport = transport(backend);
        for (int code : new int[] {25, 26}) {
            HwParcel request = request(M11SehRadioTransport.INDICATION);
            request.writeInt32(100 + code);
            HwParcel reply = call(transport.indication, code, request, 0);
            assertReplyOk(reply);
            assertEquals("sync void has no payload", 0, reply.events().size());
        }
        assertEquals("sync void calls", 2, backend.ignoredCalls);
        assertEquals("sync void last type", 126, backend.lastIndicationType);

        HwParcel oneway = request(M11SehRadioTransport.INDICATION);
        oneway.writeInt32(5);
        HwParcel onewayReply = call(transport.indication, 1, oneway, 1);
        assertEquals("oneway indication called", 3, backend.ignoredCalls);
        assertFalse("oneway sends no reply/ACK", onewayReply.sent());
        assertEquals("oneway writes no status", null, onewayReply.status());

        HwParcel wrong = request(M11SehRadioTransport.INDICATION);
        wrong.writeInt32(7);
        HwParcel wrongReply = call(transport.indication, 25, wrong, 1);
        assertEquals("sync void rejects oneway", Integer.MIN_VALUE,
                wrongReply.status().intValue());
        assertEquals("wrong flag no backend", 3, backend.ignoredCalls);
    }

    private static void testStaleAndExceptions() throws Exception {
        FakeBackend stale = new FakeBackend();
        stale.current = false;
        M11SehRadioTransport transport = transport(stale);
        assertEmptyApnReply(call(transport.indication, 22,
                requestWithString(M11SehRadioTransport.INDICATION, "ims"), 0));
        assertEquals("stale APN backend skipped", 0, stale.apnCalls);
        HwParcel settingRequest = request(M11SehRadioTransport.INDICATION);
        settingRequest.writeString("key");
        settingRequest.writeString("global");
        HwParcel settingReply = call(transport.indication, 23, settingRequest, 0);
        assertEquals("stale setting", -1, settingReply.readInt32());
        HwParcel packetReply = call(transport.indication, 27,
                requestWithString(M11SehRadioTransport.INDICATION, "rmnet0"), 0);
        assertUnsupportedPacket(packetReply);
        HwParcel ignored = request(M11SehRadioTransport.INDICATION);
        ignored.writeInt32(1);
        call(transport.indication, 1, ignored, 1);
        assertEquals("stale indication skipped", 0, stale.ignoredCalls);

        FakeBackend throwing = new FakeBackend();
        throwing.throwSync = true;
        transport = transport(throwing);
        assertEmptyApnReply(call(transport.indication, 22,
                requestWithString(M11SehRadioTransport.INDICATION, "ims"), 0));
        settingRequest = request(M11SehRadioTransport.INDICATION);
        settingRequest.writeString("key");
        settingRequest.writeString("secure");
        settingReply = call(transport.indication, 23, settingRequest, 0);
        assertEquals("throwing setting", -1, settingReply.readInt32());
        packetReply = call(transport.indication, 27,
                requestWithString(M11SehRadioTransport.INDICATION, "rmnet0"), 0);
        assertUnsupportedPacket(packetReply);

        FakeBackend throwingCurrent = new FakeBackend();
        throwingCurrent.throwCurrent = true;
        transport = transport(throwingCurrent);
        assertEmptyApnReply(call(transport.indication, 22,
                requestWithString(M11SehRadioTransport.INDICATION, "ims"), 0));
    }

    private static void testBaseTransactions() throws Exception {
        M11SehRadioTransport transport = transport(new FakeBackend());
        checkBase(transport.response, M11SehRadioTransport.RESPONSE, RESPONSE_HASH);
        checkBase(transport.indication, M11SehRadioTransport.INDICATION, INDICATION_HASH);

        HwBinder.resetInstrumentationCalls();
        HwParcel setHal = request(M11SehRadioTransport.BASE);
        HwParcel setHalReply = call(transport.indication, 256462420, setHal, 1);
        assertFalse("setHALInstrumentation oneway no reply", setHalReply.sent());
        HwParcel notify = request(M11SehRadioTransport.BASE);
        HwParcel notifyReply = call(transport.indication, 257120595, notify, 1);
        assertFalse("notifySysprops oneway no reply", notifyReply.sent());
        assertEquals("instrumentation enabled", 1, HwBinder.instrumentationCalls());
    }

    private static void checkBase(IHwBinder binder, String descriptor, byte[] ownHash)
            throws Exception {
        HwParcel chainReply = call(binder, 256067662, request(M11SehRadioTransport.BASE), 0);
        assertReplyOk(chainReply);
        assertEquals("chain", new ArrayList<>(Arrays.asList(descriptor,
                M11SehRadioTransport.BASE)), chainReply.readStringVector());

        HwParcel descriptorReply = call(binder, 256136003,
                request(M11SehRadioTransport.BASE), 0);
        assertReplyOk(descriptorReply);
        assertEquals("descriptor", descriptor, descriptorReply.readString());

        HwParcel hashReply = call(binder, 256398152, request(M11SehRadioTransport.BASE), 0);
        assertReplyOk(hashReply);
        HwBlob vector = hashReply.readBuffer();
        assertEquals("hash vector header size", 16, vector.size());
        assertEquals("hash count", 2, vector.getInt32(8));
        assertFalse("hash owns child", vector.getBool(12));
        HwBlob child = vector.getBlob(0);
        assertEquals("hash child size", 64, child.size());
        assertArrayEquals("own hash", ownHash, child.getInt8Array(0));
        assertArrayEquals("base hash", BASE_HASH, child.getInt8Array(32));

        HwParcel pingReply = call(binder, 256921159, request(M11SehRadioTransport.BASE), 0);
        assertReplyOk(pingReply);
        assertEquals("ping no payload", 0, pingReply.events().size());

        HwParcel debugRequest = request(M11SehRadioTransport.BASE);
        debugRequest.writeNativeHandle(new NativeHandle());
        debugRequest.writeStringVector(new ArrayList<>(Arrays.asList("one", "two")));
        HwParcel debugReply = call(binder, 256131655, debugRequest, 0);
        assertReplyOk(debugReply);
        assertEquals("debug no payload", 0, debugReply.events().size());

        HwParcel infoReply = call(binder, 257049926, request(M11SehRadioTransport.BASE), 0);
        assertReplyOk(infoReply);
        HwBlob info = infoReply.readBuffer();
        assertEquals("debug info size", 24, info.size());
        assertEquals("debug pid", 4242, info.getInt32(0));
        assertEquals("debug pointer", 0L, info.getInt64(8));
        assertEquals("debug arch", 0, info.getInt32(16));
    }

    private static void testLocalBinderContract() throws Exception {
        M11SehRadioTransport transport = transport(new FakeBackend());
        IHwBinder.DeathRecipient recipient = cookie -> {};
        for (IHwBinder binder : new IHwBinder[] {transport.response, transport.indication}) {
            assertTrue("linkToDeath", binder.linkToDeath(recipient, 99));
            assertTrue("unlinkToDeath", binder.unlinkToDeath(recipient));
        }
        assertSame("local response", transport.response,
                transport.response.queryLocalInterface(M11SehRadioTransport.RESPONSE));
        assertSame("local indication", transport.indication,
                transport.indication.queryLocalInterface(M11SehRadioTransport.INDICATION));
        assertEquals("wrong local interface", null,
                transport.indication.queryLocalInterface(M11SehRadioTransport.RESPONSE));
    }

    private static void testUnknownBounds() throws Exception {
        FakeBackend backend = new FakeBackend();
        M11SehRadioTransport transport = transport(backend);
        for (int code : new int[] {-1, 0, 28, 41, Integer.MAX_VALUE}) {
            HwParcel reply = call(transport.indication, code, new HwParcel(), code & 1);
            assertFalse("unknown indication not sent " + code, reply.sent());
            assertEquals("unknown indication no status " + code, null, reply.status());
        }
        assertEquals("unknown indication no backend", 0, backend.totalCalls());
    }

    private static void testResponseBounds() throws Exception {
        FakeBackend backend = new FakeBackend();
        M11SehRadioTransport transport = transport(backend);
        for (int code : new int[] {1, 40}) {
            HwParcel reply = call(transport.response, code,
                    request(M11SehRadioTransport.RESPONSE), 1);
            assertFalse("oneway response no reply", reply.sent());
        }
        assertEquals("bounded response callbacks", 2, backend.unexpectedCalls);
        for (int code : new int[] {0, 41}) {
            call(transport.response, code, new HwParcel(), 1);
        }
        assertEquals("out of bounds ignored", 2, backend.unexpectedCalls);
        backend.current = false;
        call(transport.response, 2, request(M11SehRadioTransport.RESPONSE), 1);
        assertEquals("stale response ignored", 2, backend.unexpectedCalls);

        HwParcel wrong = call(transport.response, 3,
                request(M11SehRadioTransport.RESPONSE), 0);
        assertEquals("response requires oneway", Integer.MIN_VALUE, wrong.status().intValue());
        assertEquals("wrong response flag skipped", 2, backend.unexpectedCalls);
    }

    private static void testHashValidation() throws Exception {
        expectThrows(IllegalArgumentException.class,
                () -> new M11SehRadioTransport(null, hashes(RESPONSE_HASH), hashes(INDICATION_HASH)));
        expectThrows(IllegalArgumentException.class,
                () -> new M11SehRadioTransport(new FakeBackend(), new byte[][] {RESPONSE_HASH},
                        hashes(INDICATION_HASH)));
        expectThrows(IllegalArgumentException.class,
                () -> new M11SehRadioTransport(new FakeBackend(),
                        new byte[][] {new byte[31], BASE_HASH}, hashes(INDICATION_HASH)));

        byte[][] response = hashes(RESPONSE_HASH);
        byte[][] indication = hashes(INDICATION_HASH);
        M11SehRadioTransport transport = new M11SehRadioTransport(
                new FakeBackend(), response, indication);
        response[0][0] ^= 0x7f;
        indication[1][0] ^= 0x7f;
        HwParcel reply = call(transport.response, 256398152,
                request(M11SehRadioTransport.BASE), 0);
        HwBlob child = reply.readBuffer().getBlob(0);
        assertArrayEquals("response hash cloned", RESPONSE_HASH, child.getInt8Array(0));
        assertArrayEquals("base hash cloned", BASE_HASH, child.getInt8Array(32));
    }

    private static M11SehRadioTransport transport(FakeBackend backend) {
        return new M11SehRadioTransport(backend, hashes(RESPONSE_HASH), hashes(INDICATION_HASH));
    }

    private static byte[][] hashes(byte[] own) { return new byte[][] {own.clone(), BASE_HASH.clone()}; }
    private static M11SehApnPolicy.Profile profile() {
        return new M11SehApnPolicy.Profile("ims", "IPV4V6", "IPV4V6", "", "", "0");
    }
    private static HwParcel request(String descriptor) {
        HwParcel request = new HwParcel();
        request.writeInterfaceToken(descriptor);
        return request;
    }
    private static HwParcel requestWithString(String descriptor, String value) {
        HwParcel request = request(descriptor);
        request.writeString(value);
        return request;
    }
    private static HwParcel call(IHwBinder binder, int code, HwParcel request, int flags)
            throws Exception {
        HwParcel reply = new HwParcel();
        binder.transact(code, request, reply, flags);
        return reply;
    }
    private static void assertReplyOk(HwParcel reply) {
        assertEquals("reply status", Integer.valueOf(0), reply.status());
        assertTrue("reply sent", reply.sent());
    }
    private static void assertEmptyApnReply(HwParcel reply) {
        assertReplyOk(reply);
        HwBlob blob = reply.readBuffer();
        for (int offset = 0; offset < 96; offset += 16) {
            assertEquals("empty APN field @" + offset, "", blob.getString(offset));
        }
    }
    private static void assertUnsupportedPacket(HwParcel reply) {
        assertReplyOk(reply);
        assertEquals("unsupported packet error", 44, reply.readInt32());
        HwBlob blob = reply.readBuffer();
        assertEquals("unsupported rx", 0L, blob.getInt64(0));
        assertEquals("unsupported tx", 0L, blob.getInt64(8));
    }
    private static void assertEmpty(String message, M11SehApnPolicy.Profile value) {
        assertSame(message, M11SehApnPolicy.EMPTY, value);
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
    private static void expectThrows(Class<? extends Throwable> expected, CheckedRunnable action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (expected.isInstance(actual)) return;
            throw new AssertionError("expected " + expected.getName() + " but got " + actual, actual);
        }
        throw new AssertionError("expected " + expected.getName());
    }
    private static void assertTrue(String message, boolean value) {
        if (!value) throw new AssertionError(message);
    }
    private static void assertFalse(String message, boolean value) { assertTrue(message, !value); }
    private static void assertNotNull(String message, Object value) {
        if (value == null) throw new AssertionError(message);
    }
    private static void assertSame(String message, Object expected, Object actual) {
        if (expected != actual) throw new AssertionError(message + ": expected same instance");
    }
    private static void assertEquals(String message, Object expected, Object actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(message + ": expected=" + expected + " actual=" + actual);
        }
    }
    private static void assertEquals(String message, long expected, long actual) {
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

    private static final class RecordingService implements IHwBinder {
        int code = -1;
        int flags = -1;
        HwParcel request;
        HwParcel reply;
        IHwBinder response;
        IHwBinder indication;

        @Override public void transact(int code, HwParcel request, HwParcel reply, int flags) {
            this.code = code;
            this.flags = flags;
            this.request = request;
            this.reply = reply;
            request.enforceInterface(M11SehRadioTransport.RADIO);
            response = request.readStrongBinder();
            indication = request.readStrongBinder();
            reply.writeStatus(0);
            reply.send();
        }
        @Override public boolean linkToDeath(DeathRecipient recipient, long cookie) { return true; }
        @Override public boolean unlinkToDeath(DeathRecipient recipient) { return true; }
        @Override public IHwInterface queryLocalInterface(String descriptor) { return null; }
    }

    private static final class FakeBackend implements M11SehRadioTransport.Backend {
        boolean current = true;
        boolean throwSync;
        boolean throwCurrent;
        M11SehApnPolicy.Profile apnResult = profile();
        int settingResult;
        M11SehRadioTransport.PacketUsage packetResult =
                new M11SehRadioTransport.PacketUsage(0, 1, 2);
        String lastSelection, lastKey, lastTable, lastIface;
        int lastIndicationType;
        int apnCalls, settingCalls, packetCalls, ignoredCalls, unexpectedCalls;

        @Override public boolean current() {
            if (throwCurrent) throw new IllegalStateException("current failure");
            return current;
        }
        @Override public M11SehApnPolicy.Profile apn(String selection) {
            apnCalls++;
            lastSelection = selection;
            if (throwSync) throw new IllegalStateException("apn failure");
            return apnResult;
        }
        @Override public int setting(String key, String table) {
            settingCalls++;
            lastKey = key;
            lastTable = table;
            if (throwSync) throw new IllegalStateException("setting failure");
            return settingResult;
        }
        @Override public M11SehRadioTransport.PacketUsage packetUsage(String iface) {
            packetCalls++;
            lastIface = iface;
            if (throwSync) throw new IllegalStateException("packet failure");
            return packetResult;
        }
        @Override public void ignoredIndication(int indicationType) {
            ignoredCalls++;
            lastIndicationType = indicationType;
        }
        @Override public void unexpectedResponse() { unexpectedCalls++; }
        int totalCalls() {
            return apnCalls + settingCalls + packetCalls + ignoredCalls + unexpectedCalls;
        }
    }
}
