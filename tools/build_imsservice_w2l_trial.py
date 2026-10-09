#!/usr/bin/env python3
"""Layer the narrow BV1 IMS W2L trial on the exact reproducible current IMS APK.

This is APK assembly only. The stable stock-to-IMS builder remains unchanged;
its pinned output is the only accepted baseline. Preserve its bridge DEX,
manifest, resources and all unrelated entries. No signing or ROM build.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_epdgservice as BASE
import build_epdgservice_w2l_trial as ROUNDTRIP
import apk_entry_replace as ZIPPER
import verify_epdgservice_w2l_refs as REFS

IDENTITY = "BV1-w2l-ip-continuity-trial"
BASE_APK = "4cf9360b609fcc45329d038835a5913ba9c76844fe4cf59b70c132f904ae0dd1"
BASE_DEX = "cd8be33628bfabeafe77e78c58bf13ba8207e0eba41718845dcf116a8594cfe2"
BRIDGE_DEX = "b9d57c1a1aab37fd88a5443bde177c710897b1603481350e8037cf332ce0d325"
IMSMANAGER_SHA256 = "ba88f7111ea5c678d597dcb0498ee9fc42611fd4f6af12b6312fad05495de78b"
DEFAULT_CONTRACT = ROOT / "devices/m11q/bv1-w2l-ip-continuity-trial-contract.json"
DEFAULT_PINS = ROOT / "devices/m11q/imsservice-w2l-trial-build.json"
BuildError = BASE.BuildError


def load_pins(path):
    pins = json.loads(BASE._regular(path, "BV1 pins").read_text(encoding="utf-8"))
    if (set(pins) != {"schema_version", "transformation_id", "classes_dex_sha256", "unsigned_apk_sha256"}
            or pins["schema_version"] != 1 or pins["transformation_id"] != IDENTITY):
        raise BuildError("BV1 pin schema/identity drift")
    for key in ("classes_dex_sha256", "unsigned_apk_sha256"):
        value = pins[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise BuildError("BV1 output pins require promoted SHA-256 values")
    return pins


def verify_envelope(before, after, contract, discovery=False):
    original = BASE._smali_inventory(before)
    final = BASE._smali_inventory(after)
    targets = {x["path"]: x for x in contract["targets"]}
    additions = {x["path"]: x for x in contract["additions"]}
    if set(final) != set(original) | set(additions):
        raise BuildError("BV1 primary class inventory drift")
    reviewed = targets | additions
    for path in sorted(final):
        # Every class, including unchanged classes, must retain its actual
        # instructions, register operands, metadata and exception ranges.
        if normalized_smali((before / path).read_text(encoding="utf-8")) != normalized_smali((after / path).read_text(encoding="utf-8")):
            raise BuildError(f"BV1 instruction/metadata roundtrip drift: {path}")
        if path in reviewed and not discovery and final[path] != reviewed[path]["redecoded_sha256"]:
            raise BuildError(f"BV1 canonical class pin drift: {path}")
    return len(final), {path: final[path] for path in reviewed}


def normalized_smali(text):
    declarations, methods = ROUNDTRIP.normalized_smali(text)
    # The IMS DEX string table exceeds 65535 entries. Assembly widens only
    # the string-index encoding; keep its register and literal operands exact.
    return declarations, {key: ([re.sub(r"^const-string/jumbo ", "const-string ", line) for line in statements], catches)
                          for key, (statements, catches) in methods.items()}


def verify_references(root, contract, manager_root=None):
    classes = REFS.inventory(root)
    if manager_root is not None:
        manager = REFS.inventory(manager_root)
        if set(classes) & set(manager):
            raise BuildError("duplicate native class across IMS/imsmanager dependency")
        classes.update(manager)
    count = 0
    for item in contract["additions"]:
        text = (root / item["path"]).read_text(encoding="utf-8")
        owner = REFS.CLASS.search(text).group(2)
        for target, member in sorted(set(REFS.REFERENCE.findall(text))):
            declaring, flags = REFS.resolve(classes, target, member)
            same_package = owner.rsplit("/", 1)[0] == declaring.rsplit("/", 1)[0]
            if declaring != owner and ("private" in flags or ("public" not in flags and not same_package)):
                raise BuildError(f"BV1 inaccessible native member: {declaring}->{member}")
            count += 1
    return {"status": "PASS", "resolved_samsung_helper_references": count,
            "android_framework_reference_validation": "not performed by this tool", "runtime_validated": False}


def build(args):
    import transform_bv1_w2l_ip_continuity as trial
    contract = trial.load_contract(args.contract)
    base = BASE._pinned(args.base_apk, "current reproducible IMS baseline", BASE_APK)
    manager = BASE._pinned(args.imsmanager_jar, "stock native imsmanager dependency", IMSMANAGER_SHA256)
    java = BASE._pinned(args.java, "Java runtime", BASE.JAVA_SHA256)
    apktool = BASE._pinned(args.apktool_jar, "apktool JAR", BASE.APKTOOL_SHA256)
    entries = BASE._zip_entries(base)
    if (hashlib.sha256(entries.get("classes.dex", b"")).hexdigest() != BASE_DEX
            or hashlib.sha256(entries.get("classes2.dex", b"")).hexdigest() != BRIDGE_DEX):
        raise BuildError("BV1 baseline DEX drift")
    discovery = args.discover_pins
    pins = None if discovery else load_pins(args.pins)
    if discovery and args.output or not discovery and not args.output:
        raise BuildError("discovery publishes report only; strict mode requires output")
    for path in (args.report, args.output):
        if path and (path.exists() or path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink()):
            raise BuildError("unsafe or already existing output/report")
    if args.work_dir.is_symlink() or not args.work_dir.is_dir():
        raise BuildError("unsafe BV1 work directory")
    stage = Path(tempfile.mkdtemp(prefix="bv1-ims-w2l-", dir=args.work_dir))
    try:
        source, final = stage / "source", stage / "final"
        command = [str(java), "-XX:ActiveProcessorCount=1", "-jar", str(apktool)]
        BASE._run(command + ["d", "-r", str(base), "-o", str(source)], "BV1 baseline decode")
        manager_root = stage / "imsmanager"
        BASE._run(command + ["d", "-r", str(manager), "-o", str(manager_root)], "BV1 native dependency decode")
        # Raw resources/manifest are not rebuilt into the published candidate.
        # The exact original ZIP is repacked with only primary DEX replacement.
        changes = trial.transform(args.contract, source / "smali", stage / "overlay", stage / "transform.json")
        ROUNDTRIP._trial_overlay(stage / "overlay", source / "smali", contract["targets"], contract["additions"])
        rebuilt = stage / "assembled.apk"
        BASE._run(command + ["b", str(source), "-o", str(rebuilt)], "BV1 primary DEX assembly")
        dex = stage / "classes.dex"
        dex.write_bytes(BASE._zip_entries(rebuilt)["classes.dex"])
        candidate = stage / "candidate.apk"
        zipper = ZIPPER.build_archive(base, candidate, {"classes.dex": dex}, {})
        after_entries = BASE._zip_entries(candidate)
        changes_allowed = {"classes.dex"} | (set(entries) & BASE.SIGNATURES)
        if ({x["entry"] for x in zipper["changed_entries"]} != changes_allowed
                or set(after_entries) != set(entries) - BASE.SIGNATURES
                or any(after_entries[k] != v for k, v in entries.items() if k not in changes_allowed)):
            raise BuildError("BV1 unrelated ZIP/bridge DEX changed")
        BASE._run(command + ["d", "-r", str(candidate), "-o", str(final)], "BV1 candidate decode")
        count, canonical = verify_envelope(source / "smali", final / "smali", contract, discovery)
        reference = verify_references(final / "smali", contract, manager_root / "smali")
        observed = {"schema_version": 1, "transformation_id": IDENTITY,
                    "classes_dex_sha256": BASE.sha256_file(dex), "unsigned_apk_sha256": BASE.sha256_file(candidate)}
        if pins is not None and pins != observed:
            raise BuildError("BV1 final APK/DEX pin drift")
        payload = {"schema_version": 1, "transformation_id": IDENTITY, "status": "PASS",
                   "mode": "pin-discovery" if discovery else "strict", "observed_build_pins": observed,
                   "observed_redecoded_pins": canonical, "transformations": changes,
                   "inputs": {"base_apk_sha256": BASE_APK, "base_classes_dex_sha256": BASE_DEX,
                              "imsmanager_jar_sha256": IMSMANAGER_SHA256},
                   "toolchain": {"apktool_sha256": BASE.APKTOOL_SHA256, "java_sha256": BASE.JAVA_SHA256},
                   "instruction_roundtrip_validation": {"status": "PASS", "classes_verified": count},
                   "helper_reference_validation": reference,
                   "output": {**observed, "strict_pins_verified": not discovery, "artifact_published": not discovery,
                              "all_redecoded_classes_verified": True, "unrelated_zip_entries_preserved": True,
                              "classes2_dex_sha256": BRIDGE_DEX, "runtime_validated": False, "signed": False},
                   "safety": {"rom_build_run": False, "saved_decoded_payload_used": False}}
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
    for name in ("base-apk", "imsmanager-jar", "apktool-jar", "java", "report", "work-dir"):
        result.add_argument("--" + name, type=Path, required=True)
    result.add_argument("--output", type=Path)
    result.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    result.add_argument("--pins", type=Path, default=DEFAULT_PINS)
    result.add_argument("--discover-pins", action="store_true")
    result.add_argument("--keep-work", action="store_true")
    return result


def main():
    try:
        result = build(parser().parse_args())
    except (OSError, ValueError, BuildError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "mode": result["mode"], **result["observed_build_pins"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
