#!/usr/bin/env python3
"""Stage or roll back the pinned LG2 ePDG prefix repair; never builds a ROM."""

import argparse
import json
import shutil
from pathlib import Path

import legacy_epdg_prefix_compat as LG2
import legacy_iwlan_trial as LEG1

APK_RELATIVE = "device/samsung/m11q/ims/proprietary/priv-app/EpdgService/EpdgService.apk"
BASE_APK = "4c7cca55f8647fd49e4d91b0c600033fcbbab71292fb039c53cbf289c0fc63bc"


def stage(args):
    root = LEG1.source_root(args.android_root)
    pins = LG2.load_pins(args.pins)
    wanted = pins["unsigned_apk_sha256"]
    original, candidate = LEG1.bundle(args.state_dir)
    for relative in original:
        if LEG1.regular(root / relative).read_bytes() != candidate[relative]:
            raise ValueError("LG2 requires the exact LEG1 boot configuration")
    for relative, digest in LEG1.PREREQUISITES.items():
        if relative != APK_RELATIVE and LEG1.sha(LEG1.regular(root / relative).read_bytes()) != digest:
            raise ValueError(f"LG2 source prerequisite drift: {relative}")
    target = LEG1.regular(root / APK_RELATIVE)
    current = target.read_bytes()
    current_hash = LEG1.sha(current)
    if current_hash not in {BASE_APK, wanted}:
        raise ValueError("unknown source ePDG APK; refusing to overwrite")
    backup = LEG1.safe(args.backup)
    if not backup.parent.is_dir() or backup in {target, LEG1.safe(args.apk)}:
        raise ValueError("unsafe or overlapping backup path")
    if backup.exists():
        if LEG1.sha(LEG1.regular(backup).read_bytes()) != BASE_APK:
            raise ValueError("LG2 backup drift")
    elif current_hash != BASE_APK:
        raise ValueError("LG2 already staged without its verified EC2-r2 backup")
    if args.rollback:
        if not backup.exists():
            raise ValueError("rollback requires the verified EC2-r2 backup")
        replacement = backup.read_bytes()
    else:
        report = json.loads(LEG1.regular(args.build_report).read_text(encoding="utf-8"))
        output = report.get("output", {})
        if (report.get("status") != "PASS" or report.get("mode") != "strict"
                or report.get("observed_build_pins") != pins
                or any(output.get(key) is not True for key in (
                    "strict_pins_verified", "artifact_published",
                    "all_redecoded_classes_verified", "unrelated_zip_entries_preserved"))):
            raise ValueError("matching complete strict LG2 build report required")
        apk = LEG1.regular(args.apk)
        LG2.verify_apk(apk, args.pins)
        replacement = apk.read_bytes()
        if LEG1.sha(replacement) != wanted:
            raise ValueError("unsigned LG2 APK pin drift")
        if not backup.exists():
            with backup.open("xb") as stream, target.open("rb") as source:
                shutil.copyfileobj(source, stream)
            if LEG1.sha(backup.read_bytes()) != BASE_APK:
                raise ValueError("backup verification failed")
    if current != replacement:
        LEG1.atomic_replace(target, current, replacement)
    expected = BASE_APK if args.rollback else wanted
    if LEG1.sha(target.read_bytes()) != expected:
        raise ValueError("staged LG2 content drift")
    return {"status": "PASS", "rollback": args.rollback,
            "already_staged": current == replacement, "staged_apk_sha256": expected,
            "backup_sha256": BASE_APK, "rom_build_run": False, "runtime_validated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("android-root", "state-dir", "apk", "pins", "build-report", "backup"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--rollback", action="store_true")
    try:
        print(json.dumps(stage(parser.parse_args()), sort_keys=True))
    except (OSError, ValueError, LG2.BuildError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
