#!/usr/bin/env python3
"""Build the opt-in EC2 W2L trial from stock plus the pinned EC1 transform."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "devices/m11q/epdgservice-w2l-trial-contract.json"
DEFAULT_PINS = ROOT / "devices/m11q/epdgservice-w2l-trial-build.json"


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BASE = _module("ec2_base_builder", "tools/build_epdgservice.py")
BuildError = BASE.BuildError


def load_pins(path):
    pins = json.loads(BASE._regular(path, "trial build pins").read_text(encoding="utf-8"))
    if set(pins) != {"schema_version", "transformation_id", "classes_dex_sha256", "unsigned_apk_sha256"}:
        raise BuildError("trial build pin schema drift")
    if pins["schema_version"] != 1 or pins["transformation_id"] != "EC2-active-w2l-trial":
        raise BuildError("trial build identity drift")
    for key in ("classes_dex_sha256", "unsigned_apk_sha256"):
        digest = pins[key]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise BuildError("trial output pins must be promoted SHA-256 values")
    return pins


def _trial_overlay(overlay, root, targets, additions):
    expected = {item["path"] for item in targets + additions}
    actual = {p.relative_to(overlay).as_posix() for p in overlay.rglob("*") if p.is_file()}
    if actual != expected:
        raise BuildError("trial overlay inventory drift")
    for item in targets + additions:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.as_posix().endswith(".smali"):
            raise BuildError("unsafe trial target")
        source = overlay.joinpath(*relative.parts)
        destination = root.joinpath(*relative.parts)
        if source.is_symlink() or destination.is_symlink():
            raise BuildError("unsafe trial overlay entry")
        if item in additions:
            if destination.exists():
                raise BuildError("added trial class already exists")
        elif not destination.is_file():
            raise BuildError("missing trial target")
        if BASE.sha256_file(source) != item["output_sha256"]:
            raise BuildError("trial overlay hash drift")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def verify_classes(stock, verified, ec1, trial, source_verified=False):
    """Verify every class, including untouched stock and exact added classes."""
    ec1_targets = {item["path"]: item for item in ec1["targets"]}
    targets = {item["path"]: item for item in trial["targets"]}
    additions = {item["path"]: item for item in trial.get("additions", [])}
    normalizations = {item["path"]: item for item in ec1["roundtrip_normalizations"]}
    if set(verified) != set(stock) | set(additions):
        raise BuildError("final trial class inventory drift")
    transformed_paths = set(targets) | set(additions) | set(ec1_targets) | set(normalizations)
    for path in sorted(verified):
        if path in targets:
            expected = targets[path].get("redecoded_sha256", targets[path]["output_sha256"])
        elif path in additions:
            expected = additions[path].get("redecoded_sha256", additions[path]["output_sha256"])
        elif path in ec1_targets:
            expected = ec1_targets[path]["output_sha256"]
        elif path in normalizations:
            if stock[path] != normalizations[path]["input_sha256"]:
                raise BuildError("round-trip input normalization drift")
            expected = normalizations[path]["output_sha256"]
        else:
            expected = stock[path]
        if verified[path] != expected and not (
                source_verified and path in transformed_paths):
            raise BuildError(f"final trial class hash drift: {path}")


def _normalize_static_default_field(line):
    match = re.fullmatch(
        r"\.field\s+((?:(?:public|private|protected|static|final|volatile|transient|synthetic|enum)\s+)*)"
        r"([A-Za-z_$][\w$]*):([^\s=]+)(?:\s*=\s*(\S+))?", line)
    if not match:
        return line
    modifiers, name, descriptor, value = match.groups()
    if value is None or "static" not in modifiers.split():
        return line
    is_default = False
    if descriptor == "Z":
        is_default = value == "false"
    elif descriptor in {"B", "S", "C", "I", "J"}:
        numeric = value[:-1] if descriptor == "J" and value[-1:] in {"l", "L"} else value
        try:
            parsed = int(numeric, 0)
            is_default = parsed == 0
        except ValueError:
            is_default = False
    elif descriptor in {"F", "D"}:
        numeric = value[:-1] if value[-1:] in {"f", "F", "d", "D"} else value
        if not numeric.startswith("-"):
            if numeric in {"0", "0.0", "0.", ".0"}:
                is_default = True
            elif re.fullmatch(r"0[xX]0(?:\.0*)?[pP][+-]?0", numeric):
                is_default = True
    elif descriptor.startswith(("L", "[")):
        is_default = value == "null"
    if is_default:
        return f".field {modifiers}{name}:{descriptor}"
    return line


def normalized_smali(text):
    """Ignore only presentation differences from assembly/baksmali.

    Preserve instructions, registers, constants, metadata, and exception ranges.
    Labels are represented by statement positions, including switch data. Catch
    directives are compared separately because baksmali relocates their text.
    This is not an ART verifier or a behavioral-equivalence claim.
    """
    methods = {}
    pattern = re.compile(r"(?ms)^\.method\s+([^\n]+)\n(.*?)^\.end method\s*$")
    for match in pattern.finditer(text):
        header, body = match.groups()
        if header in methods:
            raise BuildError("duplicate method during round-trip verification")
        labels, statements, catches = {}, [], []
        lines = [raw.strip() for raw in body.splitlines() if raw.strip() and not raw.lstrip().startswith("#")]
        in_data = False
        for index, line in enumerate(lines):
            if line.startswith((".line ", ".local ", ".end local", ".restart local", ".param ", ".end param")):
                continue
            # DEX payloads require alignment; baksmali may expose this padding.
            if line == "nop":
                following = next((value for value in lines[index + 1:] if not value.startswith(":")), "")
                if following.startswith((".packed-switch ", ".sparse-switch", ".array-data ")):
                    continue
            if line.startswith((".packed-switch ", ".sparse-switch", ".array-data ")):
                in_data = True
            if line.startswith(":") and not in_data:
                labels[line[1:]] = len(statements)
            elif line.startswith(".catch"):
                catches.append(line)
            else:
                statements.append(line)
            if line.startswith((".end packed-switch", ".end sparse-switch", ".end array-data")):
                in_data = False
        def normalize(line):
            line = re.sub(r"(?<![\w$]):([A-Za-z_]\w*)", lambda m: f":@{labels[m[1]]}" if m[1] in labels else m[0], line)
            # Encoding width is selected by the assembler, not program behavior.
            line = re.sub(r"^goto(?:/16|/32)? ", "goto ", line)
            return re.sub(r"^const-string/jumbo ", "const-string ", line)
        methods[header] = ([normalize(line) for line in statements], [normalize(line) for line in catches])
    outside = pattern.sub("", text)
    declarations = sorted(_normalize_static_default_field(line.strip())
                         for line in outside.splitlines()
                         if line.strip() and not line.lstrip().startswith("#"))
    return declarations, methods


def verify_roundtrip_sources(source, verified, contract, source_verified=False):
    paths = [item["path"] for item in contract["targets"] + contract["additions"]]
    if source_verified:
        before_inventory = BASE._smali_inventory(source)
        after_inventory = BASE._smali_inventory(verified)
        if set(after_inventory) != set(before_inventory):
            raise BuildError("source-verified final class inventory drift")
        paths = sorted(before_inventory)
    for path in paths:
        before = normalized_smali((source / path).read_text(encoding="utf-8"))
        after = normalized_smali((verified / path).read_text(encoding="utf-8"))
        if before != after:
            raise BuildError(f"trial instruction/exception round-trip drift: {path}")
    return len(paths)


def verify_output_pins(observed, pins, source_verified=False):
    if (observed["schema_version"] != pins["schema_version"] or
            observed["transformation_id"] != pins["transformation_id"]):
        raise BuildError("trial output identity drift")
    if not source_verified and observed != pins:
        raise BuildError("trial final APK/DEX pin drift")


def build(args):
    ec1 = BASE._module("ec2_ec1_transform", "tools/transform_epdgservice_compat.py")
    trial = _module("ec2_trial_transform", "tools/transform_epdgservice_w2l_trial.py")
    zipper = BASE._module("ec2_zipper", "tools/apk_entry_replace.py")
    contract = trial.load_contract(args.contract)
    ec1_contract_path = ROOT / "devices/m11q/epdgservice-compat-contract.json"
    ec1_contract = ec1.load_contract(ec1_contract_path)
    artifact = ec1_contract["source_artifact"]
    stock = BASE._pinned(args.stock_apk, "stock ePDG APK", artifact["apk_sha256"], artifact["apk_size"])
    java = BASE._pinned(args.java, "Java runtime", BASE.JAVA_SHA256)
    apktool = BASE._pinned(args.apktool_jar, "apktool JAR", BASE.APKTOOL_SHA256)
    entries = BASE._zip_entries(stock)
    if hashlib.sha256(entries.get("classes.dex", b"")).hexdigest() != artifact["classes_dex_sha256"]:
        raise BuildError("stock classes.dex identity drift")
    discovery = args.discover_pins
    source_verified = args.source_verified
    if discovery and source_verified:
        raise BuildError("pin discovery and source-verified publication are mutually exclusive")
    pins = None if discovery else load_pins(args.pins)
    if args.report.exists() or args.report.is_symlink() or (args.output and (args.output.exists() or args.output.is_symlink())):
        raise BuildError("refusing to overwrite output or report")
    if discovery and args.output:
        raise BuildError("pin discovery cannot publish an APK")
    if not discovery and not args.output:
        raise BuildError("strict build requires --output")
    if args.work_dir and (args.work_dir.is_symlink() or not args.work_dir.is_dir()):
        raise BuildError("unsafe work directory")
    stage = Path(tempfile.mkdtemp(prefix="ec2-w2l-build-", dir=args.work_dir))
    try:
        decoded = stage / "decoded"
        verified = stage / "verified"
        command = [str(java), "-XX:ActiveProcessorCount=1", "-jar", str(apktool)]
        BASE._run(command + ["d", "-f", "-o", str(decoded), str(stock)], "stock APK decode")
        stock_classes = BASE._smali_inventory(decoded / "smali")
        ec1_result = ec1.transform(ec1_contract_path, decoded / "smali", stage / "ec1", stage / "ec1.json")
        BASE._copy_overlay(stage / "ec1", decoded / "smali", {item["path"] for item in ec1_contract["targets"]})
        trial_result = trial.transform(args.contract, decoded / "smali", stage / "ec2", stage / "ec2.json")
        _trial_overlay(stage / "ec2", decoded / "smali", contract["targets"], contract.get("additions", []))
        rebuilt = stage / "rebuilt.apk"
        BASE._run(command + ["b", str(decoded), "-o", str(rebuilt)], "ePDG APK assembly")
        dex = stage / "classes.dex"
        dex.write_bytes(BASE._zip_entries(rebuilt)["classes.dex"])
        dex_hash = BASE.sha256_file(dex)
        candidate = stage / "candidate.apk"
        zip_report = zipper.build_archive(stock, candidate, {"classes.dex": dex}, {})
        apk_hash = zip_report["output_sha256"]
        expected_changes = {"classes.dex"} | (set(entries) & BASE.SIGNATURES)
        if {item["entry"] for item in zip_report["changed_entries"]} != expected_changes:
            raise BuildError("unexpected trial APK entry change")
        if set(zip_report["removed_signatures"]) != set(entries) & BASE.SIGNATURES:
            raise BuildError("trial signature inventory drift")
        after_entries = BASE._zip_entries(candidate)
        if set(after_entries) != set(entries) - BASE.SIGNATURES or any(after_entries[name] != content for name, content in entries.items() if name not in expected_changes):
            raise BuildError("unrelated trial APK entries changed")
        BASE._run(command + ["d", "-f", "-o", str(verified), str(candidate)], "trial APK re-decode")
        final_classes = BASE._smali_inventory(verified / "smali")
        roundtrip_count = verify_roundtrip_sources(
            decoded / "smali", verified / "smali", contract, source_verified)
        observed_redecoded = {item["path"]: final_classes[item["path"]] for item in contract["targets"] + contract["additions"]}
        final_contract = contract
        if discovery:
            # Only these reviewed classes may discover canonical text hashes;
            # every instruction and exception range has already been checked.
            final_contract = {**contract, **{key: [{**item, "redecoded_sha256": observed_redecoded[item["path"]]} for item in contract[key]] for key in ("targets", "additions")}}
        verify_classes(stock_classes, final_classes, ec1_contract, final_contract, source_verified)
        references = _module("ec2_reference_verifier", "tools/verify_epdgservice_w2l_refs.py")
        reference_result = references.verify(verified / "smali")
        observed = {"schema_version": 1, "transformation_id": "EC2-active-w2l-trial", "classes_dex_sha256": dex_hash, "unsigned_apk_sha256": apk_hash}
        if pins is not None:
            verify_output_pins(observed, pins, source_verified)
        payload = {
            "schema_version": 1, "status": "SOURCE_VERIFIED" if source_verified else "PASS",
            "transformation_id": trial.TRANSFORMATION_ID,
            "mode": "source-verified" if source_verified else ("pin-discovery" if discovery else "strict"),
            "observed_build_pins": observed,
            "observed_redecoded_pins": observed_redecoded,
            "instruction_roundtrip_validation": {"classes_verified": roundtrip_count, "status": "PASS"},
            "inputs": {"stock_apk_sha256": artifact["apk_sha256"], "stock_classes_dex_sha256": artifact["classes_dex_sha256"]},
            "toolchain": {"apktool_sha256": BASE.APKTOOL_SHA256, "java_sha256": BASE.JAVA_SHA256},
            "transformations": {"EC1": ec1_result["files"], "EC2": trial_result["files"]},
            "helper_reference_validation": reference_result,
            "output": {"classes_dex_sha256": dex_hash, "unsigned_apk_sha256": apk_hash, "strict_pins_verified": not discovery,
                       "artifact_published": not discovery, "signed": False, "runtime_validated": False,
                       "all_redecoded_classes_verified": True, "unrelated_zip_entries_preserved": True},
            "safety": {"rom_build_run": False, "saved_decoded_payload_used": False, "saved_final_payload_used": False},
        }
        if source_verified:
            receipt_api = _module("ec2_source_verified_receipt", "tools/source_verified_receipt.py")
            source_classification = {
                "source_classification_verified": True,
                "stock_apk_sha256": artifact["apk_sha256"],
                "stock_classes_dex_sha256": artifact["classes_dex_sha256"],
                "apktool_sha256": BASE.APKTOOL_SHA256,
                "java_sha256": BASE.JAVA_SHA256,
                "transformations": [
                    {"id": ec1_result["transformation_id"], "files": ec1_result["files"]},
                    {"id": trial.TRANSFORMATION_ID, "files": trial_result["files"]},
                ],
                "published_input_class_anchors_verified": True,
                "helper_references_verified": True,
                "all_class_instruction_metadata_roundtrip_count": roundtrip_count,
            }
            payload.update({
                "strict_pins_verified": False,
                "source_invariants_verified": True,
                "runtime_validated": False,
                "release_eligible": False,
                "source_verified_receipt": receipt_api.make_source_verified_receipt(
                    "epdgservice-ec2-source-verified", candidate,
                    {"classes.dex": dex_hash}, source_classification),
            })
        if discovery:
            if not args.report.parent.is_dir() or args.report.parent.is_symlink():
                raise BuildError("unsafe report parent")
            with args.report.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
        else:
            BASE._publish(candidate, args.output, args.report, payload)
        return payload
    finally:
        if getattr(args, "keep_work", False):
            print(f"retained diagnostic work directory: {stage}", file=sys.stderr)
        else:
            shutil.rmtree(stage, ignore_errors=True)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for argument in ("stock-apk", "apktool-jar", "java", "report"):
        result.add_argument("--" + argument, type=Path, required=True)
    result.add_argument("--output", type=Path)
    result.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    result.add_argument("--pins", type=Path, default=DEFAULT_PINS)
    result.add_argument("--work-dir", type=Path)
    result.add_argument("--discover-pins", action="store_true")
    result.add_argument("--source-verified", action="store_true",
                        help="publish actual serialization hashes after source/inventory/round-trip checks")
    result.add_argument("--keep-work", action="store_true", help="retain private decoded files for host diagnostics")
    return result


def main(argv=None):
    try:
        result = build(parser().parse_args(argv))
    except (OSError, ValueError, BuildError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "mode": result["mode"], **result["observed_build_pins"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
