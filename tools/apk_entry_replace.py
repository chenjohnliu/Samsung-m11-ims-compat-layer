#!/usr/bin/env python3
"""Safely replace an explicit set of entries in an unsigned APK/ZIP.

This module intentionally knows nothing about Android or proprietary payloads.  It
preserves every base entry except the three exact APK v1 signature names, replaces
only named existing entries, and adds entries only through ``--add``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import zipfile


SIGNATURE_ENTRIES = frozenset(
    {"META-INF/CERT.RSA", "META-INF/CERT.SF", "META-INF/MANIFEST.MF"}
)


class SafetyError(Exception):
    """An unsafe or ambiguous input was rejected."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_entry_name(name: str, *, directory_ok: bool = True) -> None:
    if not name or "\x00" in name or "\\" in name:
        raise SafetyError(f"unsafe ZIP entry name: {name!r}")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise SafetyError(f"absolute ZIP entry name: {name!r}")
    raw = name[:-1] if directory_ok and name.endswith("/") else name
    if not raw or name.endswith("//"):
        raise SafetyError(f"unsafe ZIP entry name: {name!r}")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SafetyError(f"non-canonical ZIP entry name: {name!r}")
    if str(PurePosixPath(raw)) != raw:
        raise SafetyError(f"non-canonical ZIP entry name: {name!r}")


def validate_zip_info(info: zipfile.ZipInfo) -> None:
    validate_entry_name(info.filename)
    mode = (info.external_attr >> 16) & 0xFFFF
    kind = stat.S_IFMT(mode)
    if stat.S_ISLNK(mode):
        raise SafetyError(f"symlink-like ZIP entry rejected: {info.filename!r}")
    if kind and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        raise SafetyError(f"special-file ZIP entry rejected: {info.filename!r}")
    if info.is_dir() and kind and not stat.S_ISDIR(mode):
        raise SafetyError(f"directory/type mismatch: {info.filename!r}")
    if not info.is_dir() and stat.S_ISDIR(mode):
        raise SafetyError(f"file/type mismatch: {info.filename!r}")


def read_mapping(values: list[str], option: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SafetyError(f"{option} requires ENTRY=FILE: {value!r}")
        name, source_text = value.split("=", 1)
        validate_entry_name(name, directory_ok=False)
        if name in result:
            raise SafetyError(f"duplicate {option} entry: {name!r}")
        source = Path(source_text)
        try:
            source_stat = source.lstat()
        except FileNotFoundError as error:
            raise SafetyError(f"missing replacement source: {source}") from error
        if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
            raise SafetyError(f"replacement source must be a regular non-symlink file: {source}")
        result[name] = source
    return result


def load_base(path: Path) -> tuple[list[zipfile.ZipInfo], dict[str, bytes], bytes]:
    if not path.is_file():
        raise SafetyError(f"base ZIP does not exist: {path}")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            duplicates = sorted({name for name in names if names.count(name) > 1})
            if duplicates:
                raise SafetyError(f"duplicate base ZIP entries: {duplicates}")
            for info in infos:
                validate_zip_info(info)
            bad = archive.testzip()
            if bad is not None:
                raise SafetyError(f"base ZIP CRC failure: {bad!r}")
            data = {info.filename: archive.read(info) for info in infos}
            return infos, data, archive.comment
    except zipfile.BadZipFile as error:
        raise SafetyError(f"invalid base ZIP: {path}") from error


def addition_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.flag_bits |= 0x800
    return info


def changed_inventory(
    base_data: dict[str, bytes], output_data: dict[str, bytes]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for name in sorted(set(base_data) | set(output_data)):
        before = base_data.get(name)
        after = output_data.get(name)
        if before == after:
            continue
        if before is None:
            status = "added"
        elif after is None:
            status = "removed"
        else:
            status = "replaced"
        result.append(
            {
                "entry": name,
                "status": status,
                "before_size": None if before is None else len(before),
                "before_sha256": None if before is None else sha256_bytes(before),
                "after_size": None if after is None else len(after),
                "after_sha256": None if after is None else sha256_bytes(after),
            }
        )
    return result


def build_archive(
    base: Path,
    output: Path,
    replacements: dict[str, Path],
    additions: dict[str, Path],
) -> dict[str, object]:
    if set(replacements) & set(additions):
        raise SafetyError("an entry cannot be both a replacement and an addition")
    if base.resolve() == output.resolve():
        raise SafetyError("output must not be the base ZIP")

    infos, base_data, comment = load_base(base)
    base_names = set(base_data)
    missing = sorted(set(replacements) - base_names)
    if missing:
        raise SafetyError(f"expected replacement entries are missing from base: {missing}")
    existing_additions = sorted(set(additions) & base_names)
    if existing_additions:
        raise SafetyError(f"--add cannot replace existing entries: {existing_additions}")
    signature_mapping = sorted((set(replacements) | set(additions)) & SIGNATURE_ENTRIES)
    if signature_mapping:
        raise SafetyError(f"signature entries cannot be replaced or added: {signature_mapping}")

    replacement_data = {name: path.read_bytes() for name, path in replacements.items()}
    addition_data = {name: path.read_bytes() for name, path in additions.items()}
    expected_data = {
        name: data for name, data in base_data.items() if name not in SIGNATURE_ENTRIES
    }
    expected_data.update(replacement_data)
    expected_data.update(addition_data)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
        ) as temporary:
            temporary_name = temporary.name
        temporary_path = Path(temporary_name)
        with zipfile.ZipFile(temporary_path, "w", allowZip64=True) as archive:
            archive.comment = comment
            for info in infos:
                name = info.filename
                if name in SIGNATURE_ENTRIES:
                    continue
                archive.writestr(info, replacement_data.get(name, base_data[name]))
            for name in sorted(addition_data):
                archive.writestr(addition_info(name), addition_data[name])

        out_infos, output_data, _ = load_base(temporary_path)
        del out_infos
        if output_data != expected_data:
            actual_changes = changed_inventory(base_data, output_data)
            raise SafetyError(f"unexpected changed entry after assembly: {actual_changes}")

        intended_hash = sha256_file(temporary_path)
        if output.exists():
            if not output.is_file() or output.is_symlink():
                raise SafetyError(f"existing output is not a regular file: {output}")
            existing_hash = sha256_file(output)
            if existing_hash != intended_hash:
                raise SafetyError(
                    f"refusing to overwrite different output: {output} "
                    f"(existing={existing_hash}, intended={intended_hash})"
                )
            temporary_path.unlink()
            temporary_name = None
        else:
            # Windows rejects fsync on a read-only descriptor.  rb+ does not
            # alter the archive, but supplies a descriptor that can be flushed
            # durably before the atomic rename.
            with temporary_path.open("rb+") as assembled:
                os.fsync(assembled.fileno())
            os.replace(temporary_path, output)
            temporary_name = None

        changes = changed_inventory(base_data, output_data)
        allowed = set(replacements) | set(additions) | (base_names & SIGNATURE_ENTRIES)
        unexpected = sorted({item["entry"] for item in changes} - allowed)
        if unexpected:
            raise SafetyError(f"unexpected changed entries: {unexpected}")
        return {
            "status": "PASS",
            "base": str(base),
            "base_sha256": sha256_file(base),
            "output": str(output),
            "output_sha256": sha256_file(output),
            "requested_replacements": sorted(replacements),
            "explicit_additions": sorted(additions),
            "removed_signatures": sorted(base_names & SIGNATURE_ENTRIES),
            "preserved_entry_count": len(base_names - {item["entry"] for item in changes}),
            "changed_entries": changes,
        }
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def atomic_json(path: Path, report: dict[str, object]) -> None:
    encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as temporary:
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path, help="base APK/ZIP")
    parser.add_argument("output", type=Path, help="new APK/ZIP; never overwrites different content")
    parser.add_argument(
        "--replace", action="append", default=[], metavar="ENTRY=FILE",
        help="replace an entry that must already exist (repeatable)",
    )
    parser.add_argument(
        "--add", action="append", default=[], metavar="ENTRY=FILE",
        help="explicitly allow and add a new entry (repeatable)",
    )
    parser.add_argument("--report", type=Path, help="write changed-entry JSON atomically")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        replacements = read_mapping(args.replace, "--replace")
        additions = read_mapping(args.add, "--add")
        report = build_archive(args.base, args.output, replacements, additions)
        if args.report:
            atomic_json(args.report, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, SafetyError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
