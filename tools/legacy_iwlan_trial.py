#!/usr/bin/env python3
"""Prepare/stage/restore LEG1 boot-time IWLAN configuration. Never builds a ROM."""

import argparse
import hashlib
import json
import os
import stat
import struct
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

TRIAL = "LEG1-modem-led-iwlan"
MODE = "ro.telephony.iwlan_operation_mode"
LABEL = "ro.m11q.ims_trial"
KEY = "m11q_active_call_w2l_handover_bool"
PROP = "device/samsung/m11q/system.prop"
VENDOR = "device/samsung/m11q/overlay/packages/apps/CarrierConfig/res/xml/vendor.xml"
ORIGINAL = {
    PROP: "44f31736088d6b080fbad9d2b8f798ab07b50bb5af6ab6f26138b6e4d06167c3",
    VENDOR: "8b21b2d5511586e938da2ca03d0c7e2004384f519edabac6a44519151dfda4dd",
}
PREREQUISITES = {
    "frameworks/base/telephony/java/android/telephony/ServiceState.java":
        "3248f8549360a5101f5535d18c5bfd5a7b3f189a65099356c67d1e6695e27f88",
    "frameworks/opt/telephony/src/java/com/android/internal/telephony/data/AccessNetworksManager.java":
        "4c1818e45d2368521dd3021653de299f42f6c741c5d8b8320811410b59428350",
    "frameworks/opt/telephony/src/java/com/android/internal/telephony/data/DataNetworkController.java":
        "6b8bf4490598d642be784beb55551c0af5f71c47c213134b2a5504918ae6895b",
    "device/samsung/m11q/ims/proprietary/priv-app/EpdgService/EpdgService.apk":
        "5c9f372867afcee56da55f10851b4c30bd95452bea0720fca68e6e73ac96de27",
    "device/samsung/m11q/ims/proprietary/priv-app/imsservice/imsservice.apk":
        "251f95cb892e38b8ba8025c3033332c55d8ac4bec1d0d53b8d18c8d33a870d0b",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"symlink refused: {part}")
    return path


def regular(path):
    path = safe(path)
    if not path.is_file():
        raise ValueError(f"expected regular file: {path}")
    return path


def source_root(path):
    path = safe(path)
    if not path.is_dir():
        raise ValueError("Android root must exist")
    return path


def prerequisites(root):
    for relative, expected in PREREQUISITES.items():
        if sha(regular(root / relative).read_bytes()) != expected:
            raise ValueError(f"source prerequisite drift: {relative}")


def candidates(original):
    prop = original[PROP]
    if MODE.encode() in prop or LABEL.encode() in prop:
        raise ValueError("pre-existing IWLAN mode/trial property")
    old = f'<boolean name="{KEY}" value="true"/>'.encode()
    vendor = original[VENDOR]
    if vendor.count(old) != 1:
        raise ValueError("expected one AP-assisted experiment switch")
    candidate = {
        PROP: prop.rstrip(b"\n") + b"\n\n# LEG1 trial: modem-led IWLAN; requires a full reboot.\n"
              + f"{MODE}=legacy\n{LABEL}=legacy-r1\n".encode(),
        VENDOR: vendor.replace(old, old.replace(b'"true"', b'"false"'), 1),
    }
    comment = (b"<!-- Experimental: preserve an established ordinary IMS voice call on\n"
               b"             W2L. Idle transitions retain the fresh-bearer policy below. -->")
    if candidate[VENDOR].count(comment) != 1:
        raise ValueError("unrecognized experiment comment")
    candidate[VENDOR] = candidate[VENDOR].replace(
        comment, b"<!-- LEG1: EC2/BV1 AP-assisted experiments disabled; modem-led\n"
                 b"             IWLAN is selected at boot in system.prop. -->", 1)
    validate_vendor(ET.fromstring(candidate[VENDOR]))
    return candidate


def validate_vendor(tree):
    if tree.tag != "carrier_config_list":
        raise ValueError("unexpected CarrierConfig XML root")
    configs = tree.findall("carrier_config")
    def carrier_matches(config, mnc):
        # aapt can compile unquoted numeric XML attributes into typed integers,
        # so 01/05 read back as 1/5. Only accept the known two spellings; do not
        # broadly coerce arbitrary or three-digit MNC strings.
        spellings = {mnc, mnc[1:]} if mnc in ("01", "05") else {mnc}
        return config.get("mcc") == "466" and config.get("mnc") in spellings

    matches = [c for c in configs if carrier_matches(c, "97")]
    if len(matches) != 1:
        raise ValueError("missing/duplicate TWM configuration")
    flags = [e for e in matches[0].findall("boolean") if e.get("name") == KEY]
    if len(flags) != 1 or flags[0].get("value") != "false":
        raise ValueError("AP-assisted experiment must be explicitly disabled")
    # Keep the existing Taiwan availability scope, not a new global carrier rollout.
    for mnc in ("01", "05", "92", "97"):
        carriers = [c for c in configs if carrier_matches(c, mnc)]
        if len(carriers) != 1 or not any(
                e.get("name") == "carrier_wfc_ims_available_bool" and e.get("value") == "true"
                for e in carriers[0].findall("boolean")):
            raise ValueError(f"Taiwan WFC availability drift: 466{mnc}")


def bundle(state):
    state = safe(state)
    original = {r: regular(state / ("backup-" + Path(r).name)).read_bytes() for r in ORIGINAL}
    for relative, data in original.items():
        if sha(data) != ORIGINAL[relative]:
            raise ValueError(f"backup drift: {relative}")
    candidate = candidates(original)
    for relative, data in candidate.items():
        if regular(state / ("candidate-" + Path(relative).name)).read_bytes() != data:
            raise ValueError(f"candidate drift: {relative}")
    return original, candidate


def prepare(root, state):
    root, state = source_root(root), safe(state)
    prerequisites(root)
    if state.exists():
        bundle(state)
        return verify_source(root, state, expected="either")
    if not state.parent.is_dir():
        raise ValueError("state parent must exist")
    original = {r: regular(root / r).read_bytes() for r in ORIGINAL}
    if any(sha(original[r]) != h for r, h in ORIGINAL.items()):
        raise ValueError("unrecognized original configuration; nothing changed")
    candidate = candidates(original)
    state.mkdir(mode=0o700)
    for label, entries in (("backup", original), ("candidate", candidate)):
        for relative, data in entries.items():
            with (state / (label + "-" + Path(relative).name)).open("xb") as stream:
                stream.write(data)
    bundle(state)
    return verify_source(root, state, expected="original")


def result(**extra):
    return {"status": "PASS", "trial": TRIAL, "rom_build_run": False,
            "runtime_validated": False, **extra}


def verify_source(root, state, expected="candidate"):
    root = source_root(root)
    prerequisites(root)
    original, candidate = bundle(state)
    observed = {r: regular(root / r).read_bytes() for r in ORIGINAL}
    allowed = {"candidate": [candidate], "original": [original],
               "either": [original, candidate]}[expected]
    if not any(observed == choice for choice in allowed):
        raise ValueError("configuration drift or mixed state; do not build")
    return result(source_state="legacy-r1" if observed == candidate else "original-ap-assisted",
                  source_hashes={r: sha(b) for r, b in observed.items()})


def atomic_replace(path, expected, data):
    path = regular(path)
    if path.read_bytes() != expected:
        raise ValueError(f"concurrent edit refused: {path}")
    descriptor, name = tempfile.mkstemp(prefix=".leg1-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        if path.read_bytes() != expected:
            raise ValueError(f"concurrent edit refused: {path}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def change(root, state, rollback=False):
    root = source_root(root)
    prerequisites(root)
    original, candidate = bundle(state)
    destination = original if rollback else candidate
    observed = {r: regular(root / r).read_bytes() for r in ORIGINAL}
    for relative, data in observed.items():
        if data not in (original[relative], candidate[relative]):
            raise ValueError(f"unrelated edit refused: {relative}")
    changed = []
    try:
        for relative in ORIGINAL:
            if observed[relative] != destination[relative]:
                atomic_replace(root / relative, observed[relative], destination[relative])
                changed.append(relative)
        verified = verify_source(root, state, "original" if rollback else "candidate")
    except Exception:
        # A crash can leave a mixed configuration; rerunning apply/rollback
        # safely completes known states. On ordinary errors restore this run
        # only, and never overwrite a concurrent/unrecognized user edit.
        for relative in reversed(changed):
            if regular(root / relative).read_bytes() == destination[relative]:
                atomic_replace(root / relative, destination[relative], observed[relative])
        raise
    return {**verified, "configuration_changed": bool(changed), "rollback": rollback}


def binary_xml(data):
    """Minimal bounded Android resource XML reader (no external executables)."""
    if data.lstrip().startswith(b"<"):
        return ET.fromstring(data)
    if len(data) < 8 or struct.unpack_from("<HHI", data) != (3, 8, len(data)):
        raise ValueError("invalid Android XML envelope")
    strings, stack, root, pos = None, [], None, 8
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated XML chunk")
        kind, header, size = struct.unpack_from("<HHI", data, pos)
        if header < 8 or size < header or pos + size > len(data):
            raise ValueError("invalid XML chunk bounds")
        chunk = data[pos:pos + size]
        if kind == 1:
            if strings is not None or header < 28:
                raise ValueError("invalid string pool")
            count, _, flags, start, _ = struct.unpack_from("<5I", chunk, 8)
            if header + count * 4 > size or start < header + count * 4:
                raise ValueError("invalid string offsets")
            strings = []
            def length(offset, width):
                fmt, high = ("<B", 0x80) if width == 1 else ("<H", 0x8000)
                first = struct.unpack_from(fmt, chunk, offset)[0]
                offset += width
                if first & high:
                    second = struct.unpack_from(fmt, chunk, offset)[0]
                    offset += width
                    first = ((first & (high - 1)) << (width * 8)) | second
                return first, offset
            for index in range(count):
                offset = start + struct.unpack_from("<I", chunk, header + index * 4)[0]
                if flags & 0x100:
                    _, offset = length(offset, 1)
                    size_string, offset = length(offset, 1)
                    encoding, terminator = "utf-8", b"\x00"
                else:
                    size_string, offset = length(offset, 2)
                    size_string *= 2
                    encoding, terminator = "utf-16-le", b"\x00\x00"
                end = offset + size_string
                if end + len(terminator) > size or chunk[end:end + len(terminator)] != terminator:
                    raise ValueError("invalid string boundary")
                strings.append(chunk[offset:end].decode(encoding))
        elif kind == 0x102:
            if strings is None or header != 16 or size < 36:
                raise ValueError("invalid start element")
            _, name, attr_start, attr_size, count = struct.unpack_from("<IIHHH", chunk, header)
            if attr_start < 20 or attr_size < 20 or header + attr_start + count * attr_size > size:
                raise ValueError("invalid attribute bounds")
            element = ET.Element(strings[name])
            for index in range(count):
                offset = header + attr_start + index * attr_size
                _, name, raw, value_size, _, value_type, value = struct.unpack_from("<IIIHBBI", chunk, offset)
                if value_size != 8:
                    raise ValueError("invalid typed value")
                if raw != 0xffffffff:
                    text = strings[raw]
                elif value_type == 3:
                    text = strings[value]
                elif value_type == 0x12:
                    text = "true" if value else "false"
                else:
                    text = str(value)
                element.set(strings[name], text)
            if stack:
                stack[-1].append(element)
            elif root is not None:
                raise ValueError("multiple XML roots")
            else:
                root = element
            stack.append(element)
        elif kind == 0x103:
            if not stack or header != 16 or size < 24 or strings[struct.unpack_from("<I", chunk, 20)[0]] != stack[-1].tag:
                raise ValueError("mismatched end element")
            stack.pop()
        elif kind == 0x104:
            # CarrierConfig string values are CDATA nodes in compiled XML.
            # Preserve them rather than validating attributes alone.
            if strings is None or not stack or header != 16 or size < 28:
                raise ValueError("invalid XML text node")
            data_index, value_size, _, value_type, value = struct.unpack_from(
                "<IHBBI", chunk, header)
            # AAPT2 writes the raw string index and leaves typedData zeroed.
            # Older encoders can also populate the standard eight-byte value.
            if value_size not in (0, 8):
                raise ValueError("invalid XML text value")
            index = data_index if data_index != 0xffffffff else value
            if data_index == 0xffffffff and (value_size != 8 or value_type != 3):
                raise ValueError("unsupported XML text type")
            if index >= len(strings):
                raise ValueError("invalid XML text string index")
            parent = stack[-1]
            if len(parent):
                parent[-1].tail = (parent[-1].tail or "") + strings[index]
            else:
                parent.text = (parent.text or "") + strings[index]
        elif kind not in (0x100, 0x101, 0x180):
            raise ValueError("unknown resource XML chunk")
        pos += size
    if root is None or stack:
        raise ValueError("incomplete XML tree")
    return root


def verify_product(product):
    root = source_root(product)
    definitions = {MODE: [], LABEL: []}
    # Inspect installed-partition outputs only, not stale intermediates/obj.
    paths = [root / "system/build.prop"]
    paths += [root / r for r in ("vendor/build.prop", "product/etc/build.prop",
                                "system/system_ext/etc/build.prop", "odm/etc/build.prop")]
    for path in paths:
        if path.exists():
            for line in regular(path).read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key.strip() in definitions:
                        definitions[key.strip()].append(value.strip())
    if definitions != {MODE: ["legacy"], LABEL: ["legacy-r1"]}:
        raise ValueError(f"packaged boot properties mismatch: {definitions}; do not flash")
    overlay = regular(root / "vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk")
    with zipfile.ZipFile(overlay) as archive:
        if archive.namelist().count("res/xml/vendor.xml") != 1:
            raise ValueError("missing/duplicate packaged vendor.xml")
        xml = archive.read("res/xml/vendor.xml")
        if xml.lstrip().startswith(b"<"):
            raise ValueError("packaged vendor.xml must be compiled Android XML")
        validate_vendor(binary_xml(xml))
    import verify_ims_w2l_trial_artifacts as combined
    import build_imsservice_w2l_trial as bv1
    apks = root / "system/system_ext/priv-app"
    prefix_pins = Path(__file__).resolve().parents[1] / "devices/m11q/legacy-epdg-prefix-build.json"
    combined.verify(apks / "EpdgService/EpdgService.apk", apks / "imsservice/imsservice.apk",
                    bv1.DEFAULT_PINS, epdg_prefix_pins=prefix_pins)
    import legacy_service_state_compat as ss1
    framework = ss1.verify_framework(root / "system/framework/framework.jar")
    return result(packaged_boot_mode="legacy", packaged_ap_assisted_trial=False,
                  apk_dex_identity_verified=True, legacy_epdg_prefix_verified=True,
                  signature_verified=False,
                  service_state_legacy_abi_verified=framework["service_state_legacy_abi_verified"],
                  framework_sha256=framework["framework_sha256"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "apply", "verify-source", "rollback", "verify-product"))
    parser.add_argument("--android-root", type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--product-root", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "verify-product":
            if args.product_root is None:
                raise ValueError("--product-root required")
            output = verify_product(args.product_root)
            # New releases must contain the full profile-derived global matrix,
            # not merely the historical four Taiwan entries. Historical direct
            # verify_product() callers retain their original baseline checks.
            import global_wfc_profile_policy as global_wfc
            if global_wfc.DEFAULT_CONTRACT.exists():
                output.update(global_wfc.verify_product(args.product_root))
        else:
            if args.android_root is None or args.state_dir is None:
                raise ValueError("--android-root and --state-dir required")
            if args.action == "prepare":
                output = prepare(args.android_root, args.state_dir)
            elif args.action == "verify-source":
                output = verify_source(args.android_root, args.state_dir)
            else:
                output = change(args.android_root, args.state_dir, args.action == "rollback")
        print(json.dumps(output, sort_keys=True))
    except (OSError, ValueError, RuntimeError, KeyError, IndexError, struct.error, ET.ParseError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
