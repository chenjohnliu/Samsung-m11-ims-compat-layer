#!/usr/bin/env python3
"""Verify and optionally stage files declared by PAYLOAD_MANIFEST.tsv."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath


REQUIRED_COLUMNS = {
    "stock_path", "destination", "stock_sha256", "stock_size",
    "architecture", "licensing_class", "action",
}
VALID_ACTIONS = {"copy", "patch-to-stage1"}
DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[1] / "devices" / "m11q" / "payload-manifest.tsv"
)


class ManifestError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(raw: str, field: str) -> Path:
    value = raw.replace("\\", "/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(p in ("", ".", "..") for p in pure.parts):
        raise ManifestError(f"unsafe {field}: {raw!r}")
    return Path(*pure.parts)


def load_manifest(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or ()))
            raise ManifestError(f"manifest is missing columns: {', '.join(missing)}")
        rows = []
        seen_sources: set[str] = set()
        seen_destinations: set[str] = set()
        for number, raw in enumerate(reader, start=2):
            source_text = raw["stock_path"]
            if not source_text.startswith("/system/"):
                raise ManifestError(f"line {number}: stock_path must start with /system/")
            source_rel = safe_relative(source_text.lstrip("/"), "stock_path")
            destination_rel = safe_relative(raw["destination"], "destination")
            source_key = source_rel.as_posix().casefold()
            destination_key = destination_rel.as_posix().casefold()
            if source_key in seen_sources:
                raise ManifestError(f"line {number}: duplicate stock_path")
            if destination_key in seen_destinations:
                raise ManifestError(f"line {number}: duplicate destination")
            seen_sources.add(source_key)
            seen_destinations.add(destination_key)
            action = raw["action"]
            if action not in VALID_ACTIONS:
                raise ManifestError(f"line {number}: unsupported action {action!r}")
            sha = raw["stock_sha256"].lower()
            if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise ManifestError(f"line {number}: invalid SHA-256")
            try:
                size = int(raw["stock_size"])
            except ValueError as exc:
                raise ManifestError(f"line {number}: invalid stock_size") from exc
            if size < 0:
                raise ManifestError(f"line {number}: invalid stock_size")
            rows.append({**raw, "source_rel": source_rel, "destination_rel": destination_rel,
                         "stock_sha256": sha, "stock_size": size})
    if not rows:
        raise ManifestError("manifest has no payload rows")
    return rows


def contained_path(root: Path, relative: Path) -> Path:
    root_resolved = root.resolve()
    candidate = (root_resolved / relative).resolve()
    if os.path.commonpath((str(root_resolved), str(candidate))) != str(root_resolved):
        raise ManifestError(f"path escapes root: {relative.as_posix()}")
    return candidate


def source_path(root: Path, relative: Path) -> Path:
    # Accept either an extraction root containing system/ or system/ itself.
    if root.name.casefold() == "system" and relative.parts[0].casefold() == "system":
        relative = Path(*relative.parts[1:])
    return contained_path(root, relative)


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def run(args: argparse.Namespace) -> tuple[dict[str, object], int]:
    manifest = args.manifest.resolve()
    rows = load_manifest(manifest)
    extracted_root = args.extracted_system_root.resolve()
    if not extracted_root.is_dir():
        raise ManifestError(f"extracted system root is not a directory: {extracted_root}")
    if args.copy and args.destination_root is None:
        raise ManifestError("--copy requires destination_root")
    if args.destination_root is not None and not args.copy:
        raise ManifestError("destination_root requires --copy")

    destination_root = args.destination_root.resolve() if args.destination_root else None
    stock_input_root = args.stock_input_dir.resolve() if args.stock_input_dir else None
    results = []
    verified = True
    for row in rows:
        source = source_path(extracted_root, row["source_rel"])
        item = {
            "stock_path": row["stock_path"],
            "destination": row["destination"],
            "action": row["action"],
            "expected_size": row["stock_size"],
            "expected_sha256": row["stock_sha256"],
            "source": str(source),
            "status": "missing",
            "copied_to": None,
        }
        if source.is_file():
            size = source.stat().st_size
            digest = sha256_file(source)
            item.update(actual_size=size, actual_sha256=digest)
            if size != row["stock_size"]:
                item["status"] = "size-mismatch"
            elif digest != row["stock_sha256"]:
                item["status"] = "sha256-mismatch"
            else:
                item["status"] = "verified"
                target = None
                if args.copy and row["action"] == "copy":
                    target = contained_path(destination_root, row["destination_rel"])
                elif row["action"] == "patch-to-stage1" and stock_input_root is not None:
                    target = contained_path(stock_input_root, row["source_rel"])
                if target is not None:
                    if target.exists() and (not target.is_file() or sha256_file(target) != digest):
                        item["status"] = "destination-conflict"
                    else:
                        if not target.exists():
                            atomic_copy(source, target)
                        item["copied_to"] = str(target)
        if item["status"] != "verified":
            verified = False
        results.append(item)

    copied = sum(item["copied_to"] is not None for item in results)
    report = {
        "schema_version": 1,
        "manifest": str(manifest),
        "extracted_system_root": str(extracted_root),
        "mode": "copy" if args.copy or stock_input_root else "verify-only",
        "verified": verified,
        "summary": {"total": len(results), "verified": sum(i["status"] == "verified" for i in results),
                    "copied": copied, "failed": sum(i["status"] != "verified" for i in results)},
        "files": results,
    }
    return report, 0 if verified else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("extracted_system_root", type=Path)
    result.add_argument("destination_root", nargs="?", type=Path)
    result.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    result.add_argument("--copy", action="store_true", help="copy only manifest rows whose action is 'copy'")
    result.add_argument("--stock-input-dir", type=Path,
                        help="explicit private staging root for patch-to-stage1 stock input")
    result.add_argument("--report", type=Path, help="also write the JSON report to this file")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report, status = run(args)
    except (ManifestError, OSError) as exc:
        report, status = {"schema_version": 1, "verified": False, "error": str(exc)}, 2
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"could not write report: {exc}", file=sys.stderr)
            return 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
