#!/usr/bin/env python3
"""Build the M11 Stage-1 IMS APK from exact local proprietary inputs.

This orchestrator never downloads firmware, publishes decoded Samsung files,
signs a ROM, or invokes an Android ROM build. All decoded/generated material is
created in a disposable directory beside the requested output.
"""

from __future__ import annotations

import argparse
import csv
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
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "devices" / "m11q" / "imsservice-build.json"
DEFAULT_PAYLOAD = ROOT / "devices" / "m11q" / "payload-manifest.tsv"
DEFAULT_BRIDGE = ROOT / "bridge" / "java"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SIGNATURES = {"META-INF/CERT.RSA", "META-INF/CERT.SF", "META-INF/MANIFEST.MF"}


class BuildError(RuntimeError):
    pass


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


def _regular(path: Path, label: str) -> Path:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise BuildError(f"missing {label}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise BuildError(f"{label} must be a regular non-symlink file")
    return path.resolve(strict=True)


def _expected_file(path: Path, label: str, digest: str, size: int | None = None) -> Path:
    actual = _regular(path, label)
    if size is not None and actual.stat().st_size != size:
        raise BuildError(f"{label} size mismatch")
    found = sha256_file(actual)
    if found != digest:
        raise BuildError(f"{label} SHA-256 mismatch: expected={digest} actual={found}")
    return actual


def _hash(value, label: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise BuildError(f"invalid configured SHA-256 for {label}")
    return value


def load_config(path: Path) -> dict:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        if config["schema_version"] != 1:
            raise BuildError("unsupported build config schema")
        if config["device"] != {
            "codename": "m11q", "model": "SM-M115F", "stock_build": "M115FXXS5CWK3",
            "stock_android": 12, "target_android": 13,
        }:
            raise BuildError("device/build identity drift")
        if config["ordered_patches"] != [
            "BC1-modern-mmtel-discovery", "BC2-modern-bridge-native-hooks",
            "BG1-network-statistics-guard", "BH1-sms-icc-type-compat",
            "BP1-sms-hqm-telemetry-guard",
        ]:
            raise BuildError("ordered transformation identity drift")
        expected_contracts = {
            "BC1-modern-mmtel-discovery": "devices/m11q/bc1-manifest-contract.json",
            "BC2-modern-bridge-native-hooks": "devices/m11q/bc2-native-hooks-contract.json",
            "BG1-network-statistics-guard": "devices/m11q/bg1-stats-guard-contract.json",
            "BH1-sms-icc-type-compat": "devices/m11q/bh1-sms-icc-type-contract.json",
            "BP1-sms-hqm-telemetry-guard": "devices/m11q/bp1-sms-hqm-telemetry-guard-contract.json",
        }
        if config["transformation_contracts"] != expected_contracts:
            raise BuildError("transformation contract mapping drift")
        _hash(config["stock_apk"]["sha256"], "stock APK")
        _hash(config["stock_framework_res"]["sha256"], "framework-res")
        for key, value in config["toolchain"].items():
            if key == "apktool":
                _hash(value["sha256"], "apktool")
                if value.get("jvm_args") != ["-XX:ActiveProcessorCount=1"]:
                    raise BuildError("apktool JVM determinism arguments drift")
            elif key == "jdk11":
                _hash(value["java_sha256"], "java")
                _hash(value["javac_sha256"], "javac")
                _hash(value["javap_sha256"], "javap")
            elif key in {"r8", "zipalign"}:
                _hash(value["sha256"], key)
        bridge = config["bridge_source"]
        if bridge["publication_status"] != "project-authored-apache-2.0":
            raise BuildError("bridge publication boundary drift")
        if not isinstance(bridge["files"], dict) or len(bridge["files"]) != 7:
            raise BuildError("bridge source manifest must contain exactly seven files")
        for relative, digest in bridge["files"].items():
            pure = PurePosixPath(relative)
            if pure.is_absolute() or ".." in pure.parts or pure.suffix != ".java":
                raise BuildError("unsafe bridge source path")
            _hash(digest, f"bridge source {relative}")
        if sorted(bridge["top_level_classes"]) != sorted(Path(x).stem for x in bridge["files"]):
            raise BuildError("bridge class/source identity drift")
        for value in config["final_dex_invariants"]["entries"].values():
            _hash(value, "final DEX")
        _hash(config["final_dex_invariants"]["unsigned_apk_sha256"],
              "final unsigned APK")
    except (KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
        raise BuildError(f"malformed build config: {exc}") from exc
    return config


def payload_identity(path: Path, stock_path: str) -> tuple[str, int]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
    except OSError as exc:
        raise BuildError(f"cannot read payload manifest: {exc}") from exc
    matches = [row for row in rows if row.get("stock_path") == stock_path]
    if len(matches) != 1:
        raise BuildError(f"payload identity occurrence drift: {stock_path}")
    digest = _hash(matches[0].get("stock_sha256"), stock_path)
    try:
        size = int(matches[0]["stock_size"])
    except (KeyError, ValueError) as exc:
        raise BuildError(f"invalid payload size: {stock_path}") from exc
    return digest, size


def _run(command: list[str], label: str, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                                check=False)
    except OSError as exc:
        raise BuildError(f"cannot execute {label}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace("\r", " ").replace("\n", " ")
        raise BuildError(f"{label} failed with exit {result.returncode}: {detail[:500]}")
    return result.stdout.strip()


def _copy_overlay(overlay: Path, decoded_smali: Path, expected: set[str]) -> None:
    found = {item.relative_to(overlay).as_posix() for item in overlay.rglob("*") if item.is_file()}
    if found != expected:
        raise BuildError(f"overlay inventory drift: expected={sorted(expected)} found={sorted(found)}")
    for relative in sorted(expected):
        source = overlay.joinpath(*PurePosixPath(relative).parts)
        target = decoded_smali.joinpath(*PurePosixPath(relative).parts)
        if not target.is_file() or target.is_symlink():
            raise BuildError(f"overlay target is missing or unsafe: {relative}")
        shutil.copyfile(source, target)


def _bridge_sources(root: Path, config: dict) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise BuildError("bridge source root must be a non-symlink directory")
    resolved = root.resolve(strict=True)
    expected = config["bridge_source"]["files"]
    actual_java = {item.relative_to(resolved).as_posix() for item in resolved.rglob("*.java")
                   if item.is_file()}
    if actual_java != set(expected):
        raise BuildError("bridge source inventory drift")
    sources = []
    for relative, digest in expected.items():
        candidate = resolved.joinpath(*PurePosixPath(relative).parts)
        sources.append(_expected_file(candidate, f"bridge source {relative}", digest))
    return sources


def _bridge_jar(classes: Path, destination: Path, config: dict) -> dict:
    package = classes / "com" / "sec" / "internal" / "google"
    names = set(config["bridge_source"]["top_level_classes"])
    selected = {}
    for item in package.rglob("*.class") if package.is_dir() else []:
        stem = item.name[:-6]
        owner = stem.split("$", 1)[0]
        if owner in names:
            selected[item.relative_to(classes).as_posix()] = item.read_bytes()
    for name in names:
        if f"com/sec/internal/google/{name}.class" not in selected:
            raise BuildError(f"missing compiled bridge class: {name}")
    if not selected:
        raise BuildError("no bridge classes selected")
    with zipfile.ZipFile(destination, "w", allowZip64=False) as archive:
        for name, data in sorted(selected.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    return {"class_count": len(selected), "sha256": sha256_file(destination)}


def _zip_data(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise BuildError("duplicate output APK entries")
            bad = archive.testzip()
            if bad is not None:
                raise BuildError(f"output APK CRC failure: {bad}")
            return {name: archive.read(name) for name in names}
    except zipfile.BadZipFile as exc:
        raise BuildError("invalid output APK") from exc


def _verify_zip(stock: Path, candidate: Path, config: dict) -> dict:
    before, after = _zip_data(stock), _zip_data(candidate)
    expected_names = (set(before) - SIGNATURES) | {"classes2.dex"}
    if set(after) != expected_names:
        raise BuildError("final APK entry inventory drift")
    changed = []
    for name in sorted(set(before) | set(after)):
        if before.get(name) != after.get(name):
            changed.append(name)
    allowed = SIGNATURES | {"AndroidManifest.xml", "classes.dex", "classes2.dex"}
    if set(changed) - allowed:
        raise BuildError(f"undeclared final APK entry changes: {sorted(set(changed) - allowed)}")
    expected_dex = config["final_dex_invariants"]["entries"]
    for name, digest in expected_dex.items():
        if hashlib.sha256(after[name]).hexdigest() != digest:
            raise BuildError(f"final {name} hash mismatch")
    apk_digest = sha256_file(candidate)
    if apk_digest != config["final_dex_invariants"]["unsigned_apk_sha256"]:
        raise BuildError("final unsigned APK hash mismatch: "
                         f"expected={config['final_dex_invariants']['unsigned_apk_sha256']} "
                         f"actual={apk_digest}")
    return {"entry_count": len(after), "changed_entries": changed,
            "dex_sha256": {name: hashlib.sha256(after[name]).hexdigest()
                           for name in sorted(expected_dex)}}


def _publish_pair(candidate: Path, output: Path, report: Path, payload: dict) -> None:
    if output.exists() or report.exists() or output.is_symlink() or report.is_symlink():
        raise BuildError("refusing to overwrite output or report")
    if output.parent.is_symlink() or report.parent.is_symlink() or not output.parent.is_dir() or not report.parent.is_dir():
        raise BuildError("output parents must be existing non-symlink directories")
    output_abs = output.parent.resolve(strict=True) / output.name
    report_abs = report.parent.resolve(strict=True) / report.name
    if output_abs == report_abs:
        raise BuildError("output and report must be distinct")
    output_fd, output_temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    report_fd, report_temp_name = tempfile.mkstemp(
        prefix=f".{report.name}.", suffix=".tmp", dir=report.parent)
    os.close(output_fd)
    os.close(report_fd)
    output_temp = Path(output_temp_name)
    report_temp = Path(report_temp_name)
    output_published = False
    try:
        with output_temp.open("wb") as stream, candidate.open("rb") as source:
            shutil.copyfileobj(source, stream)
            stream.flush(); os.fsync(stream.fileno())
        with report_temp.open("wb") as stream:
            stream.write((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
            stream.flush(); os.fsync(stream.fileno())
        os.rename(output_temp, output_abs)
        output_published = True
        os.link(report_temp, report_abs)
    except BaseException:
        if output_published:
            try: output_abs.unlink()
            except FileNotFoundError: pass
        try: report_abs.unlink()
        except FileNotFoundError: pass
        raise
    finally:
        try: output_temp.unlink()
        except FileNotFoundError: pass
        try: report_temp.unlink()
        except FileNotFoundError: pass


def build(args: argparse.Namespace) -> dict:
    config_path = _regular(args.config, "build config")
    payload_path = _regular(args.payload_manifest, "payload manifest")
    config = load_config(config_path)
    stock = _expected_file(args.stock_apk, "stock IMS APK",
                           config["stock_apk"]["sha256"], config["stock_apk"]["size"])
    framework_res = _expected_file(args.framework_res_apk, "stock framework-res APK",
                                   config["stock_framework_res"]["sha256"],
                                   config["stock_framework_res"]["size"])
    manager_hash, manager_size = payload_identity(payload_path, "/system/framework/imsmanager.jar")
    imsmanager = _expected_file(args.imsmanager_jar, "stock imsmanager JAR",
                                manager_hash, manager_size)
    tools = {
        "apktool": _expected_file(args.apktool_jar, "apktool JAR",
                                  config["toolchain"]["apktool"]["sha256"]),
        "java": _expected_file(args.java, "java", config["toolchain"]["jdk11"]["java_sha256"]),
        "javac": _expected_file(args.javac, "javac", config["toolchain"]["jdk11"]["javac_sha256"]),
        "r8": _expected_file(args.r8_jar, "R8 JAR", config["toolchain"]["r8"]["sha256"]),
        "zipalign": _expected_file(args.zipalign, "zipalign", config["toolchain"]["zipalign"]["sha256"]),
    }
    framework = _regular(args.framework_jar, "Android framework JAR")
    javap = _expected_file(args.javap, "javap",
                           config["toolchain"]["jdk11"]["javap_sha256"])
    sources = _bridge_sources(args.bridge_source_root, config)

    output = args.output
    report = args.report
    if output.exists() or report.exists():
        raise BuildError("refusing to overwrite output or report")
    if output.parent.is_symlink() or report.parent.is_symlink() or not output.parent.is_dir() or not report.parent.is_dir():
        raise BuildError("output parents must be existing non-symlink directories")
    work_parent = args.work_dir if args.work_dir is not None else output.parent
    if work_parent.is_symlink() or not work_parent.is_dir():
        raise BuildError("work directory must be an existing non-symlink directory")
    stage = Path(tempfile.mkdtemp(prefix=".m11-ims-build-", dir=work_parent))
    try:
        framework_dir = stage / "apktool-framework"
        decoded = stage / "imsservice-decoded"
        manager_decoded = stage / "imsmanager-decoded"
        framework_dir.mkdir()
        apktool = ([str(tools["java"])] + config["toolchain"]["apktool"]["jvm_args"]
                   + ["-jar", str(tools["apktool"])])
        if _run(apktool + ["--version"], "apktool version") != config["toolchain"]["apktool"]["version"]:
            raise BuildError("apktool version output mismatch")
        _run(apktool + ["if", "-p", str(framework_dir), str(framework_res)],
             "install private framework-res")
        _run(apktool + ["d", "-f", "-p", str(framework_dir), str(stock), "-o", str(decoded)],
             "decode stock IMS APK")
        _run(apktool + ["d", "-f", "-p", str(framework_dir), str(imsmanager),
                        "-o", str(manager_decoded)], "decode stock imsmanager JAR")

        bc1 = _module("m11_bc1", "tools/transform_bc1_manifest.py")
        bc2 = _module("m11_bc2", "tools/transform_bc2_native_hooks.py")
        bg1 = _module("m11_bg1", "tools/transform_bg1_stats_guard.py")
        bh1 = _module("m11_bh1", "tools/transform_bh1_sms_icc_type.py")
        bp1 = _module("m11_bp1", "tools/transform_bp1_sms_hqm_guard.py")
        stubs = _module("m11_stubs", "tools/generate_compile_stubs.py")
        abi = _module("m11_abi", "tools/verify_framework_abi.py")
        packer = _module("m11_packer", "tools/apk_entry_replace.py")
        contracts = {name: ROOT / relative for name, relative in config["transformation_contracts"].items()}
        transform_reports = {}

        bc1_out = stage / "bc1-manifest.xml"
        transform_reports["BC1-modern-mmtel-discovery"] = bc1.transform(
            contracts["BC1-modern-mmtel-discovery"], decoded / "AndroidManifest.xml", bc1_out)
        shutil.copyfile(bc1_out, decoded / "AndroidManifest.xml")

        bc2_overlay, bc2_report = stage / "bc2-overlay", stage / "bc2-report.json"
        transform_reports["BC2-modern-bridge-native-hooks"] = bc2.transform(
            contracts["BC2-modern-bridge-native-hooks"], decoded / "smali",
            bc2_overlay, bc2_report)
        _copy_overlay(bc2_overlay, decoded / "smali", bc2.EXPECTED_PATHS)

        bg1_overlay, bg1_report = stage / "bg1-overlay", stage / "bg1-report.json"
        transform_reports["BG1-network-statistics-guard"] = bg1.transform(
            contracts["BG1-network-statistics-guard"], decoded / "smali",
            bg1_overlay, bg1_report)
        _copy_overlay(bg1_overlay, decoded / "smali", bg1.EXPECTED_PATHS)

        bh1_overlay, bh1_report = stage / "bh1-overlay", stage / "bh1-report.json"
        transform_reports["BH1-sms-icc-type-compat"] = bh1.transform(
            contracts["BH1-sms-icc-type-compat"], decoded / "smali",
            bh1_overlay, bh1_report)
        _copy_overlay(bh1_overlay, decoded / "smali", bh1.EXPECTED_PATHS)

        bp1_overlay, bp1_report = stage / "bp1-overlay", stage / "bp1-report.json"
        transform_reports["BP1-sms-hqm-telemetry-guard"] = bp1.transform(
            contracts["BP1-sms-hqm-telemetry-guard"], decoded / "smali",
            bp1_overlay, bp1_report)
        _copy_overlay(bp1_overlay, decoded / "smali", bp1.EXPECTED_PATHS)

        stub_dir, stub_report = stage / "compile-stubs", stage / "stub-report.json"
        stub_result = stubs.generate(ROOT / "devices/m11q/compile-stub-contract.json",
            {"imsmanager": manager_decoded / "smali", "imsservice": decoded / "smali"},
            stub_dir, stub_report)

        abi_result = abi.verify(framework, config_path, args.framework_mode, str(javap))
        classes = stage / "classes"
        classes.mkdir()
        stub_sources = sorted(stub_dir.rglob("*.java"))
        _run([str(tools["javac"]), "-source", "8", "-target", "8", "-classpath",
              str(framework), "-d", str(classes)] + [str(x) for x in sources + stub_sources],
             "compile modern bridge")
        bridge_jar = stage / "bridge.jar"
        bridge_info = _bridge_jar(classes, bridge_jar, config)
        dex_dir = stage / "bridge-dex"
        dex_dir.mkdir()
        _run([str(tools["java"]), "-cp", str(tools["r8"]),
              "com.android.tools.r8.D8", "--min-api", "30", "--lib", str(framework),
              "--output", str(dex_dir), str(bridge_jar)], "D8 bridge compilation")
        bridge_dex = dex_dir / "classes.dex"
        if not bridge_dex.is_file() or set(x.name for x in dex_dir.iterdir()) != {"classes.dex"}:
            raise BuildError("D8 bridge output inventory drift")
        expected_bridge_dex = config["final_dex_invariants"]["entries"]["classes2.dex"]
        actual_bridge_dex = sha256_file(bridge_dex)
        if actual_bridge_dex != expected_bridge_dex:
            raise BuildError("bridge classes2.dex hash mismatch: "
                             f"expected={expected_bridge_dex} actual={actual_bridge_dex}")

        rebuilt = stage / "rebuilt.apk"
        _run(apktool + ["b", "-p", str(framework_dir), str(decoded), "-o", str(rebuilt)],
             "assemble transformed primary DEX")
        rebuilt_data = _zip_data(rebuilt)
        for name in ("AndroidManifest.xml", "classes.dex"):
            if name not in rebuilt_data:
                raise BuildError(f"rebuilt APK is missing {name}")
            (stage / name).write_bytes(rebuilt_data[name])
        expected_primary = config["final_dex_invariants"]["entries"]["classes.dex"]
        actual_primary = hashlib.sha256(rebuilt_data["classes.dex"]).hexdigest()
        if actual_primary != expected_primary:
            raise BuildError("primary classes.dex hash mismatch: "
                             f"expected={expected_primary} actual={actual_primary}")

        unaligned = stage / "candidate-unaligned.apk"
        packer.build_archive(stock, unaligned,
            {"AndroidManifest.xml": stage / "AndroidManifest.xml",
             "classes.dex": stage / "classes.dex"},
            {"classes2.dex": bridge_dex})
        aligned = stage / "candidate.apk"
        _run([str(tools["zipalign"]), "-p", "-f", "4", str(unaligned), str(aligned)],
             "zipalign candidate")
        _run([str(tools["zipalign"]), "-c", "4", str(aligned)], "verify zip alignment")
        zip_result = _verify_zip(stock, aligned, config)

        verified = stage / "verified"
        _run(apktool + ["d", "-f", "-p", str(framework_dir), str(aligned), "-o", str(verified)],
             "redecode final candidate")
        tree = ET.parse(verified / "AndroidManifest.xml")
        bc1._validate_result(tree, bc1.load_contract(contracts["BC1-modern-mmtel-discovery"]))
        for marker in ("Lcom/sec/internal/google/ModernCallRelay;->constructionListener",
                        "Lcom/sec/internal/google/ModernVoiceContext;->onIncoming",
                        "Lcom/sec/internal/google/ImsSmsImpl;->getIccTypeCompat(I)I",
                        "BP1: default SMS role unavailable; HQM CSDA omitted"):
            if not any(marker in item.read_text(encoding="utf-8")
                       for item in (verified / "smali").rglob("*.smali")):
                raise BuildError(f"final primary DEX is missing hook: {marker}")
        bridge_defs = {item.stem.split("$", 1)[0] for item in
                       (verified / "smali_classes2/com/sec/internal/google").glob("*.smali")}
        if bridge_defs != set(config["bridge_source"]["top_level_classes"]):
            raise BuildError("final bridge class inventory drift or compile-stub leakage")
        for marker in (
                "BQ2: Voice capability reconciled from normal Samsung mmtel registration",
                "BQ3: Voice enablement restored across feature recreation"):
            if not any(marker in item.read_text(encoding="utf-8") for item in
                       (verified / "smali_classes2/com/sec/internal/google").rglob("*.smali")):
                raise BuildError(f"final bridge DEX is missing recovery marker: {marker}")

        payload = {
            "schema_version": 1,
            "status": "PASS",
            "device": config["device"],
            "inputs": {
                "stock_apk_sha256": sha256_file(stock),
                "stock_framework_res_sha256": sha256_file(framework_res),
                "stock_imsmanager_sha256": sha256_file(imsmanager),
                "framework_sha256": abi_result["framework_sha256"],
                "framework_classification": abi_result["classification"],
                "bridge_source_sha256": config["bridge_source"]["files"],
            },
            "toolchain": {
                "apktool_sha256": sha256_file(tools["apktool"]),
                "java_sha256": sha256_file(tools["java"]),
                "javac_sha256": sha256_file(tools["javac"]),
                "javap_sha256": sha256_file(javap),
                "r8_sha256": sha256_file(tools["r8"]),
                "zipalign_sha256": sha256_file(tools["zipalign"]),
            },
            "transformations": [{"id": name, "files": result.get("files", []),
                                  "changed": result.get("changed", True)}
                                 for name, result in transform_reports.items()],
            "compile_stubs": {"class_count": stub_result["class_count"],
                              "method_provenance_counts": stub_result["method_provenance_counts"],
                              "candidate_dex_eligible": False},
            "bridge": bridge_info,
            "output": {**zip_result, "apk_sha256": sha256_file(aligned),
                       "signed": False, "runtime_validated": False},
            "safety": {"stock_tree_published": False, "generated_stubs_packaged": False,
                       "platform_key_used": False, "rom_build_run": False},
        }
        _publish_pair(aligned, output, report, payload)
        return payload
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--stock-apk", required=True, type=Path)
    result.add_argument("--framework-res-apk", required=True, type=Path)
    result.add_argument("--imsmanager-jar", required=True, type=Path)
    result.add_argument("--bridge-source-root", type=Path, default=DEFAULT_BRIDGE,
                        help="bridge source tree (default: repository bridge/java)")
    result.add_argument("--framework-jar", required=True, type=Path)
    result.add_argument("--framework-mode", choices=("golden", "compatible"), default="golden")
    result.add_argument("--apktool-jar", required=True, type=Path)
    result.add_argument("--java", required=True, type=Path)
    result.add_argument("--javac", required=True, type=Path)
    result.add_argument("--javap", required=True, type=Path)
    result.add_argument("--r8-jar", required=True, type=Path)
    result.add_argument("--zipalign", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--report", required=True, type=Path)
    result.add_argument("--work-dir", type=Path,
                        help="private temporary parent; use a native filesystem for speed")
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    result.add_argument("--payload-manifest", type=Path, default=DEFAULT_PAYLOAD)
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        payload = build(args)
    except (BuildError, OSError, ValueError, ET.ParseError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": payload["status"],
                      "apk_sha256": payload["output"]["apk_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
