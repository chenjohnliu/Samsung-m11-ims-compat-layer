#!/usr/bin/env python3
"""Read-only gate for the ROM-packaged ePDG APK, independent of signing."""

import argparse
import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ec2_artifact_builder", ROOT / "tools/build_epdgservice_w2l_trial.py")
BUILDER = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = BUILDER
spec.loader.exec_module(BUILDER)


def verify(apk, pins_path):
    pins = BUILDER.load_pins(pins_path)
    if apk.is_symlink() or not apk.is_file():
        raise ValueError("packaged APK must be a regular non-symlink file")
    data = apk.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        dex_entries = [name for name in names if name.startswith("classes") and name.endswith(".dex")]
        if dex_entries != ["classes.dex"]:
            raise ValueError("unexpected packaged ePDG DEX inventory")
        digest = hashlib.sha256(archive.read("classes.dex")).hexdigest()
    if digest != pins["classes_dex_sha256"]:
        raise ValueError(f"NOT EC2: packaged DEX {digest}, expected {pins['classes_dex_sha256']}; do not flash/test this artifact")
    return {"status": "PASS", "apk_sha256": hashlib.sha256(data).hexdigest(),
            "classes_dex_sha256": digest, "ec2_dex_verified": True,
            "signature_verified": False, "runtime_validated": False, "rom_build_run": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--pins", type=Path, default=ROOT / "devices/m11q/epdgservice-w2l-trial-build.json")
    args = parser.parse_args()
    try:
        result = verify(args.apk, args.pins)
    except (OSError, ValueError, BUILDER.BuildError, zipfile.BadZipFile, KeyError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
