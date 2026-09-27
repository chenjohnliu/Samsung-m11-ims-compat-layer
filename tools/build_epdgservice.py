#!/usr/bin/env python3
"""Rebuild the validated M11 EpdgService compatibility DEX from exact stock."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "devices" / "m11q" / "epdgservice-compat-contract.json"
APKTOOL_SHA256 = "7956eb04194300ce0d0a84ad18771eebc94b89fb8d1ddcce8ea4c056818646f4"
JAVA_SHA256 = "2f515280cc6ec9870c873a61ea83cb7b15d6872a111d1964d758e4daac464132"
FINAL_DEX_SHA256 = "845ffb5b45fa3c077776c0d51bbd51dc2aa5b2fb84b087001a2561b4ee33acee"
FINAL_APK_SHA256 = "5eb14c66f5a6917de214d823f34b7dd453f6b22a64b91d74c733c89e23e23f98"
SIGNATURES = {"META-INF/CERT.RSA", "META-INF/CERT.SF", "META-INF/MANIFEST.MF"}


class BuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular(path: Path, label: str) -> Path:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise BuildError(f"missing {label}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise BuildError(f"{label} must be a regular non-symlink file")
    return path.resolve(strict=True)


def _pinned(path: Path, label: str, digest: str, size: int | None = None) -> Path:
    resolved = _regular(path, label)
    if size is not None and resolved.stat().st_size != size:
        raise BuildError(f"{label} size mismatch")
    if sha256_file(resolved) != digest:
        raise BuildError(f"{label} SHA-256 mismatch")
    return resolved


def _module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load project tool: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(command: list[str], label: str) -> None:
    try:
        result = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise BuildError(f"cannot execute {label}: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().replace("\r", " ").replace("\n", " ")
        raise BuildError(f"{label} failed with exit {result.returncode}: {detail[:400]}")


def _zip_entries(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise BuildError("duplicate APK entries")
            bad = archive.testzip()
            if bad is not None:
                raise BuildError(f"APK CRC failure: {bad}")
            return {name: archive.read(name) for name in names}
    except zipfile.BadZipFile as exc:
        raise BuildError("invalid APK") from exc


def _copy_overlay(overlay: Path, smali: Path, expected: set[str]) -> None:
    actual = {p.relative_to(overlay).as_posix() for p in overlay.rglob("*") if p.is_file()}
    if actual != expected:
        raise BuildError("overlay inventory drift")
    for relative in sorted(expected):
        source = overlay.joinpath(*PurePosixPath(relative).parts)
        target = smali.joinpath(*PurePosixPath(relative).parts)
        if target.is_symlink() or not target.is_file():
            raise BuildError(f"unsafe or missing decoded target: {relative}")
        shutil.copyfile(source, target)


def _smali_inventory(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise BuildError("decoded smali root is missing or unsafe")
    inventory = {}
    for item in root.rglob("*.smali"):
        if item.is_symlink() or not item.is_file():
            raise BuildError("unsafe decoded smali entry")
        inventory[item.relative_to(root).as_posix()] = sha256_file(item)
    if not inventory:
        raise BuildError("decoded smali inventory is empty")
    return inventory


def _publish(source: Path, destination: Path, report: Path, payload: dict) -> None:
    if destination.exists() or report.exists() or destination.is_symlink() or report.is_symlink():
        raise BuildError("refusing to overwrite output or report")
    if not destination.parent.is_dir() or destination.parent.is_symlink() or not report.parent.is_dir() or report.parent.is_symlink():
        raise BuildError("output parents must be existing non-symlink directories")
    output_fd, output_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    report_fd, report_name = tempfile.mkstemp(prefix=f".{report.name}.", suffix=".tmp", dir=report.parent)
    os.close(output_fd)
    os.close(report_fd)
    output_tmp = Path(output_name)
    report_tmp = Path(report_name)
    published = False
    try:
        shutil.copyfile(source, output_tmp)
        report_tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        os.replace(output_tmp, destination)
        published = True
        os.link(report_tmp, report)
    except BaseException:
        if published:
            destination.unlink(missing_ok=True)
        report.unlink(missing_ok=True)
        raise
    finally:
        output_tmp.unlink(missing_ok=True)
        report_tmp.unlink(missing_ok=True)


def build(args: argparse.Namespace) -> dict:
    transformer = _module("transform_epdgservice_compat", "tools/transform_epdgservice_compat.py")
    zipper = _module("apk_entry_replace", "tools/apk_entry_replace.py")
    contract_path = _regular(args.contract, "contract")
    contract = transformer.load_contract(contract_path)
    artifact = contract["source_artifact"]
    stock = _pinned(args.stock_apk, "stock EpdgService APK", artifact["apk_sha256"], artifact["apk_size"])
    apktool = _pinned(args.apktool_jar, "apktool JAR", APKTOOL_SHA256)
    java = _pinned(args.java, "Java runtime", JAVA_SHA256)
    stock_entries = _zip_entries(stock)
    if "classes.dex" not in stock_entries or hashlib.sha256(stock_entries["classes.dex"]).hexdigest() != artifact["classes_dex_sha256"]:
        raise BuildError("stock classes.dex identity drift")
    if args.output.exists() or args.report.exists():
        raise BuildError("refusing to overwrite output or report")
    parent = args.work_dir
    if parent is not None:
        if parent.is_symlink() or not parent.is_dir():
            raise BuildError("work directory must be an existing non-symlink directory")
        parent = parent.resolve(strict=True)
    stage = Path(tempfile.mkdtemp(prefix="epdgservice-build-", dir=parent))
    try:
        decoded = stage / "decoded"
        overlay = stage / "overlay"
        transform_report = stage / "transform.json"
        rebuilt = stage / "rebuilt.apk"
        candidate = stage / "candidate.apk"
        verified = stage / "verified"
        java_cmd = [str(java), "-XX:ActiveProcessorCount=1", "-jar", str(apktool)]
        _run(java_cmd + ["d", "-f", "-o", str(decoded), str(stock)], "apktool decode")
        stock_smali = _smali_inventory(decoded / "smali")
        result = transformer.transform(contract_path, decoded / "smali", overlay, transform_report)
        expected = {item["path"] for item in contract["targets"]}
        _copy_overlay(overlay, decoded / "smali", expected)
        _run(java_cmd + ["b", str(decoded), "-o", str(rebuilt)], "apktool build")
        rebuilt_entries = _zip_entries(rebuilt)
        dex = stage / "classes.dex"
        dex.write_bytes(rebuilt_entries.get("classes.dex", b""))
        if sha256_file(dex) != FINAL_DEX_SHA256:
            raise BuildError("rebuilt classes.dex hash drift")
        zip_result = zipper.build_archive(stock, candidate, {"classes.dex": dex}, {})
        if zip_result["output_sha256"] != FINAL_APK_SHA256:
            raise BuildError("unsigned APK hash drift")
        if set(zip_result["removed_signatures"]) != (set(stock_entries) & SIGNATURES):
            raise BuildError("signature removal inventory drift")
        if {item["entry"] for item in zip_result["changed_entries"]} != ({"classes.dex"} | (set(stock_entries) & SIGNATURES)):
            raise BuildError("unexpected output APK entry change")
        _run(java_cmd + ["d", "-f", "-o", str(verified), str(candidate)], "final APK re-decode")
        verified_smali = _smali_inventory(verified / "smali")
        if set(verified_smali) != set(stock_smali):
            raise BuildError("final decoded class inventory drift")
        normalizations = {item["path"]: item for item in contract["roundtrip_normalizations"]}
        for relative, item in normalizations.items():
            if stock_smali.get(relative) != item["input_sha256"] or verified_smali.get(relative) != item["output_sha256"]:
                raise BuildError(f"round-trip normalization drift: {relative}")
            before = (decoded / "smali").joinpath(*PurePosixPath(relative).parts).read_text(encoding="utf-8")
            after = (verified / "smali").joinpath(*PurePosixPath(relative).parts).read_text(encoding="utf-8")
            if item["rule"] != "explicit_false_static_default_elided" or before.replace(".field public static final VDBG:Z = false", ".field public static final VDBG:Z") != after:
                raise BuildError(f"unexpected round-trip normalization content: {relative}")
        for relative in set(stock_smali) - expected - set(normalizations):
            if verified_smali[relative] != stock_smali[relative]:
                raise BuildError(f"unrelated decoded class changed: {relative}")
        for item in contract["targets"]:
            target = (verified / "smali").joinpath(*PurePosixPath(item["path"]).parts)
            if target.is_symlink() or not target.is_file() or sha256_file(target) != item["output_sha256"]:
                raise BuildError(f"final transformed class verification failed: {item['path']}")
        payload = {
            "schema_version": 1,
            "status": "PASS",
            "transformation_id": transformer.TRANSFORMATION_ID,
            "inputs": {"stock_apk_sha256": artifact["apk_sha256"], "stock_classes_dex_sha256": artifact["classes_dex_sha256"]},
            "toolchain": {"apktool_sha256": APKTOOL_SHA256, "java_sha256": JAVA_SHA256, "apktool_jvm_args": ["-XX:ActiveProcessorCount=1"]},
            "transformations": result["files"],
            "output": {"unsigned_apk_sha256": FINAL_APK_SHA256, "classes_dex_sha256": FINAL_DEX_SHA256, "redecoded_target_hashes_verified": True, "redecoded_unrelated_classes_verified": True, "roundtrip_normalizations_verified": [item["path"] for item in contract["roundtrip_normalizations"]], "changed_entries": sorted({item["entry"] for item in zip_result["changed_entries"]}), "unrelated_zip_entries_preserved": True, "signed": False, "runtime_validated": False},
            "reference": {"historical_runtime_validated_dex_sha256": artifact["validated_reference_dex_sha256"], "byte_identical_to_historical_dex": FINAL_DEX_SHA256 == artifact["validated_reference_dex_sha256"], "equivalence_basis": "exact transformed class hashes plus preserved unrelated methods and APK entries"},
            "safety": {"saved_decoded_payload_used": False, "saved_final_payload_used": False, "decoded_tree_published": False, "rom_build_run": False},
        }
        _publish(candidate, args.output, args.report, payload)
        return payload
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--stock-apk", required=True, type=Path)
    result.add_argument("--apktool-jar", required=True, type=Path)
    result.add_argument("--java", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--report", required=True, type=Path)
    result.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    result.add_argument("--work-dir", type=Path)
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        result = build(args)
    except (BuildError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "apk_sha256": result["output"]["unsigned_apk_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
