package com.android.internal.telephony;

/** Standalone checks for the packed Samsung M11 legacy IWLAN MTU representation. */
public final class SamsungM11MtuTest {
    private SamsungM11MtuTest() {}

    public static void main(String[] args) {
        expect(1500, 1500, 1500, 0x05dc05dc, "packed 1500/1500");
        expect(1310, 1310, 1310, 0x051e051e, "packed 1310/1310");
        expect(1500, 1500, 1310, 0x051e05dc, "asymmetric family MTUs");
        expect(1310, 0, 1310, 0x051e0000, "valid IPv6-only packed MTU");
        expect(1280, 68, 1280, 0x05000044, "minimum family MTU bounds");
        expect(10000, 10000, 10000, 0x27102710, "maximum family MTU bounds");
        expect(1500, 1500, 1500, 1500, "ordinary scalar value retained in all fields");
        expect(576, 576, 576, 576, "ordinary scalar MTU");
        expect(65535, 65535, 65535, 65535, "scalar sentinel preserved");
        expect(0x051e0001, 0x051e0001, 0x051e0001, 0x051e0001,
                "invalid IPv4 field bypasses packed decode");
        expect(0x04ff05dc, 0x04ff05dc, 0x04ff05dc, 0x04ff05dc,
                "invalid IPv6 field bypasses packed decode");
        expect(0x00010000, 0x00010000, 0x00010000, 0x00010000,
                "invalid nonzero family bypasses packed decode");
        expect(0, 0, 0, 0, "zero sentinel preserved");
        expect(-1, -1, -1, -1, "negative sentinel preserved");
    }

    private static void expect(int expectedLegacy, int expectedV4, int expectedV6,
            int rawMtu, String description) {
        int[] actual = SamsungM11Mtu.decodeLegacyMtu(rawMtu);
        if (actual.length != 3 || actual[0] != expectedLegacy || actual[1] != expectedV4
                || actual[2] != expectedV6) {
            throw new AssertionError(description + ": expected [" + expectedLegacy + ", "
                    + expectedV4 + ", " + expectedV6 + "] but got [" + actual[0] + ", "
                    + actual[1] + ", " + actual[2] + "]");
        }
    }
}
