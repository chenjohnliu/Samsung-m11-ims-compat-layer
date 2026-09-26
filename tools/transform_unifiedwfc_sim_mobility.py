#!/usr/bin/env python3
"""Disable the pinned UnifiedWFC SIM-mobility extension in-place in its DEX."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import zlib


ROOT = Path(__file__).resolve().parents[1]
TRANSFORMATION_ID = "UW1-disable-sim-mobility-extension"
EXPECTED = {
    "stock_apk_sha256": "f75fb6ae72bab70aeec85e6b2db30d804cbddb026bd022761cbfd22e5e3889c7",
    "entry_input_sha256": "afbbbd4f7eeca73bd1584e2fce7091ba1c4d61243d8d5312aac069b0b1b25e0e",
    "entry_output_sha256": "baecec81eb0eb32422071b4f52abce9af6c71a8e06aae208aa5f6ded735632d0",
    "output_apk_sha256": "99f89de78d5ef798b47a444027dd29c65962a00c1adece9975027f0d00e35c1a",
    "class": "Lcom/sec/unifiedwfc/util/w;", "name": "M0",
    "prototype": "(Landroid/content/Context;I)Z",
}


class TransformError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _uleb(data: bytes, offset: int) -> tuple[int, int]:
    value = shift = 0
    for _ in range(5):
        if offset >= len(data):
            raise TransformError("truncated DEX ULEB128")
        byte = data[offset]; offset += 1
        value |= (byte & 0x7f) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
    raise TransformError("oversized DEX ULEB128")


class Dex:
    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 112 or data[:4] != b"dex\n" or data[7] != 0:
            raise TransformError("classes.dex is not a supported DEX image")
        if struct.unpack_from("<I", data, 32)[0] != len(data):
            raise TransformError("DEX file size drift")
        self.string_size, self.string_off = struct.unpack_from("<II", data, 0x38)
        self.type_size, self.type_off = struct.unpack_from("<II", data, 0x40)
        self.proto_size, self.proto_off = struct.unpack_from("<II", data, 0x48)
        self.method_size, self.method_off = struct.unpack_from("<II", data, 0x58)
        self.class_size, self.class_off = struct.unpack_from("<II", data, 0x60)
        for size, offset, width in ((self.string_size, self.string_off, 4),
                                    (self.type_size, self.type_off, 4),
                                    (self.proto_size, self.proto_off, 12),
                                    (self.method_size, self.method_off, 8),
                                    (self.class_size, self.class_off, 32)):
            if offset + size * width > len(data):
                raise TransformError("DEX table is out of bounds")

    def string(self, index: int) -> str:
        if not 0 <= index < self.string_size:
            raise TransformError("DEX string index out of bounds")
        offset = struct.unpack_from("<I", self.data, self.string_off + index * 4)[0]
        _, offset = _uleb(self.data, offset)
        end = self.data.find(b"\0", offset)
        if end < 0:
            raise TransformError("unterminated DEX string")
        try:
            return self.data[offset:end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransformError("invalid DEX string") from exc

    def type(self, index: int) -> str:
        if not 0 <= index < self.type_size:
            raise TransformError("DEX type index out of bounds")
        return self.string(struct.unpack_from("<I", self.data, self.type_off + index * 4)[0])

    def prototype(self, index: int) -> str:
        if not 0 <= index < self.proto_size:
            raise TransformError("DEX prototype index out of bounds")
        _, result, parameters = struct.unpack_from("<III", self.data, self.proto_off + index * 12)
        arguments = []
        if parameters:
            if parameters + 4 > len(self.data):
                raise TransformError("DEX type list out of bounds")
            count = struct.unpack_from("<I", self.data, parameters)[0]
            if parameters + 4 + count * 2 > len(self.data):
                raise TransformError("DEX type list out of bounds")
            arguments = [self.type(struct.unpack_from("<H", self.data, parameters + 4 + i * 2)[0])
                         for i in range(count)]
        return "(" + "".join(arguments) + ")" + self.type(result)

    def method_identity(self, index: int) -> tuple[str, str, str]:
        if not 0 <= index < self.method_size:
            raise TransformError("DEX method index out of bounds")
        owner, proto, name = struct.unpack_from("<HHI", self.data, self.method_off + index * 8)
        return self.type(owner), self.string(name), self.prototype(proto)

    def code_offsets(self, identity: tuple[str, str, str]) -> list[int]:
        target_ids = {i for i in range(self.method_size) if self.method_identity(i) == identity}
        offsets = []
        for index in range(self.class_size):
            row = struct.unpack_from("<IIIIIIII", self.data, self.class_off + index * 32)
            class_data = row[6]
            if not class_data:
                continue
            cursor = class_data
            static_fields, cursor = _uleb(self.data, cursor)
            instance_fields, cursor = _uleb(self.data, cursor)
            direct_methods, cursor = _uleb(self.data, cursor)
            virtual_methods, cursor = _uleb(self.data, cursor)
            for _ in range(static_fields + instance_fields):
                _, cursor = _uleb(self.data, cursor); _, cursor = _uleb(self.data, cursor)
            method_index = 0
            for _ in range(direct_methods + virtual_methods):
                delta, cursor = _uleb(self.data, cursor); method_index += delta
                _, cursor = _uleb(self.data, cursor)
                code_offset, cursor = _uleb(self.data, cursor)
                if method_index in target_ids:
                    offsets.append(code_offset)
        return offsets


def load_contract(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransformError(f"cannot read contract: {exc}") from exc
    keys = {"schema_version", "transformation_id", "stock_apk_sha256", "entry",
            "entry_input_sha256", "entry_output_sha256", "method", "replacement"}
    keys.add("output_apk_sha256")
    if not isinstance(raw, dict) or set(raw) != keys or raw["schema_version"] != 1 or raw["transformation_id"] != TRANSFORMATION_ID:
        raise TransformError("malformed or unsupported contract")
    method_keys = {"class", "name", "prototype", "occurrences", "registers", "ins", "outs",
                   "tries", "debug_info_offset", "code_units", "code_input_sha256", "code_output_sha256"}
    if raw["entry"] != "classes.dex" or raw["replacement"] != "return-false-and-zero-fill" or not isinstance(raw["method"], dict) or set(raw["method"]) != method_keys:
        raise TransformError("contract identity drift")
    for key, value in EXPECTED.items():
        actual = raw["method"].get(key) if key in {"class", "name", "prototype"} else raw.get(key)
        if actual != value:
            raise TransformError("contract pin drift")
    if raw["method"]["occurrences"] != 1:
        raise TransformError("method occurrence contract drift")
    return raw


def patch_dex(data: bytes, contract: dict) -> bytes:
    if sha256(data) != contract["entry_input_sha256"]:
        if sha256(data) == contract["entry_output_sha256"]:
            raise TransformError("UnifiedWFC DEX is already transformed")
        raise TransformError("UnifiedWFC DEX input hash drift")
    method = contract["method"]
    offsets = Dex(data).code_offsets((method["class"], method["name"], method["prototype"]))
    if len(offsets) != method["occurrences"]:
        raise TransformError("target method occurrence drift")
    offset = offsets[0]
    if not offset or offset + 16 > len(data):
        raise TransformError("target method has no valid code item")
    registers, ins, outs, tries, debug, count = struct.unpack_from("<HHHHII", data, offset)
    if (registers, ins, outs, tries, debug, count) != tuple(method[k] for k in (
            "registers", "ins", "outs", "tries", "debug_info_offset", "code_units")):
        raise TransformError("target method code-item anchor drift")
    end = offset + 16 + count * 2
    if end > len(data):
        raise TransformError("target method instructions are out of bounds")
    before = data[offset + 16:end]
    if sha256(before) != method["code_input_sha256"]:
        raise TransformError("target method instruction hash drift")
    replacement = struct.pack("<HH", 0x0012, 0x000f) + b"\0" * (len(before) - 4)
    if sha256(replacement) != method["code_output_sha256"]:
        raise TransformError("replacement instruction contract drift")
    output = bytearray(data)
    output[offset + 16:end] = replacement
    output[12:32] = hashlib.sha1(output[32:]).digest()
    struct.pack_into("<I", output, 8, zlib.adler32(output[12:]) & 0xffffffff)
    if sha256(output) != contract["entry_output_sha256"]:
        raise TransformError("UnifiedWFC DEX output hash drift")
    return bytes(output)


def _apk_module():
    path = ROOT / "tools" / "apk_entry_replace.py"
    spec = importlib.util.spec_from_file_location("apk_entry_replace", path)
    module = importlib.util.module_from_spec(spec); assert spec.loader
    spec.loader.exec_module(module)
    return module


def transform(contract_path: Path, stock_apk: Path, output_apk: Path, report_path: Path) -> dict:
    contract = load_contract(contract_path)
    try:
        mode = stock_apk.lstat().st_mode
    except FileNotFoundError as exc:
        raise TransformError("missing stock APK") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise TransformError("stock APK must be a regular non-symlink file")
    apk = _apk_module()
    if apk.sha256_file(stock_apk) != contract["stock_apk_sha256"]:
        raise TransformError("stock APK hash drift")
    _, entries, _ = apk.load_base(stock_apk)
    if set(entries).intersection({"classes2.dex", "classes3.dex"}):
        raise TransformError("unexpected multidex stock APK")
    if contract["entry"] not in entries:
        raise TransformError("classes.dex is missing")
    patched = patch_dex(entries[contract["entry"]], contract)
    if output_apk.exists() or report_path.exists():
        raise TransformError("refusing to overwrite output or report")
    if not output_apk.parent.is_dir() or not report_path.parent.is_dir() or output_apk.parent.is_symlink() or report_path.parent.is_symlink():
        raise TransformError("output parents must be existing non-symlink directories")
    fd, temp_name = tempfile.mkstemp(prefix=".unifiedwfc-dex.", suffix=".dex", dir=output_apk.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(patched); stream.flush(); os.fsync(stream.fileno())
        zip_report = apk.build_archive(stock_apk, output_apk, {"classes.dex": temp}, {})
        if zip_report["output_sha256"] != contract["output_apk_sha256"]:
            output_apk.unlink(missing_ok=True)
            raise TransformError("UnifiedWFC APK output hash drift")
        changed = {item["entry"] for item in zip_report["changed_entries"]}
        allowed = {"classes.dex"} | apk.SIGNATURE_ENTRIES
        if changed - allowed or "classes.dex" not in changed:
            output_apk.unlink(missing_ok=True)
            raise TransformError("unexpected APK entry changes")
        payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID,
                   "status": "PASS", "stock_apk_sha256": contract["stock_apk_sha256"],
                   "output_apk_sha256": zip_report["output_sha256"],
                   "entry": "classes.dex", "entry_input_sha256": contract["entry_input_sha256"],
                   "entry_output_sha256": contract["entry_output_sha256"],
                   "removed_signature_entries": zip_report["removed_signatures"]}
        apk.atomic_json(report_path, payload)
        return payload
    except BaseException:
        if not report_path.exists():
            output_apk.unlink(missing_ok=True)
        raise
    finally:
        temp.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--stock-apk", required=True, type=Path)
    parser.add_argument("--output-apk", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = transform(args.contract, args.stock_apk, args.output_apk, args.report)
    except (OSError, TransformError, getattr(_apk_module(), "SafetyError")) as exc:
        print(f"error: {exc}", file=sys.stderr); return 1
    print(json.dumps(result, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
