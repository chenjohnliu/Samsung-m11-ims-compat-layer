#!/usr/bin/env python3
"""Layer a pinned legacy WFC startup-gate repair on BV1; never build a ROM."""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import build_imsservice_w2l_trial as BV1
import legacy_wfc_gate_transform as TRANSFORM

BASE = BV1.BASE
BuildError = BASE.BuildError
IDENTITY = "LG3-legacy-wfc-startup-gate"
BASE_APK = "251f95cb892e38b8ba8025c3033332c55d8ac4bec1d0d53b8d18c8d33a870d0b"
BASE_DEX = "00f6fe5258acaa64ec03c97b9583394f46acdafeeac79ba5a532e6f245753ae1"
DEFAULT_PINS = BV1.ROOT / "devices/m11q/legacy-wfc-gate-build.json"


def load_pins(path):
    pins = json.loads(BASE._regular(path, "LG3 pins").read_text(encoding="utf-8"))
    if (set(pins) != {"schema_version", "transformation_id", "classes_dex_sha256",
                      "unsigned_apk_sha256"}
            or pins["schema_version"] != 1 or pins["transformation_id"] != IDENTITY):
        raise BuildError("LG3 pin schema/identity drift")
    for key in ("classes_dex_sha256", "unsigned_apk_sha256"):
        value = pins[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise BuildError("LG3 output pins require promoted SHA-256 values")
    return pins


def verify_apk(apk, pins_path=DEFAULT_PINS):
    pins = load_pins(pins_path)
    entries = BASE._zip_entries(BASE._regular(apk, "LG3 IMS APK"))
    if {k for k in entries if k.startswith("classes") and k.endswith(".dex")} != {"classes.dex", "classes2.dex"}:
        raise BuildError("LG3 IMS DEX inventory drift")
    primary = hashlib.sha256(entries["classes.dex"]).hexdigest()
    if primary != pins["classes_dex_sha256"] or hashlib.sha256(entries["classes2.dex"]).hexdigest() != BV1.BRIDGE_DEX:
        raise BuildError("LG3 IMS primary/bridge DEX mismatch; do not flash")
    return {"status": "PASS", "transformation_id": IDENTITY,
            "classes_dex_sha256": primary, "classes2_dex_sha256": BV1.BRIDGE_DEX,
            "runtime_validated": False, "signature_verified": False}


def verify_roundtrip(before, after):
    original = BASE._smali_inventory(before)
    final = BASE._smali_inventory(after)
    if set(final) != set(original):
        raise BuildError("LG3 primary class inventory drift")
    for name in original:
        if BV1.normalized_smali((before / name).read_text(encoding="utf-8")) != BV1.normalized_smali((after / name).read_text(encoding="utf-8")):
            raise BuildError(f"LG3 instruction/metadata roundtrip drift: {name}")
    return {"status": "PASS", "classes_verified": len(final),
            "target_redecoded_sha256": {name: final[name] for name in TRANSFORM.PATCHERS}}


def build(args):
    base = BASE._pinned(args.base_apk, "BV1 unsigned IMS APK", BASE_APK)
    java = BASE._pinned(args.java, "Java runtime", BASE.JAVA_SHA256)
    apktool = BASE._pinned(args.apktool_jar, "apktool JAR", BASE.APKTOOL_SHA256)
    entries = BASE._zip_entries(base)
    if (hashlib.sha256(entries.get("classes.dex", b"")).hexdigest() != BASE_DEX
            or hashlib.sha256(entries.get("classes2.dex", b"")).hexdigest() != BV1.BRIDGE_DEX):
        raise BuildError("LG3 baseline DEX drift")
    discovery = args.discover_pins
    pins = None if discovery else load_pins(args.pins)
    if (discovery and args.output) or (not discovery and not args.output):
        raise BuildError("discovery publishes report only; strict mode requires output")
    for path in (args.report, args.output):
        if path and (path.exists() or path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink()):
            raise BuildError("unsafe or existing output/report")
    if args.work_dir.is_symlink() or not args.work_dir.is_dir():
        raise BuildError("unsafe work directory")
    stage = Path(tempfile.mkdtemp(prefix="lg3-wfc-gate-", dir=args.work_dir))
    try:
        source, final = stage / "source", stage / "final"
        command = [str(java), "-XX:ActiveProcessorCount=1", "-jar", str(apktool)]
        BASE._run(command + ["d", "-r", str(base), "-o", str(source)], "LG3 baseline decode")
        initial = BASE._smali_inventory(source / "smali")
        transformed = TRANSFORM.transform(source / "smali", stage / "overlay", stage / "transform.json")
        for name in TRANSFORM.PATCHERS:
            (source / "smali" / name).write_bytes((stage / "overlay" / name).read_bytes())
        patched = BASE._smali_inventory(source / "smali")
        if {name for name in initial if initial[name] != patched[name]} != set(TRANSFORM.PATCHERS):
            raise BuildError("LG3 changed unrelated native classes")
        assembled = stage / "assembled.apk"
        BASE._run(command + ["b", str(source), "-o", str(assembled)], "LG3 primary DEX assembly")
        dex = stage / "classes.dex"
        dex.write_bytes(BASE._zip_entries(assembled)["classes.dex"])
        candidate = stage / "candidate.apk"
        ZIPPER = BASE._module("lg3_zipper", "tools/apk_entry_replace.py")
        zip_report = ZIPPER.build_archive(base, candidate, {"classes.dex": dex}, {})
        after_entries = BASE._zip_entries(candidate)
        if ({x["entry"] for x in zip_report["changed_entries"]} != {"classes.dex"}
                or set(after_entries) != set(entries)
                or any(after_entries[k] != v for k, v in entries.items() if k != "classes.dex")):
            raise BuildError("LG3 unrelated ZIP entry or bridge DEX changed")
        BASE._run(command + ["d", "-r", str(candidate), "-o", str(final)], "LG3 candidate decode")
        roundtrip = verify_roundtrip(source / "smali", final / "smali")
        observed = {"schema_version": 1, "transformation_id": IDENTITY,
                    "classes_dex_sha256": BASE.sha256_file(dex),
                    "unsigned_apk_sha256": BASE.sha256_file(candidate)}
        if pins is not None and pins != observed:
            raise BuildError("LG3 final APK/DEX pin drift")
        payload = {"status": "PASS", "schema_version": 1, "transformation_id": IDENTITY,
                   "mode": "pin-discovery" if discovery else "strict",
                   "observed_build_pins": observed, "transformation": transformed,
                   "instruction_roundtrip_validation": roundtrip,
                   "inputs": {"base_apk_sha256": BASE_APK, "base_classes_dex_sha256": BASE_DEX},
                   "toolchain": {"java_sha256": BASE.JAVA_SHA256, "apktool_sha256": BASE.APKTOOL_SHA256},
                   "output": {"strict_pins_verified": not discovery, "artifact_published": not discovery,
                              "all_redecoded_classes_verified": True, "unrelated_zip_entries_preserved": True,
                              "classes2_dex_sha256": BV1.BRIDGE_DEX,
                              "signed": False, "runtime_validated": False},
                   "safety": {"rom_build_run": False, "source_tree_changed": False,
                              "saved_decoded_payload_used": False}}
        if discovery:
            with args.report.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
        else:
            BASE._publish(candidate, args.output, args.report, payload)
        return payload
    finally:
        if args.keep_work:
            print(f"retained private diagnostic directory: {stage}", file=sys.stderr)
        else:
            shutil.rmtree(stage, ignore_errors=True)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("base-apk", "apktool-jar", "java", "report", "work-dir"):
        result.add_argument("--" + name, type=Path, required=True)
    result.add_argument("--output", type=Path)
    result.add_argument("--pins", type=Path, default=DEFAULT_PINS)
    result.add_argument("--discover-pins", action="store_true")
    result.add_argument("--keep-work", action="store_true")
    return result


def main():
    try:
        result = build(parser().parse_args())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "mode": result["mode"],
                      **result["observed_build_pins"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
