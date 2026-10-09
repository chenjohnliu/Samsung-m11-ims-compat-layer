#!/usr/bin/env python3
"""Guarded SS1 source fix and read-only packaged legacy ServiceState ABI gate."""

import argparse
import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path

import legacy_iwlan_trial as LEG1

SOURCE = "frameworks/base/telephony/java/android/telephony/ServiceState.java"
ORIGINAL_SHA256 = "aa4d543b8ac88939626d012948885eefd1a157535b28399b444f37047aa8e54e"
ANCHOR = b"    /**\n     * Returns whether the device is registered only for packet-switched service.\n"
SHIM = b"""    /**
     * Samsung compatibility: roaming of the underlying WWAN data network.
     * Android 13 getDataRoaming() already uses the PS/WWAN roaming type.
     *
     * @hide
     */
    public boolean getMobileDataRoaming() {
        return getDataRoaming();
    }

"""
OWNER = "Landroid/telephony/ServiceState;"
REQUIRED = {
    "getMobileDataRoaming()Z": False,
    "getMobileDataRegState()I": False,
    "getRilMobileDataRadioTechnology()I": False,
    "getVoiceRoamingType()I": False,
    "getDataRoamingType()I": False,
    "isPsOnlyReg()Z": False,
    "getNetworkRegistrationInfo(II)Landroid/telephony/NetworkRegistrationInfo;": False,
    "rilRadioTechnologyToNetworkType(I)I": True,
}


def candidate(original):
    if LEG1.sha(original) != ORIGINAL_SHA256 or original.count(ANCHOR) != 1:
        raise ValueError("unrecognized ServiceState source; nothing changed")
    if b"getMobileDataRoaming(" in original:
        raise ValueError("existing roaming shim refused")
    return original.replace(ANCHOR, SHIM + ANCHOR, 1)


def source_action(android_root, state_dir, action):
    root, state = LEG1.source_root(android_root), LEG1.safe(state_dir)
    path = LEG1.regular(root / SOURCE)
    backup = state / "backup-ServiceState.java"
    observed = path.read_bytes()
    if not backup.exists():
        if action != "apply":
            raise ValueError("SS1 backup not prepared")
        candidate(observed)  # Validate all inputs before publishing a backup.
        if not state.is_dir():
            raise ValueError("existing LEG1 state directory required")
        with backup.open("xb") as stream:
            stream.write(observed)
    original = LEG1.regular(backup).read_bytes()
    patched = candidate(original)
    if observed not in (original, patched):
        raise ValueError("unrelated ServiceState edit refused")
    destination = original if action == "rollback" else patched
    if action == "verify-source" and observed != patched:
        raise ValueError("SS1 shim missing; do not build")
    changed = action != "verify-source" and observed != destination
    if changed:
        LEG1.atomic_replace(path, observed, destination)
    if path.read_bytes() != destination:
        raise ValueError("ServiceState verification failed")
    return {"status": "PASS", "compatibility": "SS1-mobile-data-roaming",
            "configuration_changed": changed, "source_sha256": LEG1.sha(destination),
            "source_state": "original" if action == "rollback" else "SS1",
            "rom_build_run": False, "runtime_validated": False}


def dex_definitions(data, owner_descriptor=OWNER):
    """Read defined methods, not method references/string hits, from standard DEX."""
    if (len(data) < 112 or data[:8] not in
            [f"dex\n{v}\0".encode() for v in ("035", "037", "038", "039", "040")]):
        raise ValueError("unsupported or truncated framework DEX")

    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise ValueError("DEX bounds failure")
        return struct.unpack_from(fmt, data, offset)

    def u32(offset):
        return unpack("<I", offset)[0]

    if u32(32) != len(data) or u32(36) != 112 or u32(40) != 0x12345678:
        raise ValueError("invalid DEX header")

    def table(offset, width):
        count, start = unpack("<II", offset)
        if count and (start < 112 or start + count * width > len(data)):
            raise ValueError("DEX table bounds failure")
        return count, start

    def uleb(offset):
        value = 0
        for index in range(5):
            byte = unpack("<B", offset)[0]
            offset += 1
            if index == 4 and byte > 15:
                raise ValueError("invalid DEX ULEB128")
            value |= (byte & 127) << (7 * index)
            if not byte & 128:
                return value, offset
        raise ValueError("unterminated DEX ULEB128")

    count, start = table(56, 4)
    strings = []
    for index in range(count):
        _, cursor = uleb(u32(start + 4 * index))
        end = data.find(b"\0", cursor)
        if end < 0:
            raise ValueError("unterminated DEX string")
        # Selected descriptors/method names are ASCII; irrelevant MUTF-8 strings
        # may contain surrogate encodings. Never use them for signature matching.
        strings.append(data[cursor:end].decode("utf-8", errors="replace"))
    count, start = table(64, 4)
    types = [strings[u32(start + 4 * i)] for i in range(count)]
    count, start = table(72, 12)
    protos = []
    for index in range(count):
        _, returned, parameters = unpack("<III", start + 12 * index)
        arguments = []
        if parameters:
            size = u32(parameters)
            if parameters + 4 + size * 2 > len(data):
                raise ValueError("DEX parameter bounds failure")
            arguments = [types[unpack("<H", parameters + 4 + 2 * i)[0]] for i in range(size)]
        protos.append("(" + "".join(arguments) + ")" + types[returned])
    count, start = table(88, 8)
    methods = []
    for index in range(count):
        owner, proto, name = unpack("<HHI", start + 8 * index)
        methods.append((types[owner], strings[name] + protos[proto]))
    count, start = table(96, 32)
    found = []
    for index in range(count):
        fields = unpack("<8I", start + 32 * index)
        if types[fields[0]] != owner_descriptor:
            continue
        if not fields[1] & 1 or fields[1] & 0x206:
            raise ValueError("ServiceState class is not a public concrete class")
        cursor = fields[6]
        if not cursor:
            found.append({})
            continue
        sizes = []
        for _ in range(4):
            size, cursor = uleb(cursor)
            sizes.append(size)
        if sum(sizes) > len(data):
            raise ValueError("DEX class-data count failure")
        for _ in range(sizes[0] + sizes[1]):
            _, cursor = uleb(cursor)
            _, cursor = uleb(cursor)
        defined = {}
        for group, size in enumerate(sizes[2:]):
            method_index = 0
            for _ in range(size):
                diff, cursor = uleb(cursor)
                method_index += diff
                flags, cursor = uleb(cursor)
                code, cursor = uleb(cursor)
                owner, signature = methods[method_index]
                if owner != owner_descriptor or signature in defined:
                    raise ValueError("invalid/duplicate ServiceState method definition")
                if code:
                    insns = u32(code + 12)
                    if code % 4 or code + 16 + insns * 2 > len(data):
                        raise ValueError("DEX code-item bounds failure")
                defined[signature] = (flags, group, code)
        found.append(defined)
    return found


def verify_framework(path):
    path = LEG1.regular(path)
    definitions = []
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if re.fullmatch(r"classes(?:[2-9]|[1-9][0-9]+)?\.dex", n)]
        if not names or len(names) != len(set(names)):
            raise ValueError("missing/duplicate framework DEX entries")
        for name in names:
            for methods in dex_definitions(archive.read(name)):
                definitions.append((name, methods))
    if len(definitions) != 1:
        raise ValueError("missing/duplicate ServiceState class definition")
    name, methods = definitions[0]
    for signature, static in REQUIRED.items():
        flags, group, code = methods.get(signature, (0, -1, 0))
        if (not flags & 1 or bool(flags & 8) != static or flags & 0x506
                or group != (0 if static else 1) or not code):
            raise ValueError(f"packaged legacy framework ABI missing/invalid: {signature}; do not flash")
    return {"status": "PASS", "service_state_legacy_abi_verified": True,
            "framework_sha256": LEG1.sha(path.read_bytes()), "service_state_dex": name,
            "required_methods": sorted(REQUIRED), "runtime_validated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("apply", "rollback", "verify-source", "verify-framework"))
    parser.add_argument("--android-root", type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--framework-jar", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "verify-framework":
            if args.framework_jar is None:
                raise ValueError("--framework-jar required")
            output = verify_framework(args.framework_jar)
        else:
            if args.android_root is None or args.state_dir is None:
                raise ValueError("--android-root and --state-dir required")
            output = source_action(args.android_root, args.state_dir, args.action)
        print(json.dumps(output, sort_keys=True))
    except (OSError, ValueError, IndexError, KeyError, struct.error, zipfile.BadZipFile) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
