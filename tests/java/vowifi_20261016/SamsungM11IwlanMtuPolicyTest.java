package com.android.internal.telephony.data;

/** Standalone behavioral checks for the pure Samsung M11 IWLAN MTU policy. */
public final class SamsungM11IwlanMtuPolicyTest {
    private static final String IFACE = "rmnet_data0";
    private static final int IFINDEX = 7;
    private static final int CID = 3;

    private SamsungM11IwlanMtuPolicyTest() {}

    public static void main(String[] args) {
        restoresOwnedWfcCapAndWaitsForObservedRestore();
        externalChangeDuringPendingRestoreIsPreserved();
        iwlanReentryDuringPendingRestoreKeepsBaseline();
        scopeLossStillCleansUpOwnedLease();
        honorsNativeSmallKernelMtu();
        externalKernelChangeRevokesLease();
        restoresTheObservedSourceBaseline();
        keepsFamilySpecificRoutes();
        unknownKernelSnapshotHoldsAnOwnedResult();
        changedIdentityCannotRestoreAnotherBearer();
        staticScopeFailsClosed();
        invalidInputsAndLowKernelFailClosed();
    }

    private static void externalChangeDuringPendingRestoreIsPreserved() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        evaluate(policy, true, true, IFACE, IFINDEX, CID, true, 1500, 1500, 1500);
        expect(1500, 1500, 1500, evaluate(policy, true, false, IFACE, IFINDEX, CID, true,
                1400, 1500, 1500), "restore target is issued before external update");
        SamsungM11IwlanMtuPolicy.Result external = evaluate(policy, true, false, IFACE,
                IFINDEX, CID, true, 1310, 1500, 1500);
        expect(1310, 1310, 1310, external,
                "external 1310 during pending restore revokes pending target");
        check(!policy.hasLease(), "pending restore lease clears on external kernel value");
    }

    private static void iwlanReentryDuringPendingRestoreKeepsBaseline() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        evaluate(policy, true, true, IFACE, IFINDEX, CID, true, 1500, 1500, 1500);
        evaluate(policy, true, false, IFACE, IFINDEX, CID, true, 1400, 1500, 1500);
        SamsungM11IwlanMtuPolicy.Result recapped = evaluate(policy, true, true, IFACE,
                IFINDEX, CID, true, 1400, 1500, 1500);
        expect(1400, 1400, 1400, recapped,
                "IWLAN re-entry resumes cap while restore remains pending");
        SamsungM11IwlanMtuPolicy.Result restoreAgain = evaluate(policy, true, false, IFACE,
                IFINDEX, CID, true, 1400, 1500, 1500);
        expect(1500, 1500, 1500, restoreAgain,
                "re-entry preserves the original 1500 baseline for the next exit");
    }

    private static void scopeLossStillCleansUpOwnedLease() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        evaluate(policy, true, true, IFACE, IFINDEX, CID, true, 1500, 1500, 1500);
        SamsungM11IwlanMtuPolicy.Result restored = evaluate(policy, false, false, IFACE,
                IFINDEX, CID, true, 1400, 1500, 1500);
        expect(1500, 1500, 1500, restored,
                "static scope loss still cleans up an owned lease");

        SamsungM11IwlanMtuPolicy.Result untouched = evaluate(policy, false, false, IFACE,
                IFINDEX, CID + 1, true, 1500, 1440, 1500);
        expect(1500, 1440, 1500, untouched, "scope false with no lease is unchanged");
        check(!policy.hasLease(), "scope loss leaves no active lease after cleanup");
    }

    private static void restoresOwnedWfcCapAndWaitsForObservedRestore() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        SamsungM11IwlanMtuPolicy.Result capped = evaluate(policy, true, true, IFACE, IFINDEX,
                CID, true, 1500, 1500, 1500);
        expect(1400, 1400, 1400, capped, "new data network inherits cached WFC state");
        check(policy.hasLease(), "1500 to 1400 creates ownership lease");

        SamsungM11IwlanMtuPolicy.Result restore = evaluate(policy, true, false, IFACE, IFINDEX,
                CID, true, 1400, 1500, 1500);
        expect(1500, 1500, 1500, restore, "WFC exit issues restore target");
        check(policy.hasLease(), "restore remains pending until interface observes it");

        SamsungM11IwlanMtuPolicy.Result pending = evaluate(policy, true, false, IFACE, IFINDEX,
                CID, true, 1400, 1500, 1500);
        expect(1500, 1500, 1500, pending, "repeated network event retains pending restore");

        SamsungM11IwlanMtuPolicy.Result newlyBounded = evaluate(policy, true, false, IFACE,
                IFINDEX, CID, true, 1400, 1310, 1310);
        expect(1310, 1310, 1310, newlyBounded,
                "new lower modem MTUs bound the pending restore target");

        SamsungM11IwlanMtuPolicy.Result targetCanExpandAgain = evaluate(policy, true, false,
                IFACE, IFINDEX, CID, true, 1400, 1500, 1500);
        expect(1500, 1500, 1500, targetCanExpandAgain,
                "pending target follows later valid report without losing baseline");

        SamsungM11IwlanMtuPolicy.Result observed = evaluate(policy, true, false, IFACE, IFINDEX,
                CID, true, 1500, 1500, 1500);
        expect(1500, 1500, 1500, observed, "observed restore completes lease");
        check(!policy.hasLease(), "lease clears when restore is observed");
    }

    private static void honorsNativeSmallKernelMtu() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        SamsungM11IwlanMtuPolicy.Result result = evaluate(policy, true, true, IFACE, IFINDEX,
                CID, true, 1310, 1500, 1500);
        expect(1310, 1310, 1310, result, "native 1310 kernel MTU is never raised");
        check(!policy.hasLease(), "no lease when native MTU is already below cap");
    }

    private static void externalKernelChangeRevokesLease() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        evaluate(policy, true, true, IFACE, IFINDEX, CID, true, 1500, 1500, 1500);
        SamsungM11IwlanMtuPolicy.Result external = evaluate(policy, true, false, IFACE,
                IFINDEX, CID, true, 1310, 1500, 1500);
        expect(1310, 1310, 1310, external,
                "external change to 1310 is preserved instead of restored over");
        check(!policy.hasLease(), "external kernel change revokes ownership");
    }

    private static void restoresTheObservedSourceBaseline() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        expect(1400, 1400, 1400, evaluate(policy, true, true, IFACE, IFINDEX, CID, true,
                1440, 1500, 1500), "1440 source baseline is capped to 1400");
        SamsungM11IwlanMtuPolicy.Result restore = evaluate(policy, true, false, IFACE, IFINDEX,
                CID, true, 1400, 1500, 1500);
        expect(1440, 1440, 1440, restore, "restore is bounded by 1440 source baseline");
    }

    private static void keepsFamilySpecificRoutes() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        SamsungM11IwlanMtuPolicy.Result capped = evaluate(policy, true, true, IFACE, IFINDEX,
                CID, true, 1500, 1500, 1280);
        expect(1400, 1400, 1280, capped, "asymmetric IPv4/IPv6 MTUs stay family specific");
        SamsungM11IwlanMtuPolicy.Result restore = evaluate(policy, true, false, IFACE, IFINDEX,
                CID, true, 1400, 1500, 1280);
        expect(1500, 1500, 1280, restore, "asymmetric routes restore within the link MTU");
    }

    private static void unknownKernelSnapshotHoldsAnOwnedResult() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        SamsungM11IwlanMtuPolicy.Result capped = evaluate(policy, true, true, IFACE, IFINDEX,
                CID, true, 1500, 1500, 1500);
        SamsungM11IwlanMtuPolicy.Result held = evaluate(policy, true, false, IFACE, -1, CID,
                false, -1, 1500, 1500);
        expect(capped.linkMtu, capped.routeMtuV4, capped.routeMtuV6, held,
                "unknown kernel does not discard or raise an active lease");
        check(held.heldForUnknownKernel, "result identifies a held interface snapshot");
    }

    private static void changedIdentityCannotRestoreAnotherBearer() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        evaluate(policy, true, true, IFACE, IFINDEX, CID, true, 1500, 1500, 1500);
        SamsungM11IwlanMtuPolicy.Result switchedCid = evaluate(policy, true, false, IFACE,
                IFINDEX, CID + 1, true, 1500, 1500, 1500);
        expect(1500, 1500, 1500, switchedCid, "new CID does not inherit old lease");
        check(!policy.hasLease(), "old lease is discarded on CID change");

        evaluate(policy, true, true, IFACE, IFINDEX, CID, true, 1500, 1500, 1500);
        SamsungM11IwlanMtuPolicy.Result switchedIfindex = evaluate(policy, true, false, IFACE,
                IFINDEX + 1, CID, true, 1500, 1500, 1500);
        expect(1500, 1500, 1500, switchedIfindex, "new ifindex does not inherit old lease");
        check(!policy.hasLease(), "old lease is discarded on ifindex change");
    }

    private static void staticScopeFailsClosed() {
        int wwan = 1;
        check(SamsungM11IwlanMtuPolicy.isApplicable("m11q", "legacy", "310260,", 0,
                true, true, wwan, wwan), "matching single-SIM M11 IMS scope accepted");
        check(SamsungM11IwlanMtuPolicy.isApplicable("m11q", "legacy", ",310260", 1,
                true, true, wwan, wwan), "operator in slot one matches phone one");
        check(!SamsungM11IwlanMtuPolicy.isApplicable("other", "legacy", "310260,", 0,
                true, true, wwan, wwan), "other device bypasses scope");
        check(!SamsungM11IwlanMtuPolicy.isApplicable("m11q", "legacy", "310260,", 0,
                true, false, wwan, wwan), "non-IMS APN bypasses scope");
        check(!SamsungM11IwlanMtuPolicy.isApplicable("m11q", "ap-assisted", "310260,", 0,
                true, true, wwan, wwan), "AP-assisted mode bypasses scope");
        check(!SamsungM11IwlanMtuPolicy.isApplicable("m11q", "legacy", "310260,310410", 0,
                true, true, wwan, wwan), "dual-SIM numeric values bypass scope");
        check(!SamsungM11IwlanMtuPolicy.isApplicable("m11q", "legacy", "310260,,310410", 0,
                true, true, wwan, wwan), "populated extra operator slot bypasses scope");
        check(!SamsungM11IwlanMtuPolicy.hasSingleOperatorForPhone("310260,", 1),
                "single operator must match the phone slot");
        check(!SamsungM11IwlanMtuPolicy.hasSingleOperatorForPhone("1234,", 0),
                "invalid operator numeric length bypasses scope");
        check(!SamsungM11IwlanMtuPolicy.isApplicable("m11q", "legacy", "310260,", 0,
                false, true, wwan, wwan), "invalid subscription bypasses scope");
        check(!SamsungM11IwlanMtuPolicy.isApplicable("m11q", "legacy", "310260,", 0,
                true, true, wwan, 2), "non-WWAN transport bypasses scope");
    }

    private static void invalidInputsAndLowKernelFailClosed() {
        SamsungM11IwlanMtuPolicy policy = new SamsungM11IwlanMtuPolicy();
        SamsungM11IwlanMtuPolicy.Result invalidV4 = evaluate(policy, true, true, IFACE,
                IFINDEX, CID, true, 1500, 67, 1500);
        expect(1500, 67, 1500, invalidV4, "invalid IPv4 effective MTU bypasses cap");
        check(!policy.hasLease(), "invalid typed MTUs do not acquire ownership");

        SamsungM11IwlanMtuPolicy.Result invalidV6 = evaluate(policy, true, true, IFACE,
                IFINDEX, CID, true, 1500, 1500, 1279);
        expect(1500, 1500, 1279, invalidV6, "invalid IPv6 effective MTU bypasses cap");

        SamsungM11IwlanMtuPolicy.Result lowKernel = evaluate(policy, true, true, IFACE,
                IFINDEX, CID, true, 576, 1500, 1500);
        expect(1500, 1500, 1500, lowKernel, "kernel below IPv6 minimum fails closed unchanged");
    }

    private static SamsungM11IwlanMtuPolicy.Result evaluate(SamsungM11IwlanMtuPolicy policy,
            boolean scope, boolean iwlan, String iface, int ifindex, int cid,
            boolean interfaceKnown, int kernel, int v4, int v6) {
        return policy.evaluate(scope, iwlan, iface, ifindex, cid, interfaceKnown, kernel, v4, v6);
    }

    private static void expect(int link, int v4, int v6,
            SamsungM11IwlanMtuPolicy.Result actual, String description) {
        if (actual.linkMtu != link || actual.routeMtuV4 != v4 || actual.routeMtuV6 != v6) {
            throw new AssertionError(description + ": expected link/v4/v6=" + link + "/" + v4
                    + "/" + v6 + " but got " + actual.linkMtu + "/" + actual.routeMtuV4 + "/"
                    + actual.routeMtuV6);
        }
    }

    private static void check(boolean condition, String description) {
        if (!condition) throw new AssertionError(description);
    }
}
