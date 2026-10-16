#!/usr/bin/env python3
"""Compile and run the standalone M11 VoWiFi MTU/audio policy harnesses."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
HELPERS = (
    ("src/java/com/android/internal/telephony/SamsungM11Mtu.java",
     "57adbc08887dc597b24c06c9c74e41044511e73a71188550d7e1eda977633706"),
    ("src/java/com/android/internal/telephony/data/SamsungM11IwlanMtuPolicy.java",
     "9bc4ff5c6c5d052749d2d17f16ade9be3d1b32c851098637466f2db390496df6"),
    ("src/com/android/server/telecom/SamsungImsAudioTransition.java",
     "9c3103595d8e56ccdf748977319d5083e6fabb2f9fdc3af825cb4822e4287463"),
)
CASES = (
    ("SamsungM11Mtu", "com.android.internal.telephony.SamsungM11MtuTest"),
    (
        "SamsungM11IwlanMtuPolicy",
        "com.android.internal.telephony.data.SamsungM11IwlanMtuPolicyTest",
    ),
    (
        "SamsungImsAudioTransition",
        "com.android.server.telecom.SamsungImsAudioTransitionTest",
    ),
)
HARNESS_NAMES = (
    "SamsungM11MtuTest.java",
    "SamsungM11IwlanMtuPolicyTest.java",
    "SamsungImsAudioTransitionTest.java",
)


def checked_source(root: Path, relative: str, expected_sha256: str) -> Path:
    path = root / relative
    if not path.is_file():
        raise ValueError(f"missing helper source: {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError(f"helper differs from the 2026-10-16 checkpoint: {path}")
    return path


def run(command: list[str], *, timeout: int = 60) -> None:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.returncode:
        raise subprocess.CalledProcessError(completed.returncode, command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--telephony-root",
        required=True,
        type=Path,
        help="WSL directory containing SamsungM11Mtu.java and SamsungM11IwlanMtuPolicy.java",
    )
    parser.add_argument(
        "--telecom-root",
        required=True,
        type=Path,
        help="WSL directory containing SamsungImsAudioTransition.java",
    )
    parser.add_argument(
        "--java-home",
        required=True,
        type=Path,
        help="JDK home with bin/javac and bin/java",
    )
    args = parser.parse_args()

    javac = args.java_home / "bin" / "javac"
    java = args.java_home / "bin" / "java"
    if not javac.is_file() or not java.is_file():
        parser.error(f"--java-home must contain bin/javac and bin/java: {args.java_home}")

    try:
        sources = [
            checked_source(args.telephony_root, *HELPERS[0]),
            checked_source(args.telephony_root, *HELPERS[1]),
            checked_source(args.telecom_root, *HELPERS[2]),
        ]
    except ValueError as error:
        parser.error(str(error))

    harnesses = [HERE / name for name in HARNESS_NAMES]
    missing = [path for path in harnesses if not path.is_file()]
    if missing:
        parser.error("missing harness source(s): " + ", ".join(map(str, missing)))

    with tempfile.TemporaryDirectory(prefix="m11q-vowifi-java-") as temp:
        output = Path(temp)
        run([str(javac), "-encoding", "UTF-8", "-d", str(output)]
            + [str(source) for source in sources + harnesses])
        for _, main_class in CASES:
            run([str(java), "-cp", str(output), main_class])
            print(f"{main_class}: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
