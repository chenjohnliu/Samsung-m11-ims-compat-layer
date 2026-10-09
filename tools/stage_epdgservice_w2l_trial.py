#!/usr/bin/env python3
"""Stage a strictly verified EC2 APK into a user's source tree without building."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

EC1_APK_SHA256 = "5eb14c66f5a6917de214d823f34b7dd453f6b22a64b91d74c733c89e23e23f98"
PREVIOUS_EC2_APK_SHA256 = "f75ae702513d3a0d183f3b109f49f98679e16b9aec5caafb0d766b89a4b3120e"
SOURCE_HASHES = {
    "frameworks/opt/telephony/src/java/com/android/internal/telephony/data/DataNetworkController.java":
        "6b8bf4490598d642be784beb55551c0af5f71c47c213134b2a5504918ae6895b",
    "device/samsung/m11q/overlay/packages/apps/CarrierConfig/res/xml/vendor.xml":
        "8b21b2d5511586e938da2ca03d0c7e2004384f519edabac6a44519151dfda4dd",
}
APK_RELATIVE = "device/samsung/m11q/ims/proprietary/priv-app/EpdgService/EpdgService.apk"


def digest(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected regular non-symlink file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(args):
    pins = json.loads(args.pins.read_text(encoding="utf-8"))
    report = json.loads(args.build_report.read_text(encoding="utf-8"))
    if (set(pins) != {"schema_version", "transformation_id", "classes_dex_sha256", "unsigned_apk_sha256"}
            or pins["schema_version"] != 1 or pins["transformation_id"] != "EC2-active-w2l-trial"
            or any(not isinstance(pins[key], str) or len(pins[key]) != 64
                   or any(c not in "0123456789abcdef" for c in pins[key])
                   for key in ("classes_dex_sha256", "unsigned_apk_sha256"))):
        raise ValueError("invalid EC2 final build pins")
    expected = pins["unsigned_apk_sha256"]
    if report.get("status") != "PASS" or report.get("mode") != "strict" or report.get("observed_build_pins") != pins:
        raise ValueError("a matching strict build report is required")
    output = report.get("output", {})
    if output.get("strict_pins_verified") is not True or output.get("artifact_published") is not True or output.get("all_redecoded_classes_verified") is not True:
        raise ValueError("trial build verification is incomplete")
    if digest(args.apk) != expected:
        raise ValueError("candidate APK pin drift")
    root = args.android_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Android source root must exist")
    for relative, wanted in SOURCE_HASHES.items():
        source = root / relative
        if not source.resolve(strict=True).is_relative_to(root) or digest(source) != wanted:
            raise ValueError(f"source experiment prerequisite hash drift: {relative}")
    target = root / APK_RELATIVE
    if not target.resolve(strict=True).is_relative_to(root):
        raise ValueError("ePDG target escapes Android source root")
    current = digest(target)
    if current not in {EC1_APK_SHA256, PREVIOUS_EC2_APK_SHA256, expected}:
        raise ValueError("unrecognized ePDG APK; refusing to overwrite")
    if args.backup.is_symlink() or not args.backup.parent.is_dir() or args.backup.parent.is_symlink():
        raise ValueError("unsafe backup path")
    if args.backup.resolve(strict=False) in {target.resolve(), args.apk.resolve()}:
        raise ValueError("backup cannot overlap the source or candidate")
    if args.backup.exists():
        if digest(args.backup) != EC1_APK_SHA256:
            raise ValueError("existing EC1 backup hash drift")
    elif current == EC1_APK_SHA256:
        with args.backup.open("xb") as stream, target.open("rb") as original:
            shutil.copyfileobj(original, stream)
    else:
        raise ValueError("already staged trial has no verified EC1 backup")
    if digest(args.backup) != EC1_APK_SHA256:
        raise ValueError("EC1 backup verification failed")
    mtime_refreshed = False
    if current != expected:
        descriptor, name = tempfile.mkstemp(prefix=".ec2-", suffix=".apk", dir=target.parent)
        os.close(descriptor)
        temporary = Path(name)
        try:
            shutil.copyfile(args.apk, temporary)
            # Ninja compares input mtimes. Preserve permissions, NOT the old
            # EC1 timestamp, or an incremental ROM build can silently reuse EC1.
            shutil.copymode(target, temporary)
            if digest(temporary) != expected or digest(target) != current:
                raise ValueError("source changed while staging trial")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    elif target.stat().st_mtime_ns < args.apk.stat().st_mtime_ns:
        # Repair the previously staged EC2 whose content is correct but whose
        # EC1 timestamp was preserved. Do not replace bytes or invalidate an
        # already-current source on every idempotent invocation.
        if digest(target) != expected:
            raise ValueError("source changed while refreshing trial timestamp")
        os.utime(target, None)
        mtime_refreshed = True
    if digest(target) != expected:
        raise ValueError("staged trial hash drift")
    return {"status": "PASS", "already_staged": current == expected,
            "source_mtime_refreshed": mtime_refreshed,
            "staged_mtime_ns": target.stat().st_mtime_ns,
            "staged_apk_sha256": expected, "ec1_backup_sha256": EC1_APK_SHA256,
            "source_prerequisites_verified": True, "rom_build_run": False, "runtime_validated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("android-root", "apk", "pins", "build-report", "backup"):
        parser.add_argument("--" + option, type=Path, required=True)
    try:
        result = stage(parser.parse_args())
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
