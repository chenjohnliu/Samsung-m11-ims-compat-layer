#!/usr/bin/env python3
"""Compile and run bounded host-JVM tests for M11 SEH policy/transport.

This intentionally compiles only the two production Java sources named below plus
clean-room android.os fixtures. It does not compile the bridge or invoke Android's
build system.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


HARNESS_CLASS = "com.android.internal.telephony.M11SehTransportHostHarness"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--javac", default=os.environ.get("JAVAC", "javac"),
                        help="Java compiler executable (JDK 11 is supported)")
    parser.add_argument("--java", default=os.environ.get("JAVA", "java"),
                        help="Java runtime executable")
    parser.add_argument("--class-dir", type=Path,
                        help="Keep compiled classes in this directory")
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    fixtures = repo / "tests" / "seh_transport_host"
    production = [
        repo / "platform" / "java" / "com" / "android" / "internal" / "telephony"
        / "M11SehApnPolicy.java",
        repo / "platform" / "java" / "com" / "android" / "internal" / "telephony"
        / "M11SehRadioTransport.java",
    ]
    sources = production + sorted(fixtures.rglob("*.java"))
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise SystemExit("missing Java source(s): " + ", ".join(missing))

    temporary = None
    if args.class_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="m11-seh-transport-")
        class_dir = Path(temporary.name)
    else:
        class_dir = args.class_dir.resolve()
        if class_dir.exists() and any(class_dir.iterdir()):
            raise SystemExit("--class-dir must be absent or empty: " + str(class_dir))
        class_dir.mkdir(parents=True, exist_ok=True)

    try:
        compile_command = [
            args.javac,
            "--release", "8",
            "-encoding", "UTF-8",
            "-d", str(class_dir),
            *map(str, sources),
        ]
        subprocess.run(compile_command, cwd=repo, check=True)
        subprocess.run(
            [args.java, "-ea", "-cp", str(class_dir), HARNESS_CLASS],
            cwd=repo,
            check=True,
        )
    finally:
        if temporary is not None:
            temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
