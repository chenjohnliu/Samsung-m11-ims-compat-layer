/* SPDX-License-Identifier: Apache-2.0 */
package com.android.internal.telephony;

import android.os.HwBinder;
import android.os.HwBlob;
import android.os.HwParcel;
import android.os.IHwBinder;
import android.os.IHwInterface;
import android.os.HidlSupport;
import android.os.RemoteException;
import java.util.ArrayList;
import java.util.Arrays;

/** Clean-room base-2.0 transport; does not send standard Android radio requests. */
public final class M11SehRadioTransport {
    public static final String RADIO = "vendor.samsung.hardware.radio@2.0::ISehRadio";
    public static final String INDICATION = "vendor.samsung.hardware.radio@2.0::ISehRadioIndication";
    public static final String RESPONSE = "vendor.samsung.hardware.radio@2.0::ISehRadioResponse";
    public static final String BASE = "android.hidl.base@1.0::IBase";

    public interface Backend {
        boolean current();
        M11SehApnPolicy.Profile apn(String selection);
        int setting(String key, String table);
        PacketUsage packetUsage(String iface);
        void ignoredIndication(int indicationType);
        void unexpectedResponse();
    }

    public static final class PacketUsage {
        public final int error;
        public final long receiveBytes, transmitBytes;
        public PacketUsage(int error, long receiveBytes, long transmitBytes) {
            this.error = error;
            this.receiveBytes = receiveBytes;
            this.transmitBytes = transmitBytes;
        }
    }

    public final IHwBinder response;
    public final IHwBinder indication;

    /** Hash-chain bytes are supplied from the reviewed stock ABI contract. */
    public M11SehRadioTransport(Backend backend, byte[][] responseHashes, byte[][] indicationHashes) {
        response = new Response(backend, responseHashes);
        indication = new Indication(backend, indicationHashes);
    }

    public void register(IHwBinder service) throws RemoteException {
        HwParcel request = new HwParcel();
        HwParcel reply = new HwParcel();
        try {
            request.writeInterfaceToken(RADIO);
            // The vendor setter clears both callbacks if either argument is null.
            request.writeStrongBinder(response);
            request.writeStrongBinder(indication);
            service.transact(1, request, reply, 0);
            reply.verifySuccess();
        } finally {
            request.releaseTemporaryStorage();
            reply.release();
        }
    }

    private abstract static class Callback extends HwBinder implements IHwInterface {
        final Backend backend;
        final String descriptor;
        private final byte[][] hashes;

        Callback(Backend backend, String descriptor, byte[][] hashes) {
            if (backend == null || hashes == null || hashes.length != 2) {
                throw new IllegalArgumentException("Reviewed base-2.0 hash chain required");
            }
            this.backend = backend;
            this.descriptor = descriptor;
            this.hashes = new byte[hashes.length][];
            for (int i = 0; i < hashes.length; i++) {
                if (hashes[i] == null || hashes[i].length != 32) {
                    throw new IllegalArgumentException("HIDL hash must be 32 bytes");
                }
                this.hashes[i] = hashes[i].clone();
            }
        }

        @Override public IHwBinder asBinder() { return this; }
        @Override public boolean linkToDeath(IHwBinder.DeathRecipient recipient, long cookie) {
            return true; // Local HIDL stub, matching the generated base-2.0 contract.
        }
        @Override public boolean unlinkToDeath(IHwBinder.DeathRecipient recipient) {
            return true;
        }
        @Override public IHwInterface queryLocalInterface(String name) {
            return descriptor.equals(name) ? this : null;
        }

        static boolean flags(HwParcel reply, boolean oneway, boolean expected) {
            if (oneway == expected) return true;
            reply.writeStatus(Integer.MIN_VALUE);
            reply.send();
            return false;
        }

        @Override public void onTransact(int code, HwParcel request, HwParcel reply,
                int transactionFlags) throws RemoteException {
            boolean oneway = (transactionFlags & 1) != 0;
            switch (code) {
                case 256067662: // IBase.interfaceChain
                    if (!flags(reply, oneway, false)) return;
                    request.enforceInterface(BASE);
                    reply.writeStatus(0);
                    reply.writeStringVector(new ArrayList<>(Arrays.asList(descriptor, BASE)));
                    reply.send();
                    return;
                case 256131655: // IBase.debug
                    if (!flags(reply, oneway, false)) return;
                    request.enforceInterface(BASE);
                    request.readNativeHandle();
                    request.readStringVector();
                    reply.writeStatus(0);
                    reply.send();
                    return;
                case 256136003: // IBase.interfaceDescriptor
                    if (!flags(reply, oneway, false)) return;
                    request.enforceInterface(BASE);
                    reply.writeStatus(0);
                    reply.writeString(descriptor);
                    reply.send();
                    return;
                case 256398152: // IBase.getHashChain
                    if (!flags(reply, oneway, false)) return;
                    request.enforceInterface(BASE);
                    HwBlob vector = new HwBlob(16);
                    vector.putInt32(8, hashes.length);
                    vector.putBool(12, false);
                    HwBlob child = new HwBlob(hashes.length * 32);
                    for (int i = 0; i < hashes.length; i++) child.putInt8Array(i * 32, hashes[i]);
                    vector.putBlob(0, child);
                    reply.writeStatus(0);
                    reply.writeBuffer(vector);
                    reply.send();
                    return;
                case 256462420: // IBase.setHALInstrumentation
                    if (!flags(reply, oneway, true)) return;
                    request.enforceInterface(BASE);
                    return;
                case 256921159: // IBase.ping
                    if (!flags(reply, oneway, false)) return;
                    request.enforceInterface(BASE);
                    reply.writeStatus(0);
                    reply.send();
                    return;
                case 257049926: // IBase.getDebugInfo
                    if (!flags(reply, oneway, false)) return;
                    request.enforceInterface(BASE);
                    HwBlob info = new HwBlob(24);
                    info.putInt32(0, HidlSupport.getPidIfSharable());
                    info.putInt64(8, 0);
                    info.putInt32(16, 0);
                    reply.writeStatus(0);
                    reply.writeBuffer(info);
                    reply.send();
                    return;
                case 257120595: // IBase.notifySyspropsChanged
                    if (!flags(reply, oneway, true)) return;
                    request.enforceInterface(BASE);
                    HwBinder.enableInstrumentation();
                    return;
                default:
                    vendorTransaction(code, request, reply, oneway);
            }
        }

        abstract void vendorTransaction(int code, HwParcel request, HwParcel reply, boolean oneway);
    }

    private static final class Response extends Callback {
        Response(Backend backend, byte[][] hashes) { super(backend, RESPONSE, hashes); }
        @Override void vendorTransaction(int code, HwParcel request, HwParcel reply, boolean oneway) {
            if (code < 1 || code > 40) return;
            if (!flags(reply, oneway, true)) return;
            request.enforceInterface(RESPONSE);
            // No SEH solicited operations are issued by this client. Do not touch
            // AOSP request serials, wakelocks, data setup, or call state.
            if (backend.current()) backend.unexpectedResponse();
        }
    }

    private static final class Indication extends Callback {
        Indication(Backend backend, byte[][] hashes) { super(backend, INDICATION, hashes); }
        @Override void vendorTransaction(int code, HwParcel request, HwParcel reply, boolean oneway) {
            if (code < 1 || code > 27) return;
            if (code == 22 || code == 23 || code == 27) {
                if (!flags(reply, oneway, false)) return;
                request.enforceInterface(INDICATION);
                reply.writeStatus(0);
                if (code == 23) {
                    String key = request.readString();
                    String table = request.readString();
                    int value = -1;
                    try {
                        if (backend.current()) value = backend.setting(key, table);
                        if (!backend.current()) value = -1;
                    } catch (RuntimeException ignored) { value = -1; }
                    reply.writeInt32(value);
                } else if (code == 22) {
                    String selection = request.readString();
                    M11SehApnPolicy.Profile profile = M11SehApnPolicy.EMPTY;
                    try {
                        if (backend.current()) profile = backend.apn(selection);
                        if (!backend.current()) profile = M11SehApnPolicy.EMPTY;
                    } catch (RuntimeException ignored) { profile = M11SehApnPolicy.EMPTY; }
                    if (profile == null) profile = M11SehApnPolicy.EMPTY;
                    HwBlob blob = new HwBlob(96);
                    String[] fields = profile.wireFields();
                    for (int i = 0; i < fields.length; i++) blob.putString(i * 16, fields[i]);
                    reply.writeBuffer(blob);
                } else {
                    String iface = request.readString();
                    PacketUsage usage = null;
                    try {
                        if (backend.current()) usage = backend.packetUsage(iface);
                        if (!backend.current()) usage = null;
                    } catch (RuntimeException ignored) { usage = null; }
                    if (usage == null) usage = new PacketUsage(44, 0, 0);
                    reply.writeInt32(usage.error);
                    HwBlob counters = new HwBlob(16);
                    counters.putInt64(0, usage.receiveBytes);
                    counters.putInt64(8, usage.transmitBytes);
                    reply.writeBuffer(counters);
                }
                reply.send();
                return;
            }
            // Stock signalLevelInfoChanged / extendedRegistrationState are synchronous void.
            boolean synchronous = code == 25 || code == 26;
            if (!flags(reply, oneway, !synchronous)) return;
            request.enforceInterface(INDICATION);
            int indicationType = request.readInt32();
            if (backend.current()) backend.ignoredIndication(indicationType);
            if (synchronous) { reply.writeStatus(0); reply.send(); }
            // Stock SemRIL.sendAck() is empty: never send a standard-radio ACK.
        }
    }
}
