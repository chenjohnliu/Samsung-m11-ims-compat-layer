#!/usr/bin/env python3
"""Rebuild the M11 SVE APK from an exact stock input without saved payloads."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "devices" / "m11q" / "sveservice-build.json"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SIGNATURES = {"META-INF/CERT.RSA", "META-INF/CERT.SF", "META-INF/MANIFEST.MF"}
STOCK_APK_SHA256 = "5066ebdbd2dc8d5ff8da613f8b0f63b1d7e0408f3732b889719179d2bc1e33ab"
STOCK_DEX_SHA256 = "630ff3e440b8199fb9037bd3a56585573a724c83f548e6754cdc4dbad64fa804"
APKTOOL_SHA256 = "7956eb04194300ce0d0a84ad18771eebc94b89fb8d1ddcce8ea4c056818646f4"
OUTPUT_DEX_SHA256 = "f1294ce50783bbec6ad84fbd377a9436f70954a2bcd9a4b7e258b3a4552df4f4"
OUTPUT_APK_SHA256 = "8050c925f353d42872ea88933df1d88ce5678b9f9f9dc4ccb8412573b81b2cf3"


class BuildError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BuildError(f"cannot load project tool: {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hash(value, label: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise BuildError(f"invalid configured SHA-256 for {label}")
    return value


def _regular(path: Path, label: str) -> Path:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise BuildError(f"missing {label}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise BuildError(f"{label} must be a regular non-symlink file")
    return path.resolve(strict=True)


def load_config(path: Path) -> dict:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"cannot read build config: {exc}") from exc
    expected_top = {"schema_version", "artifact", "device", "contract", "stock",
                    "toolchain", "output"}
    if not isinstance(config, dict) or set(config) != expected_top:
        raise BuildError("malformed build config")
    if config["schema_version"] != 1 or config["artifact"] != "sveservice.apk":
        raise BuildError("unsupported build identity")
    if config["device"] != {
            "codename": "m11q", "model": "SM-M115F", "stock_build": "M115FXXS5CWK3",
            "stock_android": 12, "target_android": 13}:
        raise BuildError("device/build identity drift")
    if config["contract"] != "devices/m11q/sveservice-media-contract.json":
        raise BuildError("transform contract path drift")
    stock = config["stock"]
    if set(stock) != {"size", "sha256", "entries"} or stock["size"] != 634428:
        raise BuildError("stock identity drift")
    if _hash(stock["sha256"], "stock APK") != STOCK_APK_SHA256:
        raise BuildError("stock APK pin drift")
    if not isinstance(stock["entries"], dict) or len(stock["entries"]) != 10:
        raise BuildError("stock entry inventory drift")
    for name, digest in stock["entries"].items():
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != name:
            raise BuildError("unsafe configured ZIP entry")
        _hash(digest, f"stock entry {name}")
    apktool = config["toolchain"].get("apktool")
    if set(config["toolchain"]) != {"apktool"} or set(apktool) != {
            "version", "sha256", "jvm_args"}:
        raise BuildError("toolchain contract drift")
    if apktool["version"] != "2.9.3" or apktool["jvm_args"] != ["-XX:ActiveProcessorCount=1"]:
        raise BuildError("apktool determinism contract drift")
    if _hash(apktool["sha256"], "apktool") != APKTOOL_SHA256:
        raise BuildError("apktool pin drift")
    output = config["output"]
    if set(output) != {"classes_dex_size", "classes_dex_sha256",
                       "unsigned_apk_sha256", "changed_entries"}:
        raise BuildError("output contract drift")
    if output["classes_dex_size"] != 320808:
        raise BuildError("output DEX size drift")
    if _hash(output["classes_dex_sha256"], "output DEX") != OUTPUT_DEX_SHA256:
        raise BuildError("output DEX pin drift")
    if _hash(output["unsigned_apk_sha256"], "output APK") != OUTPUT_APK_SHA256:
        raise BuildError("output APK pin drift")
    if output["changed_entries"] != sorted(SIGNATURES | {"classes.dex"}):
        raise BuildError("changed-entry contract drift")
    return config


def _zip_data(path: Path) -> tuple[dict[str, bytes], str]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise BuildError("duplicate ZIP entries")
            bad = archive.testzip()
            if bad is not None:
                raise BuildError("ZIP CRC failure")
            return {name: archive.read(name) for name in names}, sha256_file(path)
    except zipfile.BadZipFile as exc:
        raise BuildError("invalid APK/ZIP") from exc


def verify_stock(path: Path, config: dict) -> tuple[Path, dict[str, bytes]]:
    stock = _regular(path, "stock APK")
    expected = config["stock"]
    if stock.stat().st_size != expected["size"] or sha256_file(stock) != expected["sha256"]:
        raise BuildError("stock APK identity mismatch")
    data, _ = _zip_data(stock)
    actual = {name: sha256_bytes(value) for name, value in data.items()}
    if actual != expected["entries"]:
        raise BuildError("stock ZIP entry inventory or hash drift")
    return stock, data


def _java(value: str) -> Path:
    candidate = Path(value)
    found = shutil.which(value) if candidate.parent == Path(".") else None
    launcher = Path(found) if found else candidate
    try:
        resolved = launcher.resolve(strict=True)
    except FileNotFoundError as exc:
        raise BuildError("missing Java launcher") from exc
    # System Java launchers are commonly a trusted symlink chain managed by
    # alternatives.  Resolve that chain, then require the endpoint to be a
    # regular file; inputs and outputs retain the stricter no-symlink rule.
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise BuildError("Java launcher endpoint must be a regular file")
    return resolved


def _run(command: list[str], label: str) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        tail = detail[-1] if detail else "no diagnostic"
        raise BuildError(f"{label} failed: {tail}")


def _apktool(java: Path, jar: Path, jvm_args: list[str], args: list[str], label: str) -> None:
    _run([str(java), *jvm_args, "-jar", str(jar), *args], label)


def _verify_output_tree(root: Path, transform, contract: dict) -> None:
    for item in contract["targets"]:
        target = root.joinpath(*PurePosixPath(item["path"]).parts)
        if target.is_symlink() or not target.is_file():
            raise BuildError("rebuilt target is missing")
        data = target.read_bytes()
        if sha256_bytes(data) != item["output_sha256"]:
            raise BuildError("rebuilt target hash drift")
        text = data.decode("utf-8")
        methods = transform._methods(text)
        for method in item["methods"]:
            body = methods.get(method["signature"])
            if body is None or sha256_bytes(body.encode("utf-8")) != method["output_sha256"]:
                raise BuildError("rebuilt method invariant drift")
    if "m11q_sve_compat" not in (root / transform.JNI_PATH).read_text(encoding="utf-8"):
        raise BuildError("compat loader invariant missing")


def build(config_path: Path, stock_path: Path, apktool_path: Path, java_value: str,
          output_path: Path, report_path: Path | None = None) -> dict:
    config = load_config(config_path)
    if report_path is not None and output_path.resolve(strict=False) == report_path.resolve(strict=False):
        raise BuildError("output APK and report must be different paths")
    stock, stock_data = verify_stock(stock_path, config)
    jar = _regular(apktool_path, "apktool JAR")
    if sha256_file(jar) != config["toolchain"]["apktool"]["sha256"]:
        raise BuildError("apktool JAR SHA-256 mismatch")
    java = _java(java_value)
    contract_path = ROOT / config["contract"]
    transform = _module("transform_sveservice_media", "tools/transform_sveservice_media.py")
    apk = _module("apk_entry_replace_sveservice", "tools/apk_entry_replace.py")
    contract = transform.load_contract(contract_path)
    artifact = contract["artifact"]
    if (artifact["stock_apk_sha256"] != config["stock"]["sha256"] or
            artifact["stock_apk_size"] != config["stock"]["size"] or
            artifact["stock_dex_sha256"] != config["stock"]["entries"]["classes.dex"] or
            config["stock"]["entries"]["classes.dex"] != STOCK_DEX_SHA256):
        raise BuildError("build and transform stock identities disagree")
    output_parent = output_path.parent.resolve(strict=True)
    if output_parent.is_symlink() or output_path.is_symlink():
        raise BuildError("unsafe output path")
    with tempfile.TemporaryDirectory(prefix=".sveservice-build.", dir=output_parent) as temp_name:
        work = Path(temp_name)
        decoded = work / "decoded"
        overlay = work / "overlay"
        transform_report = work / "transform-report.json"
        rebuilt = work / "apktool-output.apk"
        verify = work / "verify"
        dex = work / "classes.dex"
        jvm_args = config["toolchain"]["apktool"]["jvm_args"]
        _apktool(java, jar, jvm_args, ["d", "-f", "-o", str(decoded), str(stock)],
                 "stock decode")
        transform.transform(contract_path, decoded / "smali", overlay, transform_report)
        for path in transform.EXPECTED_PATHS:
            source = overlay.joinpath(*PurePosixPath(path).parts)
            target = (decoded / "smali").joinpath(*PurePosixPath(path).parts)
            if not source.is_file() or target.is_symlink() or not target.is_file():
                raise BuildError("overlay target drift")
            shutil.copyfile(source, target)
        _apktool(java, jar, jvm_args, ["b", str(decoded), "-o", str(rebuilt)],
                 "patched rebuild")
        rebuilt_data, _ = _zip_data(rebuilt)
        if set(rebuilt_data).isdisjoint({"classes.dex"}) or "classes.dex" not in rebuilt_data:
            raise BuildError("rebuilt DEX is missing")
        dex.write_bytes(rebuilt_data["classes.dex"])
        expected_output = config["output"]
        if dex.stat().st_size != expected_output["classes_dex_size"] or \
                sha256_file(dex) != expected_output["classes_dex_sha256"]:
            raise BuildError("deterministic DEX pin mismatch")
        try:
            assembly = apk.build_archive(stock, output_path, {"classes.dex": dex}, {})
        except (OSError, apk.SafetyError, zipfile.BadZipFile) as exc:
            raise BuildError(f"APK assembly failed: {exc}") from exc
        if assembly["output_sha256"] != expected_output["unsigned_apk_sha256"]:
            raise BuildError("deterministic APK pin mismatch")
        changed = sorted(item["entry"] for item in assembly["changed_entries"])
        if changed != expected_output["changed_entries"]:
            raise BuildError("assembled changed-entry set drift")
        output_data, output_hash = _zip_data(output_path)
        expected_data = {name: value for name, value in stock_data.items()
                         if name not in SIGNATURES}
        expected_data["classes.dex"] = dex.read_bytes()
        if output_data != expected_data:
            raise BuildError("unrelated ZIP entry changed")
        _apktool(java, jar, jvm_args, ["d", "-f", "-o", str(verify), str(output_path)],
                 "output verification decode")
        _verify_output_tree(verify / "smali", transform, contract)
        report = {
            "schema_version": 1,
            "artifact": "sveservice.apk",
            "status": "PASS",
            "stock_apk_sha256": config["stock"]["sha256"],
            "output_apk_sha256": output_hash,
            "output_dex_sha256": sha256_file(dex),
            "changed_entries": changed,
            "preserved_entry_count": assembly["preserved_entry_count"],
            "structural_invariants": [
                "compat_loader_precedes_svejni",
                "sae_create_entry_and_return_diagnostics",
                "sae_start_entry_and_return_diagnostics",
                "all_unrelated_zip_entries_byte_identical",
            ],
        }
    if report_path is not None:
        try:
            apk.atomic_json(report_path, report)
        except (OSError, apk.SafetyError) as exc:
            raise BuildError(f"cannot write report: {exc}") from exc
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--stock-apk", required=True, type=Path)
    parser.add_argument("--apktool-jar", required=True, type=Path)
    parser.add_argument("--java", default="java", help="Java launcher path or command")
    parser.add_argument("--output-apk", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        result = build(args.config, args.stock_apk, args.apktool_jar, args.java,
                       args.output_apk, args.report)
    except (OSError, UnicodeError, BuildError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
