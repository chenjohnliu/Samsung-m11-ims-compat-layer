#!/usr/bin/env python3
"""Compile and run bounded host-JVM behavior tests for M11SehRadioBridge."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


HARNESS = "com.android.internal.telephony.M11SehBridgeHostHarness"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--javac", default=os.environ.get("JAVAC", "javac"))
    parser.add_argument("--java", default=os.environ.get("JAVA", "java"))
    parser.add_argument("--class-dir", type=Path)
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    production_dir = repo / "platform" / "java" / "com" / "android" / "internal" / "telephony"
    production = [
        production_dir / "M11SehApnPolicy.java",
        production_dir / "M11SehRadioTransport.java",
        production_dir / "M11SehRadioBridge.java",
        production_dir / "M11SehProfilePublisher.java",
    ]
    transport_fakes = repo / "tests" / "seh_transport_host"
    bridge_fakes = repo / "tests" / "seh_bridge_host"
    reused = [
        path for path in sorted(transport_fakes.rglob("*.java"))
        if path.name not in {"HwBinder.java", "IHwBinder.java", "M11SehTransportHostHarness.java"}
    ]
    sources = production + reused + sorted(bridge_fakes.rglob("*.java"))
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        raise SystemExit("missing Java source(s): " + ", ".join(missing))

    temporary = None
    if args.class_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="m11-seh-bridge-")
        class_dir = Path(temporary.name)
    else:
        class_dir = args.class_dir.resolve()
        if class_dir.exists() and any(class_dir.iterdir()):
            raise SystemExit("--class-dir must be absent or empty: " + str(class_dir))
        class_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run([
            args.javac, "--release", "8", "-encoding", "UTF-8", "-d", str(class_dir),
            *map(str, sources),
        ], cwd=repo, check=True)
        subprocess.run([args.java, "-ea", "-cp", str(class_dir), HARNESS],
                       cwd=repo, check=True)
    finally:
        if temporary is not None:
            temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
