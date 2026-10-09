#!/usr/bin/env python3
"""Stage only a strictly verified BV1 IMS APK with original baseline backup."""

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

import build_imsservice_w2l_trial as BUILD
import stage_epdgservice_w2l_trial as EC2

APK_RELATIVE = "device/samsung/m11q/ims/proprietary/priv-app/imsservice/imsservice.apk"
CURRENT_EPDG_APK = "4c7cca55f8647fd49e4d91b0c600033fcbbab71292fb039c53cbf289c0fc63bc"


def stage(args):
    pins = BUILD.load_pins(args.pins)
    report = json.loads(args.build_report.read_text(encoding="utf-8"))
    output = report.get("output", {})
    if (report.get("status") != "PASS" or report.get("mode") != "strict"
            or report.get("observed_build_pins") != pins
            or any(output.get(key) is not True for key in
                   ("strict_pins_verified", "artifact_published", "all_redecoded_classes_verified", "unrelated_zip_entries_preserved"))
            or output.get("classes2_dex_sha256") != BUILD.BRIDGE_DEX):
        raise ValueError("complete matching strict BV1 report required")
    expected = pins["unsigned_apk_sha256"]
    if EC2.digest(args.apk) != expected:
        raise ValueError("BV1 candidate pin drift")
    root = args.android_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Android root must be a directory")
    prerequisites = {**EC2.SOURCE_HASHES, EC2.APK_RELATIVE: CURRENT_EPDG_APK,
                     "device/samsung/m11q/ims/proprietary/framework/imsmanager.jar": BUILD.IMSMANAGER_SHA256}
    for relative, digest in prerequisites.items():
        path = root / relative
        if not path.resolve(strict=True).is_relative_to(root) or EC2.digest(path) != digest:
            raise ValueError(f"BV1 prerequisite drift: {relative}")
    target = root / APK_RELATIVE
    if not target.resolve(strict=True).is_relative_to(root):
        raise ValueError("IMS target escapes source root")
    current = EC2.digest(target)
    if current not in {BUILD.BASE_APK, expected}:
        raise ValueError("unknown IMS source; refusing overwrite")
    if (args.backup.is_symlink() or not args.backup.parent.is_dir() or args.backup.parent.is_symlink()
            or args.backup.resolve(strict=False) in {target.resolve(), args.apk.resolve()}):
        raise ValueError("unsafe BV1 baseline backup")
    if args.backup.exists():
        if EC2.digest(args.backup) != BUILD.BASE_APK:
            raise ValueError("BV1 original IMS backup drift")
    elif current == BUILD.BASE_APK:
        with args.backup.open("xb") as output_stream, target.open("rb") as input_stream:
            shutil.copyfileobj(input_stream, output_stream)
    else:
        raise ValueError("trial already staged without original baseline backup")
    if EC2.digest(args.backup) != BUILD.BASE_APK:
        raise ValueError("BV1 backup verification failed")
    if current != expected:
        descriptor, name = tempfile.mkstemp(prefix=".bv1-", suffix=".apk", dir=target.parent)
        os.close(descriptor)
        temporary = Path(name)
        try:
            shutil.copyfile(args.apk, temporary)
            shutil.copymode(target, temporary)
            if EC2.digest(temporary) != expected or EC2.digest(target) != current:
                raise ValueError("BV1 source/candidate changed while staging")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    elif target.stat().st_mtime_ns < args.apk.stat().st_mtime_ns:
        os.utime(target, None)
    if EC2.digest(target) != expected:
        raise ValueError("staged BV1 hash drift")
    return {"status": "PASS", "already_staged": current == expected,
            "staged_apk_sha256": expected, "original_backup_sha256": BUILD.BASE_APK,
            "source_prerequisites_verified": True, "staged_mtime_ns": target.stat().st_mtime_ns,
            "rom_build_run": False, "runtime_validated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("android-root", "apk", "pins", "build-report", "backup"):
        parser.add_argument("--" + name, required=True, type=Path)
    try:
        print(json.dumps(stage(parser.parse_args()), sort_keys=True))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
