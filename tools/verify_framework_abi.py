#!/usr/bin/env python3
"""Fail-closed verification of the Android framework JAR used by the bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Callable


HASH = re.compile(r"^[0-9a-f]{64}$")
CLASS = re.compile(r"^(?:[A-Za-z_$][\w$]*\.)+[A-Za-z_$][\w$]*$")
Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class VerificationError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_javap(text: str) -> str:
    """Normalize transport-only differences, not ABI whitespace or ordering."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def load_config(path: Path) -> dict:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read config {path}: {error}") from error
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise VerificationError("config schema_version must be 1")
    try:
        golden = config["toolchain"]["golden_framework_minus_apex"]["sha256"]
        fixture_root_text = config["abi_fixture_root"]
        fixtures = config["abi_fixtures"]
    except (KeyError, TypeError) as error:
        raise VerificationError(f"missing required config field: {error}") from error
    if not isinstance(golden, str) or not HASH.fullmatch(golden):
        raise VerificationError("golden framework SHA-256 must be 64 lowercase hex characters")
    if not isinstance(fixtures, dict) or not fixtures:
        raise VerificationError("abi_fixtures must be a non-empty object")
    if not isinstance(fixture_root_text, str) or not fixture_root_text:
        raise VerificationError("abi_fixture_root must be a non-empty path")
    fixture_root = (path.parent / fixture_root_text).resolve()
    for class_name, relative in fixtures.items():
        if not isinstance(class_name, str) or not CLASS.fullmatch(class_name):
            raise VerificationError(f"invalid ABI class name: {class_name!r}")
        if not isinstance(relative, str) or not relative:
            raise VerificationError(f"invalid fixture path for {class_name}")
        pure = PurePosixPath(relative.replace("\\", "/"))
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise VerificationError(f"fixture path is not safe root-relative: {relative!r}")
        resolved = (fixture_root / Path(*pure.parts)).resolve()
        if not resolved.is_relative_to(fixture_root):
            raise VerificationError(f"fixture path escapes fixture root: {relative!r}")
    return config


def default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def verify(
    framework_jar: Path,
    config_path: Path,
    mode: str,
    javap: str,
    runner: Runner = default_runner,
) -> dict:
    if mode not in {"golden", "compatible"}:
        raise VerificationError("mode must be 'golden' or 'compatible'")
    config = load_config(config_path)
    if not framework_jar.is_file():
        raise VerificationError(f"framework JAR is missing: {framework_jar}")
    actual_hash = sha256_file(framework_jar)
    golden_hash = config["toolchain"]["golden_framework_minus_apex"]["sha256"]
    hash_matches = actual_hash == golden_hash
    if mode == "golden" and not hash_matches:
        raise VerificationError(
            f"golden framework hash mismatch: expected={golden_hash} actual={actual_hash}"
        )

    abi_results = []
    fixture_root = (config_path.parent / config["abi_fixture_root"]).resolve()
    for class_name, relative in config["abi_fixtures"].items():
        fixture = (fixture_root / Path(*PurePosixPath(relative).parts)).resolve()
        if not fixture.is_file():
            raise VerificationError(f"ABI fixture is missing: {fixture}")
        expected = normalize_javap(fixture.read_text(encoding="utf-8"))
        if not expected:
            raise VerificationError(f"ABI fixture is empty: {fixture}")
        command = [javap, "-classpath", str(framework_jar), class_name]
        try:
            completed = runner(command)
        except OSError as error:
            raise VerificationError(f"javap could not be executed: {error}") from error
        if completed.returncode != 0:
            detail = normalize_javap(completed.stderr or completed.stdout).strip()
            raise VerificationError(
                f"javap failed for {class_name} with exit {completed.returncode}: {detail}"
            )
        actual = normalize_javap(completed.stdout)
        match = actual == expected
        abi_results.append(
            {
                "class": class_name,
                "fixture": str(fixture),
                "fixture_sha256": hashlib.sha256(expected.encode()).hexdigest(),
                "actual_sha256": hashlib.sha256(actual.encode()).hexdigest(),
                "match": match,
            }
        )
        if not match:
            raise VerificationError(f"normalized ABI mismatch for {class_name}")

    return {
        "status": "PASS",
        "mode": mode,
        "classification": "golden" if hash_matches else "compatible-abi-only",
        "framework_jar": str(framework_jar),
        "framework_sha256": actual_hash,
        "golden_framework_sha256": golden_hash,
        "golden_hash_match": hash_matches,
        "javap": javap,
        "abi": abi_results,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("framework_jar", type=Path)
    parser.add_argument("--mode", choices=("golden", "compatible"), default="golden")
    parser.add_argument("--javap", default="javap")
    parser.add_argument(
        "--config", type=Path, default=root / "devices/m11q/imsservice-build.json"
    )
    parser.add_argument("--report", type=Path)
    return parser.parse_args(argv)


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = verify(args.framework_jar, args.config, args.mode, args.javap)
    except VerificationError as error:
        report = {"status": "FAIL", "error": str(error)}
        if args.report:
            write_report(args.report, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    if args.report:
        write_report(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
