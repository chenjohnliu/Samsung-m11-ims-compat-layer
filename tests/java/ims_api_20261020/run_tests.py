#!/usr/bin/env python3
"""Run modeled host regressions against selected Android source files.

The runner extracts method bodies from the supplied source tree at runtime and
compiles them against minimal authored stubs. It does not build Android or
access a device.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


TELEPHONY_TEMPLATE = r'''import java.util.ArrayList;
import java.util.List;

final class RemoteException extends Exception { }
@interface CallState { }

final class ServiceState {
    static final int STATE_IN_SERVICE = 0;
    static final int STATE_OUT_OF_SERVICE = 1;
    static final int STATE_EMERGENCY_ONLY = 2;
    static final int STATE_POWER_OFF = 3;
    final int dataState;
    ServiceState(int dataState) { this.dataState = dataState; }
    int getDataRegistrationState() { return dataState; }
}

interface ITelephony {
    int getDataStateForSubId(int subId) throws RemoteException;
}
interface IPhoneSubInfo {
    String getSubscriberIdForUiccAppType(int subId, int appType, String pkg, String feature)
            throws RemoteException;
}

final class Compatibility {
    static boolean modernDataDisconnecting;
    static boolean isChangeEnabled(long ignored) { return modernDataDisconnecting; }
}

final class TelephonyManagerHarness {
    static final int DATA_DISCONNECTED = 0;
    static final int DATA_CONNECTED = 2;
    static final int DATA_DISCONNECTING = 4;
    static final long GET_DATA_STATE_R_VERSION = 1;
    private final int pinnedSubId;
    private final int defaultSubId;
    int requestedServiceSubId = -1;
    boolean renounceFine;
    boolean renounceCoarse;
    ServiceState serviceState;
    ITelephony telephony;
    IPhoneSubInfo subscriberInfo;
    String opPackage = "org.example.imsclient";
    String attributionTag = "ims-feature";
    int requestedDataSubId = -1;
    int requestedSubscriberSubId = -1;
    int requestedAppType = -1;
    String sentPackage;
    String sentAttribution;
    int callStateSubId = -1;
    String[] isimImpu = {"sip:ims@example.test"};

    TelephonyManagerHarness(int pinnedSubId, int defaultSubId) {
        this.pinnedSubId = pinnedSubId;
        this.defaultSubId = defaultSubId;
    }
    int getSubId() { return pinnedSubId >= 0 ? pinnedSubId : defaultSubId; }
    ServiceState getServiceStateForSubscriber(int subId, boolean fine, boolean coarse) {
        requestedServiceSubId = subId;
        renounceFine = fine;
        renounceCoarse = coarse;
        return serviceState;
    }
    ITelephony getITelephony() { return telephony; }
    IPhoneSubInfo getSubscriberInfoService() { return subscriberInfo; }
    String getOpPackageName() { return opPackage; }
    String getAttributionTag() { return attributionTag; }
    int getCallState(int subId) { callStateSubId = subId; return 2; }
    String[] getIsimImpu() { return isimImpu; }

@@DATA_SERVICE_NOARG@@
@@DATA_SERVICE_SUBID@@
@@SUBSCRIBER@@
@@CALL_STATE@@
@@ISIM@@
@@DATA_STATE@@

    private static int assertions;
    private static void check(boolean value, String message) {
        assertions++;
        if (!value) throw new AssertionError(message);
    }
    private static TelephonyManagerHarness manager(int pinned, int defaultSub) {
        return new TelephonyManagerHarness(pinned, defaultSub);
    }
    public static void main(String[] args) {
        List<String> passed = new ArrayList<>();

        TelephonyManagerHarness explicit = manager(1101, 2202);
        explicit.serviceState = new ServiceState(ServiceState.STATE_IN_SERVICE);
        check(explicit.semGetDataServiceState(9077) == ServiceState.STATE_IN_SERVICE,
                "explicit service-state result");
        check(explicit.requestedServiceSubId == 9077,
                "explicit non-default subId must be forwarded unchanged");
        check(explicit.renounceFine && explicit.renounceCoarse,
                "service-state query must renounce fine and coarse location");
        passed.add("explicit_non_default_subid_and_location_renunciation");

        TelephonyManagerHarness pinned = manager(3303, 2202);
        pinned.serviceState = new ServiceState(ServiceState.STATE_EMERGENCY_ONLY);
        check(pinned.semGetDataServiceState() == ServiceState.STATE_EMERGENCY_ONLY,
                "no-arg method uses pinned subscription");
        check(pinned.requestedServiceSubId == 3303, "pinned subId forwarded");
        TelephonyManagerHarness unpinned = manager(-1, 4404);
        unpinned.serviceState = new ServiceState(ServiceState.STATE_POWER_OFF);
        check(unpinned.semGetDataServiceState() == ServiceState.STATE_POWER_OFF,
                "no-arg method uses default subscription when unpinned");
        check(unpinned.requestedServiceSubId == 4404, "default subId forwarded");
        passed.add("noarg_pinned_and_default_subscription");

        TelephonyManagerHarness missingState = manager(1, 2);
        check(missingState.semGetDataServiceState(9077) == ServiceState.STATE_OUT_OF_SERVICE,
                "null state must fail closed to out of service");
        passed.add("null_service_state_out_of_service_fallback");

        TelephonyManagerHarness subscriber = manager(1, 2);
        subscriber.subscriberInfo = (sub, appType, pkg, feature) -> {
            subscriber.requestedSubscriberSubId = sub;
            subscriber.requestedAppType = appType;
            subscriber.sentPackage = pkg;
            subscriber.sentAttribution = feature;
            return "modeled-imsi";
        };
        check("modeled-imsi".equals(subscriber.getSubscriberIdForUiccAppType(9077, 5)),
                "subscriber ID response returned");
        check(subscriber.requestedSubscriberSubId == 9077 && subscriber.requestedAppType == 5,
                "subscriber subId and exact UICC app type forwarded");
        check(subscriber.opPackage.equals(subscriber.sentPackage)
                        && subscriber.attributionTag.equals(subscriber.sentAttribution),
                "op package and attribution forwarded");
        subscriber.subscriberInfo = null;
        check(subscriber.getSubscriberIdForUiccAppType(9077, 5) == null,
                "missing subscriber service returns null");
        subscriber.subscriberInfo = (sub, appType, pkg, feature) -> { throw new RemoteException(); };
        check(subscriber.getSubscriberIdForUiccAppType(9077, 5) == null,
                "subscriber RemoteException returns null");
        subscriber.subscriberInfo = (sub, appType, pkg, feature) -> { throw new NullPointerException(); };
        check(subscriber.getSubscriberIdForUiccAppType(9077, 5) == null,
                "subscriber NullPointerException returns null");
        subscriber.subscriberInfo = (sub, appType, pkg, feature) -> {
            throw new SecurityException("subscriber permission denied");
        };
        boolean subscriberDenied = false;
        try { subscriber.getSubscriberIdForUiccAppType(9077, 5); }
        catch (SecurityException expected) { subscriberDenied = true; }
        check(subscriberDenied, "subscriber SecurityException propagates");
        passed.add("subscriber_service_forwarding_null_errors_and_security");

        TelephonyManagerHarness aliases = manager(1, 2);
        check(aliases.semGetCallState(9077) == 2 && aliases.callStateSubId == 9077,
                "call-state alias forwards subscription ID");
        String[] expectedImpu = {"sip:modeled@example.test"};
        aliases.isimImpu = expectedImpu;
        check(aliases.semGetIsimImpu() == expectedImpu, "ISIM alias returns delegate result");
        passed.add("call_state_and_isim_aliases");

        TelephonyManagerHarness data = manager(1, 2);
        data.telephony = sub -> {
            data.requestedDataSubId = sub;
            return TelephonyManagerHarness.DATA_DISCONNECTING;
        };
        Compatibility.modernDataDisconnecting = false;
        check(data.semGetDataState(9077) == TelephonyManagerHarness.DATA_CONNECTED,
                "legacy change behavior remaps DISCONNECTING to CONNECTED");
        check(data.requestedDataSubId == 9077, "data-state explicit subId forwarded");
        Compatibility.modernDataDisconnecting = true;
        check(data.semGetDataState(9077) == TelephonyManagerHarness.DATA_DISCONNECTING,
                "modern change behavior passes DISCONNECTING through");
        data.telephony = null;
        check(data.semGetDataState(9077) == TelephonyManagerHarness.DATA_DISCONNECTED,
                "missing telephony service returns disconnected");
        data.telephony = sub -> { throw new RemoteException(); };
        check(data.semGetDataState(9077) == TelephonyManagerHarness.DATA_DISCONNECTED,
                "data RemoteException returns disconnected");
        data.telephony = sub -> { throw new NullPointerException(); };
        check(data.semGetDataState(9077) == TelephonyManagerHarness.DATA_DISCONNECTED,
                "data NullPointerException returns disconnected");
        data.telephony = sub -> { throw new SecurityException("data permission denied"); };
        boolean dataDenied = false;
        try { data.semGetDataState(9077); }
        catch (SecurityException expected) { dataDenied = true; }
        check(dataDenied, "data-state SecurityException propagates");
        passed.add("data_state_legacy_remap_service_errors_and_security");

        ControllerHarness controller = new ControllerHarness();
        IccRecords records = new IccRecords("selected-uicc-imsi");
        UiccPort port = new UiccPort(new UiccCardApplication(records));
        Phone phone = new Phone(9077, port);
        controller.phone = phone;
        check("selected-uicc-imsi".equals(controller.getSubscriberIdForUiccAppType(
                9077, 5, "org.example.imsclient", "ims-feature")),
                "controller returns IMSI from selected UICC application");
        check(port.requestedAppType == 5 && records.reads == 1,
                "controller requests exact app type and reads selected records");
        check(controller.lastPermissionMessage.equals("getSubscriberIdForUiccAppType"),
                "controller routes through named subscriber permission check");

        IccRecords mismatchRecords = new IccRecords("must-not-read");
        Phone mismatchPhone = new Phone(99, new UiccPort(new UiccCardApplication(mismatchRecords)));
        controller.phone = mismatchPhone;
        check(controller.getSubscriberIdForUiccAppType(9077, 5,
                "org.example.imsclient", null) == null, "subscription mismatch returns null");
        check(mismatchPhone.portReads == 0 && mismatchRecords.reads == 0,
                "subscription mismatch is rejected before UICC access");

        controller.phone = null;
        check(controller.getSubscriberIdForUiccAppType(9077, 5,
                "org.example.imsclient", null) == null, "missing phone returns null");
        controller.phone = new Phone(9077, null);
        check(controller.getSubscriberIdForUiccAppType(9077, 5,
                "org.example.imsclient", null) == null, "missing UICC port returns null");
        controller.phone = new Phone(9077, new UiccPort(null));
        check(controller.getSubscriberIdForUiccAppType(9077, 5,
                "org.example.imsclient", null) == null, "missing UICC application returns null");
        controller.phone = new Phone(9077, new UiccPort(new UiccCardApplication(null)));
        check(controller.getSubscriberIdForUiccAppType(9077, 5,
                "org.example.imsclient", null) == null, "missing ICC records returns null");

        IccRecords protectedRecords = new IccRecords("must-not-read");
        Phone protectedPhone = new Phone(9077,
                new UiccPort(new UiccCardApplication(protectedRecords)));
        controller.phone = protectedPhone;
        controller.allowed = false;
        boolean permissionDenied = false;
        try { controller.getSubscriberIdForUiccAppType(
                9077, 5, "org.example.imsclient", null); }
        catch (SecurityException expected) { permissionDenied = true; }
        check(permissionDenied && protectedPhone.portReads == 0 && protectedRecords.reads == 0,
                "modeled permission denial occurs before UICC access");
        controller.allowed = true;
        boolean packageDenied = false;
        try { controller.getSubscriberIdForUiccAppType(9077, 5, "wrong.package", null); }
        catch (SecurityException expected) { packageDenied = true; }
        check(packageDenied && protectedPhone.portReads == 0 && protectedRecords.reads == 0,
                "package identity rejection occurs before UICC access");
        passed.add("controller_uicc_selection_nulls_mismatch_and_pre_access_security");

        System.out.println("PASS: " + assertions + " assertions; " + String.join(",", passed));
        System.out.println("LIMIT: modeled host test of extracted method bodies; no real Binder,"
                + " framework permission enforcement, telephony service, or modem");
    }
}

interface PhoneAction<T> { T run(Phone phone); }
final class IccRecords {
    final String imsi;
    int reads;
    IccRecords(String imsi) { this.imsi = imsi; }
    String getIMSI() { reads++; return imsi; }
}
final class UiccCardApplication {
    final IccRecords records;
    UiccCardApplication(IccRecords records) { this.records = records; }
    IccRecords getIccRecords() { return records; }
}
final class UiccPort {
    final UiccCardApplication app;
    int requestedAppType = -1;
    UiccPort(UiccCardApplication app) { this.app = app; }
    UiccCardApplication getApplicationByType(int appType) {
        requestedAppType = appType;
        return app;
    }
}
final class Phone {
    final int subId;
    final UiccPort port;
    int portReads;
    Phone(int subId, UiccPort port) { this.subId = subId; this.port = port; }
    int getSubId() { return subId; }
    UiccPort getUiccPort() { portReads++; return port; }
}
final class ControllerHarness {
    Phone phone;
    boolean allowed = true;
    int packageChecks;
    String expectedPackage = "org.example.imsclient";
    String lastPermissionMessage;
    void enforceCallingPackageUidMatched(String pkg) {
        packageChecks++;
        if (!expectedPackage.equals(pkg)) throw new SecurityException("package mismatch");
    }
    <T> T callPhoneMethodForSubIdWithReadSubscriberIdentifiersCheck(
            int subId, String pkg, String feature, String message, PhoneAction<T> action) {
        lastPermissionMessage = message;
        if (!allowed) throw new SecurityException("modeled subscriber identifier permission denied");
        if (phone == null) return null;
        return action.run(phone);
    }
    public String getSubscriberIdForUiccAppType(int subId, int appType, String callingPackage,
            String callingFeatureId) {
@@CONTROLLER_BODY@@
    }
}
'''


PARCEL_STUB = r'''package android.os;
import java.util.ArrayList;
import java.util.List;
public class Parcel {
    public final List<Object> values = new ArrayList<>();
    public void writeInt(int value) { values.add(value); }
    public int readInt() { return (Integer) values.remove(0); }
    public void writeLong(long value) { values.add(value); }
    public long readLong() { return (Long) values.remove(0); }
    public void writeString(String value) { values.add(value); }
    public String readString() { return (String) values.remove(0); }
    public void writeStringList(List<String> value) {
        values.add(value == null ? null : new ArrayList<>(value));
    }
    @SuppressWarnings("unchecked")
    public void readStringList(List<String> value) {
        List<String> source = (List<String>) values.remove(0);
        if (source != null) value.addAll(source);
    }
}
'''

PARCELABLE_STUB = r'''package android.os;
public interface Parcelable {
    int describeContents();
    void writeToParcel(Parcel dest, int flags);
    interface Creator<T> { T createFromParcel(Parcel source); T[] newArray(int size); }
}
'''

CAPABILITIES_TEST = r'''package com.samsung.android.ims.options;
import android.os.Parcel;
import android.os.Parcelable;
import java.lang.reflect.Modifier;
import java.util.Arrays;
public final class SemCapabilitiesFactoryTest {
    private static int assertions;
    private static void check(boolean ok, String message) {
        assertions++;
        if (!ok) throw new AssertionError(message);
    }
    private static long parcelFeature(SemCapabilities value) {
        Parcel parcel = new Parcel();
        value.writeToParcel(parcel, 0);
        return (Long) parcel.values.get(1);
    }
    public static void main(String[] args) throws Exception {
        check(Modifier.isStatic(SemCapabilities.class.getMethod("getBuilder").getModifiers()),
                "getBuilder must be static");
        SemCapabilities.Builder firstBuilder = SemCapabilities.getBuilder();
        SemCapabilities.Builder secondBuilder = SemCapabilities.getBuilder();
        check(firstBuilder != secondBuilder, "factory must return a fresh builder");
        SemCapabilities first = firstBuilder.setFeature(0x1234L)
                .setAvailableFeatures(0x56L).setIsAvailable(true).build();
        SemCapabilities second = secondBuilder.build();
        SemCapabilities third = SemCapabilities.getBuilder().build();
        check(parcelFeature(first) == 0x1234L, "builder feature must be preserved");
        check(parcelFeature(second) == 0L && parcelFeature(third) == 0L,
                "fresh builders must start with default feature state");
        Parcel encoded = new Parcel();
        first.writeToParcel(encoded, 0);
        SemCapabilities decoded = SemCapabilities.CREATOR.createFromParcel(encoded);
        check(parcelFeature(decoded) == 0x1234L, "parcel round trip retains feature value");
        check(SemCapabilities.CREATOR.newArray(2).length == 2, "Parcelable creator newArray");
        System.out.println("PASS: " + assertions
                + " assertions; static factory, fresh state, builder values, Parcelable round trip");
    }
}
'''


SOURCE_CANDIDATES = {
    "telephony": (
        "frameworks/base/telephony/java/android/telephony/TelephonyManager.java",
        "frameworks_base/telephony/java/android/telephony/TelephonyManager.java",
    ),
    "controller": (
        "frameworks/opt/telephony/src/java/com/android/internal/telephony/PhoneSubInfoController.java",
        "frameworks_opt_telephony/src/java/com/android/internal/telephony/PhoneSubInfoController.java",
    ),
    "capabilities": (
        "frameworks/base/core/java/com/samsung/android/ims/options/SemCapabilities.java",
        "frameworks_base/core/java/com/samsung/android/ims/options/SemCapabilities.java",
    ),
}


def extract_method(source: str, signature_pattern: str) -> str:
    """Return one actual Java method declaration with a brace-balanced body."""
    match = re.search(signature_pattern, source, re.MULTILINE)
    if not match:
        raise ValueError(f"Required method not found: {signature_pattern}")
    opening = source.find("{", match.end())
    if opening < 0:
        raise ValueError("Method body opening brace not found")
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():pos + 1]
    raise ValueError("Unterminated method body")


def extract_body(source: str, signature_pattern: str) -> str:
    method = extract_method(source, signature_pattern)
    opening = method.find("{")
    return method[opening + 1:-1]


def source_path(root: Path, kind: str) -> Path:
    for relative in SOURCE_CANDIDATES[kind]:
        candidate = root / Path(relative)
        if candidate.is_file():
            return candidate
    choices = ", ".join(SOURCE_CANDIDATES[kind])
    raise FileNotFoundError(f"Could not find {kind} source under {root}; tried: {choices}")


def java_tools(java_home: Path) -> tuple[Path, Path]:
    executable_suffix = ".exe" if sys.platform == "win32" else ""
    javac = java_home / "bin" / f"javac{executable_suffix}"
    java = java_home / "bin" / f"java{executable_suffix}"
    if not javac.is_file() or not java.is_file():
        raise FileNotFoundError(f"Expected javac and java under {java_home / 'bin'}")
    return javac, java


def write_java(base: Path, relative: str, contents: str) -> Path:
    path = base / Path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def compile_and_run(source_root: Path, java_home: Path) -> dict:
    telephony_path = source_path(source_root, "telephony")
    controller_path = source_path(source_root, "controller")
    capabilities_path = source_path(source_root, "capabilities")
    telephony_source = telephony_path.read_text(encoding="utf-8")
    controller_source = controller_path.read_text(encoding="utf-8")

    methods = {
        "@@DATA_SERVICE_NOARG@@": extract_method(
            telephony_source, r"public\s+int\s+semGetDataServiceState\s*\(\s*\)"),
        "@@DATA_SERVICE_SUBID@@": extract_method(
            telephony_source, r"public\s+int\s+semGetDataServiceState\s*\(\s*int\s+subId\s*\)"),
        "@@SUBSCRIBER@@": extract_method(
            telephony_source, r"public\s+String\s+getSubscriberIdForUiccAppType\s*\(\s*int\s+subId\s*,\s*int\s+appType\s*\)"),
        "@@CALL_STATE@@": extract_method(
            telephony_source, r"public\s+@CallState\s+int\s+semGetCallState\s*\(\s*int\s+subId\s*\)"),
        "@@ISIM@@": extract_method(
            telephony_source, r"public\s+String\[\]\s+semGetIsimImpu\s*\(\s*\)"),
        "@@DATA_STATE@@": extract_method(
            telephony_source, r"public\s+int\s+semGetDataState\s*\(\s*int\s+subId\s*\)"),
        "@@CONTROLLER_BODY@@": extract_body(
            controller_source,
            r"public\s+String\s+getSubscriberIdForUiccAppType\s*\(\s*int\s+subId\s*,\s*int\s+appType\s*,\s*String\s+callingPackage\s*,\s*String\s+callingFeatureId\s*\)"),
    }
    harness_source = TELEPHONY_TEMPLATE
    for placeholder, actual_method in methods.items():
        harness_source = harness_source.replace(placeholder, actual_method)
    if "@@" in harness_source:
        raise ValueError("Unfilled method placeholder in host harness")

    javac, java = java_tools(java_home)
    result: dict = {
        "source_sha256": {
            "TelephonyManager.java": hashlib.sha256(telephony_path.read_bytes()).hexdigest(),
            "PhoneSubInfoController.java": hashlib.sha256(controller_path.read_bytes()).hexdigest(),
            "SemCapabilities.java": hashlib.sha256(capabilities_path.read_bytes()).hexdigest(),
        },
        "method_bodies_extracted": len(methods),
    }
    with tempfile.TemporaryDirectory(prefix="ims_api_host_") as temp_name:
        temp = Path(temp_name)
        harness_java = write_java(temp, "TelephonyBehaviorHarness.java", harness_source)
        parcel_java = write_java(temp, "android/os/Parcel.java", PARCEL_STUB)
        parcelable_java = write_java(temp, "android/os/Parcelable.java", PARCELABLE_STUB)
        capabilities_test_java = write_java(
            temp, "com/samsung/android/ims/options/SemCapabilitiesFactoryTest.java",
            CAPABILITIES_TEST)
        classes = temp / "classes"
        classes.mkdir()
        compile_result = subprocess.run(
            [str(javac), "-d", str(classes), str(harness_java), str(parcel_java),
             str(parcelable_java), str(capabilities_path), str(capabilities_test_java)],
            capture_output=True, text=True, check=False)
        if compile_result.returncode:
            raise RuntimeError("javac failed:\n" + compile_result.stdout + compile_result.stderr)

        telephony_result = subprocess.run(
            [str(java), "-cp", str(classes), "TelephonyManagerHarness"],
            capture_output=True, text=True, check=False)
        if telephony_result.returncode:
            raise RuntimeError("Telephony host regression failed:\n"
                               + telephony_result.stdout + telephony_result.stderr)
        capabilities_result = subprocess.run(
            [str(java), "-cp", str(classes),
             "com.samsung.android.ims.options.SemCapabilitiesFactoryTest"],
            capture_output=True, text=True, check=False)
        if capabilities_result.returncode:
            raise RuntimeError("SemCapabilities host regression failed:\n"
                               + capabilities_result.stdout + capabilities_result.stderr)
        result["telephony"] = telephony_result.stdout.strip().splitlines()
        result["sem_capabilities"] = capabilities_result.stdout.strip().splitlines()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path,
                        help="Android source tree root containing frameworks/base and frameworks/opt/telephony")
    parser.add_argument("--java-home", required=True, type=Path,
                        help="JDK home with bin/java and bin/javac")
    args = parser.parse_args(argv)
    try:
        result = compile_and_run(args.source_root, args.java_home)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"result": "PASS", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
