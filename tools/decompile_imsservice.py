#!/usr/bin/env python3
"""Decode a caller-supplied IMS APK with a private apktool framework cache.

This helper only installs framework resources into an isolated apktool cache
and decodes the APK. It does not build, sign, install, or modify the input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


MIN_APKTOOL = (2, 9, 3)


class DecompileError(RuntimeError):
    pass


def regular_file(path: Path, label: str) -> Path:
    try:
        if path.is_symlink() or not path.is_file():
            raise DecompileError(f"{label} must be a regular, non-symlink file: {path}")
        return path.resolve(strict=True)
    except OSError as exc:
        raise DecompileError(f"cannot access {label}: {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_zip(path: Path, label: str, required: set[str] | None = None) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise DecompileError(f"{label} contains duplicate ZIP entries: {path}")
            if required and not required.issubset(names):
                missing = ", ".join(sorted(required - set(names)))
                raise DecompileError(f"{label} is missing required ZIP entries ({missing}): {path}")
            return names
    except (OSError, zipfile.BadZipFile) as exc:
        raise DecompileError(f"{label} is not a readable ZIP/APK: {path}: {exc}") from exc


def resolve_java(value: str) -> str:
    found = shutil.which(value)
    if found is None:
        raise DecompileError(f"Java executable is not available on PATH: {value}")
    return str(Path(found).resolve())


def run(command: list[str], label: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=False)
    except OSError as exc:
        raise DecompileError(f"could not start {label}: {exc}") from exc
    if result.returncode:
        details = (result.stderr or result.stdout).strip()
        raise DecompileError(
            f"{label} failed (exit {result.returncode})"
            + (f":\n{details}" if details else ""))
    return result


def apktool_version(raw: str) -> tuple[str, tuple[int, int, int]]:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?:[-+][A-Za-z0-9.-]+)?", raw)
    if not match:
        raise DecompileError(f"could not parse apktool version output: {raw.strip()!r}")
    parts = tuple(int(part) for part in match.groups())
    return match.group(0), parts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True, type=Path, help="IMS APK to decode")
    parser.add_argument("--framework-res", required=True, type=Path,
                        help="framework-res.apk from the same firmware as --apk")
    parser.add_argument("--apktool", required=True, type=Path, help="local apktool JAR")
    parser.add_argument("--java", default="java", metavar="JAVA_EXECUTABLE",
                        help="Java executable (default: java found on PATH)")
    parser.add_argument("--output", required=True, type=Path,
                        help="new output root; it must not already exist")
    args = parser.parse_args(argv)

    try:
        apk = regular_file(args.apk, "IMS APK")
        framework = regular_file(args.framework_res, "framework-res APK")
        apktool = regular_file(args.apktool, "apktool JAR")
        if apk.samefile(framework):
            raise DecompileError("--apk and --framework-res must be different files")
        apk_entries = require_zip(apk, "IMS APK", {"AndroidManifest.xml"})
        require_zip(framework, "framework-res APK", {"resources.arsc"})
        java = resolve_java(args.java)

        java_version = run([java, "-version"], "Java version check")
        java_text = (java_version.stderr or java_version.stdout).strip().splitlines()
        apktool_result = run([java, "-jar", str(apktool), "--version"], "apktool version check")
        version_text = (apktool_result.stdout or apktool_result.stderr).strip()
        observed_version, version_parts = apktool_version(version_text)
        if version_parts < MIN_APKTOOL:
            raise DecompileError(
                f"apktool {observed_version} is too old; version 2.9.3 or newer is required")

        output = args.output.absolute()
        if output.exists() or output.is_symlink():
            raise DecompileError(f"output root already exists; choose a new path: {output}")
        if not output.parent.is_dir():
            raise DecompileError(f"output parent directory does not exist: {output.parent}")

        output.mkdir()
        framework_cache = output / "framework"
        decoded = output / "decoded"
        framework_cache.mkdir()
        print("Installing framework into the private cache...", flush=True)
        run([java, "-jar", str(apktool), "if", str(framework),
             "-p", str(framework_cache)], "apktool framework install")
        print("Decoding IMS APK (manifest, resources and all DEX files)...", flush=True)
        run([java, "-jar", str(apktool), "d", str(apk),
             "-p", str(framework_cache), "-o", str(decoded)], "apktool decode")

        manifest = decoded / "AndroidManifest.xml"
        if not manifest.is_file() or manifest.is_symlink():
            raise DecompileError(f"decoded manifest was not produced: {manifest}")
        smali_dirs = sorted(
            path.relative_to(decoded).as_posix()
            for path in decoded.iterdir()
            if path.is_dir() and not path.is_symlink()
            and re.fullmatch(r"smali(?:_classes\d+)?", path.name))
        if not smali_dirs:
            raise DecompileError("decoded APK contains no smali/DEX directory")

        dex_entries = sorted(name for name in apk_entries
                             if re.fullmatch(r"classes(?:\d+)?\.dex", name))
        receipt = {
            "schema_version": 1,
            "operation": "decode-only",
            "inputs": {
                "ims_apk": {"sha256": sha256_file(apk), "size": apk.stat().st_size},
                "framework_res_apk": {
                    "sha256": sha256_file(framework), "size": framework.stat().st_size},
                "apktool_jar": {"sha256": sha256_file(apktool), "size": apktool.stat().st_size},
            },
            "tools": {"apktool_version": observed_version,
                      "java_version": java_text[0] if java_text else "version output unavailable"},
            "output": {"decoded_directory": "decoded",
                       "smali_directories": smali_dirs,
                       "input_dex_entries": dex_entries},
        }
        (output / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Decoded APK to: {decoded}")
        print(f"Framework cache: {framework_cache}")
        print(f"APK DEX entries: {', '.join(dex_entries) if dex_entries else '(none)'}")
        print(f"Smali directories: {', '.join(smali_dirs)}")
        print("Decoded smali is disassembled bytecode, not original Java source.")
        return 0
    except (DecompileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
