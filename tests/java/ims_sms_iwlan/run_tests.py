#!/usr/bin/env python3
"""Compile extracted SMS-over-IWLAN bridge methods against small host stubs.

This exercises actual method and constructor bodies from the selected bridge
sources. Framework and Samsung objects are modeled; this is not an Android
build or a device test.
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


SOURCES = {
    "ModernVoiceContext.java": "com/sec/internal/google/ModernVoiceContext.java",
    "GoogleModernMmTelFeature.java": "com/sec/internal/google/GoogleModernMmTelFeature.java",
    "ModernSmsBridge.java": "com/sec/internal/google/ModernSmsBridge.java",
}


def extract_method(source: str, pattern: str) -> str:
    match = re.search(pattern, source, re.MULTILINE)
    if not match:
        raise ValueError(f"Required source method not found: {pattern}")
    opening = source.find("{", match.end())
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():pos + 1]
    raise ValueError(f"Unterminated method: {pattern}")


def extract_declaration(source: str, pattern: str) -> str:
    match = re.search(pattern, source, re.MULTILINE)
    if not match:
        raise ValueError(f"Required source declaration not found: {pattern}")
    return match.group(0)


def source_root(value: Path) -> Path:
    if (value / "com/sec/internal/google/ModernVoiceContext.java").is_file():
        return value
    candidate = value / "bridge/java"
    if (candidate / "com/sec/internal/google/ModernVoiceContext.java").is_file():
        return candidate
    raise FileNotFoundError(
        "--bridge-root must be the repository root or its bridge/java directory")


def java_tools(java_home: Path) -> tuple[Path, Path]:
    suffix = ".exe" if sys.platform == "win32" else ""
    javac, java = java_home / "bin" / f"javac{suffix}", java_home / "bin" / f"java{suffix}"
    if not javac.is_file() or not java.is_file():
        raise FileNotFoundError(f"Expected java and javac under {java_home / 'bin'}")
    return javac, java


HARNESS = r'''import java.util.*;

final class SmsIwlanHostTest {
    static final class ModernVoiceContext {
        static final String TAG = "host";
        @@RETAINED_FIELDS@@
        final int phoneId;
        final int subscription;
        final Context app;
        final Registration registration = new Registration();
        GoogleImsService backend;
        int serviceId = -1;
        boolean disposed, voiceEnabled, wfcVoiceEnabled, smsEnabled, wfcSmsEnabled;
        boolean registered, nativeVoice;
        int registrationTech = -1;
        boolean activePair = true;
        static ImsReasonInfo reason(String message) { return new ImsReasonInfo(); }
        boolean activePair() { return activePair; }
        boolean voiceEnabledForTech(int tech) {
            if (tech == ImsRegistrationImplBase.REGISTRATION_TECH_LTE) return voiceEnabled;
            if (tech == ImsRegistrationImplBase.REGISTRATION_TECH_IWLAN) return wfcVoiceEnabled;
            return false;
        }
        void setVoiceEnabled(int tech, boolean enabled) {
            if (tech == ImsRegistrationImplBase.REGISTRATION_TECH_LTE) voiceEnabled = enabled;
            else if (tech == ImsRegistrationImplBase.REGISTRATION_TECH_IWLAN) wfcVoiceEnabled = enabled;
            else return;
            retainEnablement();
        }
        void publish() { }
        @@CONSTRUCTOR@@
        @@SET_SMS@@
        @@RETAIN@@
        @@SMS_ENABLED_FOR_TECH@@
        @@SMS_AVAILABLE@@
        @@HAS_NORMAL_SMS_REGISTRATION@@
        @@IS_CURRENT_SMS_TRANSPORT@@
    }

    static final class GoogleModernMmTelFeature {
        static final int SMS = MmTelCapabilities.CAPABILITY_TYPE_SMS;
        static final int VOICE = MmTelCapabilities.CAPABILITY_TYPE_VOICE;
        final ModernVoiceContext owner;
        GoogleModernMmTelFeature(ModernVoiceContext owner) { this.owner = owner; }
        @@QUERY_CAPABILITY@@
        @@CHANGE@@
    }

    static final class ModernSmsBridge {
        final ModernVoiceContext owner;
        boolean ready;
        boolean disposed;
        GoogleImsService attachedBackend;
        ModernSmsBridge(ModernVoiceContext owner) { this.owner = owner; }
        @@SUPPORTS_PHONE@@
        @@BRIDGE_AVAILABLE@@
        static String scaHex(String value) { return value == null ? null : "encoded:" + value; }
        @@PROFILE_SMSC@@
    }

    static int assertions;
    static void check(boolean value, String message) {
        assertions++;
        if (!value) throw new AssertionError(message);
    }
    static ModernVoiceContext owner(int phoneId, int subId, int tech) {
        ModernVoiceContext owner = new ModernVoiceContext(new Context(), phoneId, subId);
        owner.registrationTech = tech;
        return owner;
    }
    static ImsRegistration reg(int phone, int rat, boolean smsip,
            boolean emergency, int cmc, String psi) {
        return new ImsRegistration(phone, rat, smsip, emergency, cmc, psi);
    }
    static void resetRegistrations(ImsRegistration... registrations) {
        ImsRegistry.registrations.clear();
        ImsRegistry.registrations.addAll(Arrays.asList(registrations));
    }
    static void resetRetention() {
        ModernVoiceContext.retainedPhoneId = -1;
        ModernVoiceContext.retainedSubscription = -1;
        ModernVoiceContext.retainedSmsEnabled = true;
        ModernVoiceContext.retainedWfcSmsEnabled = true;
    }

    public static void main(String[] args) {
        int LTE = ImsRegistrationImplBase.REGISTRATION_TECH_LTE;
        int IWLAN = ImsRegistrationImplBase.REGISTRATION_TECH_IWLAN;

        ModernVoiceContext lte = owner(0, 100, LTE);
        resetRegistrations();
        check(!lte.hasNormalSmsRegistration(), "missing registration is excluded");
        resetRegistrations(reg(0, 13, true, false, 0, "sca-lte"));
        check(lte.hasNormalSmsRegistration(), "LTE registration over RAT 13 qualifies");
        resetRegistrations(reg(0, 13, false, false, 0, "sca"));
        check(!lte.hasNormalSmsRegistration(), "missing smsip is excluded");
        resetRegistrations(reg(1, 13, true, false, 0, "sca"));
        check(!lte.hasNormalSmsRegistration(), "wrong owner phone is excluded");
        resetRegistrations(reg(0, 13, true, true, 0, "sca"));
        check(!lte.hasNormalSmsRegistration(), "emergency registration is excluded");
        resetRegistrations(reg(0, 13, true, false, 1, "sca"));
        check(!lte.hasNormalSmsRegistration(), "nonzero CMC registration is excluded");
        resetRegistrations(reg(0, 18, true, false, 0, "sca"));
        check(!lte.hasNormalSmsRegistration(), "stale IWLAN snapshot is excluded under LTE");

        ModernVoiceContext iwlan = owner(0, 100, IWLAN);
        resetRegistrations(reg(0, 18, true, false, 0, "sca-iwlan"));
        check(iwlan.hasNormalSmsRegistration(), "IWLAN registration over RAT 18 qualifies");
        resetRegistrations(reg(0, 13, true, false, 0, "sca"));
        check(!iwlan.hasNormalSmsRegistration(), "stale LTE snapshot is excluded under IWLAN");
        ModernVoiceContext unknown = owner(0, 100, 77);
        resetRegistrations(reg(0, 18, true, false, 0, "sca"));
        check(!unknown.hasNormalSmsRegistration(), "unsupported registration technology is excluded");
        check(!unknown.isCurrentSmsTransport(13) && !unknown.isCurrentSmsTransport(18),
                "unsupported technology matches no SMS transport");

        resetRetention();
        ModernVoiceContext settings = owner(0, 100, LTE);
        settings.setSmsEnabled(LTE, false);
        check(!settings.smsEnabledForTech(LTE) && settings.smsEnabledForTech(IWLAN),
                "LTE disable leaves IWLAN enabled");
        settings.setSmsEnabled(IWLAN, false);
        check(!settings.smsEnabledForTech(LTE) && !settings.smsEnabledForTech(IWLAN),
                "IWLAN disable leaves LTE state unchanged");
        settings.setSmsEnabled(77, false);
        check(!settings.smsEnabledForTech(LTE) && !settings.smsEnabledForTech(IWLAN),
                "unsupported capability update does not mutate either flag");

        GoogleModernMmTelFeature feature = new GoogleModernMmTelFeature(settings);
        check(feature.change(new CapabilityChangeRequest.CapabilityPair(GoogleModernMmTelFeature.SMS, LTE), true),
                "LTE SMS capability update accepted");
        check(feature.change(new CapabilityChangeRequest.CapabilityPair(GoogleModernMmTelFeature.SMS, IWLAN), false),
                "IWLAN SMS capability update accepted");
        check(!feature.change(new CapabilityChangeRequest.CapabilityPair(GoogleModernMmTelFeature.SMS, 77), true),
                "unsupported SMS technology update rejected");
        check(feature.queryCapabilityConfiguration(GoogleModernMmTelFeature.SMS, LTE),
                "LTE SMS capability query uses LTE flag");
        check(!feature.queryCapabilityConfiguration(GoogleModernMmTelFeature.SMS, IWLAN),
                "IWLAN SMS capability query uses IWLAN flag");
        check(!feature.queryCapabilityConfiguration(GoogleModernMmTelFeature.SMS, 77),
                "unsupported SMS capability query is false");

        resetRetention();
        ModernVoiceContext retained = owner(1, 202, LTE);
        retained.setSmsEnabled(LTE, false);
        retained.setSmsEnabled(IWLAN, true);
        ModernVoiceContext samePair = owner(1, 202, IWLAN);
        check(!samePair.smsEnabledForTech(LTE) && samePair.smsEnabledForTech(IWLAN),
                "same phone/sub recreation restores both independent SMS flags");
        ModernVoiceContext newPair = owner(0, 101, LTE);
        check(newPair.smsEnabledForTech(LTE) && newPair.smsEnabledForTech(IWLAN),
                "new phone/sub pair defaults enabled without old-pair leakage");

        resetRetention();
        ModernVoiceContext active = owner(0, 300, IWLAN);
        active.backend = new GoogleImsService(); active.serviceId = 1; active.registered = true;
        resetRegistrations(reg(0, 18, true, false, 0, "sca"));
        check(active.smsAvailable(), "active SMS flag and IWLAN registration permit availability");
        active.setSmsEnabled(IWLAN, false);
        check(!active.smsAvailable(), "active IWLAN SMS disable gates availability");
        active.setSmsEnabled(IWLAN, true);
        active.backend = null;
        check(!active.smsAvailable(), "missing backend gates availability");
        active.backend = new GoogleImsService(); active.serviceId = -1;
        check(!active.smsAvailable(), "invalid service ID gates availability");
        active.serviceId = 1; active.registered = false;
        check(!active.smsAvailable(), "unregistered owner gates availability");
        active.registered = true; active.disposed = true;
        check(!active.smsAvailable(), "disposed owner gates availability");

        active.disposed = false;
        ModernSmsBridge bridge = new ModernSmsBridge(active);
        bridge.ready = true; bridge.attachedBackend = active.backend;
        check(bridge.available(), "ready bridge with owner and active pair is available");
        bridge.ready = false;
        check(!bridge.available(), "bridge not ready gates availability");
        bridge.ready = true; bridge.disposed = true;
        check(!bridge.available(), "disposed bridge gates availability");
        bridge.disposed = false; bridge.attachedBackend = null;
        check(!bridge.available(), "missing attached backend gates availability");
        bridge.attachedBackend = active.backend; active.activePair = false;
        check(!bridge.available(), "non-owner active pair gates availability");
        active.activePair = true;

        ModernVoiceContext scaOwner = owner(0, 300, IWLAN);
        ModernSmsBridge scaBridge = new ModernSmsBridge(scaOwner);
        resetRegistrations(reg(0, 18, true, false, 0, "iwlan-profile"));
        check("encoded:iwlan-profile".equals(scaBridge.profileSmsc()),
                "profile SMSC uses eligible current IWLAN registration");
        resetRegistrations(reg(0, 13, true, false, 0, "stale-lte"));
        check(scaBridge.profileSmsc() == null, "profile SMSC excludes stale LTE under IWLAN");
        resetRegistrations(reg(1, 18, true, false, 0, "wrong-phone"));
        check(scaBridge.profileSmsc() == null, "profile SMSC excludes wrong phone");
        resetRegistrations(reg(0, 18, false, false, 0, "no-smsip"));
        check(scaBridge.profileSmsc() == null, "profile SMSC excludes missing smsip");
        resetRegistrations(reg(0, 18, true, true, 0, "emergency"));
        check(scaBridge.profileSmsc() == null, "profile SMSC excludes emergency profile");
        resetRegistrations(reg(0, 18, true, false, 2, "cmc"));
        check(scaBridge.profileSmsc() == null, "profile SMSC excludes nonzero CMC profile");

        System.out.println("PASS: " + assertions + " assertions; extracted bridge methods and constructor");
        System.out.println("LIMIT: host stubs model Android/Samsung objects and registry state;"
                + " no real framework, Binder, modem, Android build, or device validation");
    }
}

final class Context { }
final class ImsReasonInfo { }
final class Registration { void onDeregistered(ImsReasonInfo ignored) { } }
final class GoogleImsService { }
final class ImsRegistrationImplBase {
    static final int REGISTRATION_TECH_LTE = 0;
    static final int REGISTRATION_TECH_IWLAN = 1;
}
final class MmTelCapabilities {
    static final int CAPABILITY_TYPE_SMS = 1;
    static final int CAPABILITY_TYPE_VOICE = 2;
}
final class CapabilityChangeRequest {
    static final class CapabilityPair {
        final int capability, radioTech;
        CapabilityPair(int capability, int radioTech) { this.capability = capability; this.radioTech = radioTech; }
        int getCapability() { return capability; }
        int getRadioTech() { return radioTech; }
    }
}
final class ImsProfile {
    final boolean emergency;
    final int cmc;
    final String smsPsi;
    ImsProfile(boolean emergency, int cmc, String smsPsi) {
        this.emergency = emergency; this.cmc = cmc; this.smsPsi = smsPsi;
    }
    boolean hasEmergencySupport() { return emergency; }
    int getCmcType() { return cmc; }
    String getSmsPsi() { return smsPsi; }
}
final class ImsRegistration {
    final int phone, rat;
    final boolean smsip;
    final ImsProfile profile;
    ImsRegistration(int phone, int rat, boolean smsip, boolean emergency, int cmc, String psi) {
        this.phone = phone; this.rat = rat; this.smsip = smsip;
        this.profile = new ImsProfile(emergency, cmc, psi);
    }
    int getPhoneId() { return phone; }
    int getCurrentRat() { return rat; }
    boolean hasService(String service) { return smsip && "smsip".equals(service); }
    ImsProfile getImsProfile() { return profile; }
}
final class RegistrationManager {
    List<ImsRegistration> getRegistrationInfo() { return ImsRegistry.registrations; }
}
final class ImsRegistry {
    static final List<ImsRegistration> registrations = new ArrayList<>();
    static RegistrationManager getRegistrationManager() { return new RegistrationManager(); }
}
final class GoogleModernImsService {
    static boolean isSingleActivePair(Context app, int phone, int sub) { return true; }
}
final class Log {
    static int i(String tag, String message) { return 0; }
    static int w(String tag, String message, Throwable error) { return 0; }
    static int e(String tag, String message, Throwable error) { return 0; }
}
'''


def compile_and_run(bridge_root: Path, java_home: Path) -> dict:
    root = source_root(bridge_root)
    source = {name: (root / relative).read_text(encoding="utf-8")
              for name, relative in SOURCES.items()}
    voice, feature, sms = (source[name] for name in SOURCES)
    pieces = {}
    retained_patterns = [
        r"private static int retainedPhoneId = -1;",
        r"private static int retainedSubscription = -1;",
        r"private static volatile boolean retainedVoiceEnabled;",
        r"private static volatile boolean retainedWfcVoiceEnabled;",
        r"private static volatile boolean retainedSmsEnabled = true;",
        r"private static volatile boolean retainedWfcSmsEnabled = true;",
    ]
    pieces["@@RETAINED_FIELDS@@"] = "\n".join(
        extract_declaration(voice, pattern) for pattern in retained_patterns)
    method_specs = {
        "@@CONSTRUCTOR@@": (voice, r"ModernVoiceContext\s*\(\s*Context app,\s*int phoneId,\s*int subscription\s*\)"),
        "@@SET_SMS@@": (voice, r"void\s+setSmsEnabled\s*\(\s*int tech,\s*boolean enabled\s*\)"),
        "@@RETAIN@@": (voice, r"private\s+void\s+retainEnablement\s*\(\s*\)"),
        "@@SMS_ENABLED_FOR_TECH@@": (voice, r"boolean\s+smsEnabledForTech\s*\(\s*int tech\s*\)"),
        "@@SMS_AVAILABLE@@": (voice, r"boolean\s+smsAvailable\s*\(\s*\)"),
        "@@HAS_NORMAL_SMS_REGISTRATION@@": (voice, r"boolean\s+hasNormalSmsRegistration\s*\(\s*\)"),
        "@@IS_CURRENT_SMS_TRANSPORT@@": (voice, r"boolean\s+isCurrentSmsTransport\s*\(\s*int rat\s*\)"),
        "@@QUERY_CAPABILITY@@": (feature, r"public\s+boolean\s+queryCapabilityConfiguration\s*\(\s*int capability,\s*int tech\s*\)"),
        "@@CHANGE@@": (feature, r"private\s+boolean\s+change\s*\(\s*CapabilityChangeRequest\.CapabilityPair pair,\s*boolean enabled\s*\)"),
        "@@SUPPORTS_PHONE@@": (sms, r"private\s+boolean\s+supportsPhone\s*\(\s*\)"),
        "@@BRIDGE_AVAILABLE@@": (sms, r"boolean\s+available\s*\(\s*\)"),
        "@@PROFILE_SMSC@@": (sms, r"private\s+String\s+profileSmsc\s*\(\s*\)"),
    }
    for placeholder, (text, pattern) in method_specs.items():
        pieces[placeholder] = extract_method(text, pattern)
    harness = HARNESS
    for placeholder, method in pieces.items():
        harness = harness.replace(placeholder, method)
    if "@@" in harness:
        raise ValueError("Unfilled harness placeholder")
    javac, java = java_tools(java_home)
    hashes = {name: hashlib.sha256((root / relative).read_bytes()).hexdigest()
              for name, relative in SOURCES.items()}
    with tempfile.TemporaryDirectory(prefix="ims_sms_iwlan_") as temp_name:
        temp = Path(temp_name)
        source_file = temp / "SmsIwlanHostTest.java"
        source_file.write_text(harness, encoding="utf-8")
        classes = temp / "classes"
        classes.mkdir()
        compiled = subprocess.run([str(javac), "-d", str(classes), str(source_file)],
                                  text=True, capture_output=True, check=False)
        if compiled.returncode:
            raise RuntimeError("javac failed:\n" + compiled.stdout + compiled.stderr)
        run = subprocess.run([str(java), "-cp", str(classes), "SmsIwlanHostTest"],
                             text=True, capture_output=True, check=False)
        if run.returncode:
            raise RuntimeError("host regression failed:\n" + run.stdout + run.stderr)
    return {"source_sha256": hashes, "extracted_methods": len(method_specs),
            "output": run.stdout.strip().splitlines()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-root", required=True, type=Path,
                        help="repository root or bridge/java directory")
    parser.add_argument("--java-home", required=True, type=Path,
                        help="JDK home containing bin/java and bin/javac")
    args = parser.parse_args()
    try:
        result = compile_and_run(args.bridge_root, args.java_home)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"result": "PASS", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
