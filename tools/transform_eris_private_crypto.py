#!/usr/bin/env python3
"""Move the pinned ERIS OpenSSL dependency closure into a private namespace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile


TRANSFORMATION_ID = "ER1-private-crypto-namespace"
EXPECTED_TARGETS = {
    "libcrypto.so": ("cf6dfdaf8a57730364e2be816c45d4fbdf1d3b196f5467e340e8c998d2631040", "liberc.so", "a6c7409533f4e5b2a2a0219f97643ddfefd9c8ffdad2bb26a73be8eff6973ad2"),
    "libssl.so": ("d8eef149d87bab37c66ade6d39c3ff93d6f922dc0dd4a126a3d4cca08a3dc478", "libers.so", "b381f0f9a49c48bc74d6c7e50967fb1b146d786c240b7eb78e8608ed91af3aa9"),
    "liberis_strongswan.so": ("38aecec124684f02afd5bea9a98f538913af7b3311d5eb7e62f34429b27bbe49", "liberis_strongswan.so", "61601e70a15056cb563cdb2cc8651303ffc2b8a1cd9c2fb1ca83fd64fea55dc3"),
}


class TransformError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cstring(data: bytes, offset: int, limit: int) -> str:
    end = data.find(b"\0", offset, limit)
    if end < 0:
        raise TransformError("unterminated ELF dynamic string")
    try:
        return data[offset:end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise TransformError("non-ASCII ELF dynamic string") from exc


def elf_identity(data: bytes) -> dict[str, object]:
    if len(data) < 52 or data[:6] != b"\x7fELF\x01\x01":
        raise TransformError("input is not a little-endian ELF32 image")
    machine = struct.unpack_from("<H", data, 18)[0]
    phoff = struct.unpack_from("<I", data, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 42)
    if phentsize != 32 or phnum == 0 or phoff + phentsize * phnum > len(data):
        raise TransformError("invalid ELF program-header table")
    headers = [struct.unpack_from("<IIIIIIII", data, phoff + i * phentsize)
               for i in range(phnum)]

    def file_offset(address: int) -> int:
        matches = [p[1] + address - p[2] for p in headers
                   if p[0] == 1 and p[2] <= address < p[2] + p[5]]
        if len(matches) != 1 or not 0 <= matches[0] < len(data):
            raise TransformError("ELF virtual address is not uniquely file-backed")
        return matches[0]

    dynamic = [p for p in headers if p[0] == 2]
    if len(dynamic) != 1 or dynamic[0][1] + dynamic[0][4] > len(data):
        raise TransformError("ELF must contain exactly one valid PT_DYNAMIC")
    tags: dict[int, list[int]] = {}
    for offset in range(dynamic[0][1], dynamic[0][1] + dynamic[0][4], 8):
        tag, value = struct.unpack_from("<II", data, offset)
        if tag == 0:
            break
        tags.setdefault(tag, []).append(value)
    if len(tags.get(5, [])) != 1 or len(tags.get(10, [])) != 1:
        raise TransformError("ELF dynamic string table is ambiguous")
    strtab = file_offset(tags[5][0])
    strend = strtab + tags[10][0]
    if strend > len(data):
        raise TransformError("ELF dynamic string table is out of bounds")
    sonames = [_cstring(data, strtab + item, strend) for item in tags.get(14, [])]
    if len(sonames) != 1:
        raise TransformError("ELF must contain exactly one DT_SONAME")
    needed = [_cstring(data, strtab + item, strend) for item in tags.get(1, [])]
    return {"class": data[4], "machine": machine, "soname": sonames[0],
            "needed": needed, "strtab": (strtab, strend)}


def load_contract(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransformError(f"cannot read contract: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "transformation_id", "targets"}:
        raise TransformError("malformed contract")
    if raw["schema_version"] != 1 or raw["transformation_id"] != TRANSFORMATION_ID:
        raise TransformError("unsupported contract identity")
    targets = raw["targets"]
    if not isinstance(targets, list) or len(targets) != 3:
        raise TransformError("contract must contain exactly three targets")
    required = {"input_name", "input_sha256", "output_name", "output_sha256",
                "elf_class", "elf_machine", "soname_before", "soname_after",
                "needed_before", "needed_after", "replacements"}
    found = {}
    for item in targets:
        if not isinstance(item, dict) or set(item) != required:
            raise TransformError("malformed target contract")
        name = item["input_name"]
        if name in found or name not in EXPECTED_TARGETS:
            raise TransformError("unexpected or duplicate target")
        expected_input, expected_output_name, expected_output = EXPECTED_TARGETS[name]
        if (item["input_sha256"], item["output_name"], item["output_sha256"]) != (expected_input, expected_output_name, expected_output):
            raise TransformError("target hash or name contract drift")
        if item["elf_class"] != 1 or item["elf_machine"] != 40:
            raise TransformError("unsupported ELF identity")
        replacements = item["replacements"]
        if not isinstance(replacements, list) or not replacements:
            raise TransformError("target has no replacements")
        for replacement in replacements:
            if set(replacement) != {"old", "new", "occurrences"} or replacement["occurrences"] != 1:
                raise TransformError("malformed replacement contract")
            old, new = replacement["old"], replacement["new"]
            if old not in {"libcrypto.so", "libssl.so"} or new not in {"liberc.so", "libers.so"} or len(new) > len(old):
                raise TransformError("unsafe replacement contract")
        found[name] = item
    return raw


def transform_one(item: dict, data: bytes) -> bytes:
    digest = sha256(data)
    if digest != item["input_sha256"]:
        if digest == item["output_sha256"]:
            raise TransformError(f"{item['input_name']} is already transformed")
        raise TransformError(f"{item['input_name']} input hash drift")
    before = elf_identity(data)
    if (before["class"], before["machine"], before["soname"], before["needed"]) != (
            item["elf_class"], item["elf_machine"], item["soname_before"], item["needed_before"]):
        raise TransformError(f"{item['input_name']} ELF identity drift")
    start, end = before["strtab"]
    table = data[start:end]
    updated = table
    for replacement in item["replacements"]:
        old = replacement["old"].encode() + b"\0"
        new = replacement["new"].encode() + b"\0"
        if updated.count(old) != replacement["occurrences"]:
            raise TransformError(f"{item['input_name']} dynamic-string occurrence drift")
        updated = updated.replace(old, new.ljust(len(old), b"\0"), 1)
    output = data[:start] + updated + data[end:]
    after = elf_identity(output)
    if len(output) != len(data) or (after["soname"], after["needed"]) != (item["soname_after"], item["needed_after"]):
        raise TransformError(f"{item['input_name']} post-state drift")
    if sha256(output) != item["output_sha256"]:
        raise TransformError(f"{item['input_name']} output hash drift")
    return output


def _regular(path: Path, label: str) -> bytes:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise TransformError(f"missing {label}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise TransformError(f"{label} must be a regular non-symlink file")
    return path.read_bytes()


def transform(contract_path: Path, input_dir: Path, output_dir: Path, report_path: Path) -> dict:
    contract = load_contract(contract_path)
    if input_dir.is_symlink() or not input_dir.is_dir():
        raise TransformError("input must be a non-symlink directory")
    if output_dir.exists() or report_path.exists():
        raise TransformError("refusing to overwrite output or report")
    if output_dir.parent.is_symlink() or report_path.parent.is_symlink() or not output_dir.parent.is_dir() or not report_path.parent.is_dir():
        raise TransformError("output parents must be existing non-symlink directories")
    outputs = []
    blobs = {}
    for item in contract["targets"]:
        source = input_dir / item["input_name"]
        data = _regular(source, item["input_name"])
        transformed = transform_one(item, data)
        blobs[item["output_name"]] = transformed
        outputs.append({"input_name": item["input_name"], "output_name": item["output_name"],
                        "input_sha256": sha256(data), "output_sha256": sha256(transformed),
                        "changed_dynamic_strings": len(item["replacements"])})
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID,
               "status": "PASS", "outputs": outputs}
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    fd, temp_report_name = tempfile.mkstemp(prefix=f".{report_path.name}.", suffix=".tmp", dir=report_path.parent)
    temp_report = Path(temp_report_name)
    published_report = False
    try:
        for name, data in blobs.items():
            (temp_dir / name).write_bytes(data)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
            stream.flush(); os.fsync(stream.fileno())
        os.link(temp_report, report_path.resolve(strict=False))
        published_report = True
        os.rename(temp_dir, output_dir.resolve(strict=False))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        if published_report:
            report_path.unlink(missing_ok=True)
        for child in temp_dir.glob("*"):
            child.unlink(missing_ok=True)
        temp_dir.rmdir()
        raise
    finally:
        temp_report.unlink(missing_ok=True)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = transform(args.contract, args.input_dir, args.output_dir, args.report)
    except (OSError, TransformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
