#!/usr/bin/env python3
"""Host harnesses and standalone API compilation only. Never build a ROM or contact a device."""
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SEH = ROOT / "platform/java/com/android/internal/telephony"
SA2 = ROOT / "platform/telecom/sa2"


def run(command):
    subprocess.run([str(value) for value in command], check=True)


def check(android, java_home, output):
    output.mkdir(parents=False, exist_ok=False)
    javac, java = java_home / "bin/javac", java_home / "bin/java"

    def compile_sources(label, sources, classpath=None):
        target = output / label
        target.mkdir()
        args = [javac, "-d", target]
        if classpath: args.extend(["-cp", ":".join(str(p) for p in classpath)])
        run(args + list(sources))
        return target

    sa2 = compile_sources("sa2-host", [SA2 / "SamsungImsAudioTransition.java",
                                      ROOT / "tests/SamsungImsAudioTransitionHostTest.java"])
    run([java, "-cp", sa2, "com.android.server.telecom.SamsungImsAudioTransitionHostTest"])
    transport_stubs = sorted((ROOT / "tests/seh_transport_host").rglob("*.java"))
    transport = compile_sources("seh-transport-host", transport_stubs +
                                [SEH / "M11SehApnPolicy.java", SEH / "M11SehRadioTransport.java"])
    run([java, "-cp", transport, "com.android.internal.telephony.M11SehTransportHostHarness"])
    bridge_stubs = sorted((ROOT / "tests/seh_bridge_host").rglob("*.java"))
    bridge_stubs += [p for p in transport_stubs if "/android/" in p.as_posix()
                     and p.name not in ("HwBinder.java", "IHwBinder.java")]
    helpers = sorted(SEH.glob("M11Seh*.java"))
    bridge = compile_sources("seh-bridge-host", bridge_stubs + helpers)
    run([java, "-cp", bridge, "com.android.internal.telephony.M11SehBridgeHostHarness"])

    intermediate = android / "out/soong/.intermediates"
    jars = [intermediate / relative for relative in (
        "frameworks/base/framework-minus-apex/android_common/turbine-combined/framework-minus-apex.jar",
        "libcore/core-libart/android_common_apex31/javac/core-libart.jar",
        "packages/services/Telecomm/Telecom/android_common/javac/Telecom.jar",
        "packages/modules/Connectivity/framework/framework-connectivity/android_common/javac/framework-connectivity.jar",
        "packages/modules/Connectivity/framework-t/framework-connectivity-t/android_common_apex30/javac/framework-connectivity-t.jar",
        "frameworks/opt/telephony/telephony-common/android_common/javac/telephony-common.jar")]
    if not all(path.is_file() for path in jars):
        raise ValueError("existing Android classpath missing; no build will be started")
    prefix = android / "packages/services/Telecomm/src/com/android/server/telecom"
    live_seh = android / "frameworks/opt/telephony/src/java/com/android/internal/telephony"
    compile_sources("android-api", [prefix / name for name in (
        "CallAudioManager.java", "CallAudioModeStateMachine.java",
        "SamsungImsAudioHandover.java", "SamsungImsAudioTransition.java")] +
        [live_seh / path.name for path in helpers], jars)
    print("PASS: live Telecom observer/adapter and SEH sources compile against existing Android 13 APIs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-root", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.android_root, args.java_home, args.output)
