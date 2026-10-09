import os
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import legacy_service_state_compat as T


def uleb(value):
    result = bytearray()
    while value >= 0x80:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def synthetic_dex(*, omit=(), static_ok=True, abstract=(), duplicate_class=False, method_flags=None):
    """Build a small standard DEX with actual ServiceState class-data definitions."""
    required = list(T.REQUIRED)
    owner = T.OWNER
    signatures = required
    descriptors = {owner, "Ljava/lang/Object;", "Landroid/telephony/NetworkRegistrationInfo;",
                   "I", "V", "Z"}
    method_specs = []
    defined_specs = []
    for signature in signatures:
        name, proto = signature.split("(", 1)
        proto = "(" + proto
        args, ret = proto[1:].split(")", 1)
        arg_types = []
        while args:
            if args.startswith("L"):
                end = args.index(";") + 1
            else:
                end = 1
            arg_types.append(args[:end])
            args = args[end:]
        descriptors.update(arg_types)
        descriptors.add(ret)
        spec = (name, "(" + "".join(arg_types) + ")" + ret,
                signature in abstract)
        method_specs.append(spec)
        if signature not in omit:
            defined_specs.append(spec)

    types = sorted(descriptors)
    strings = sorted(set(types) | {name for name, _, _ in method_specs} | {"V", "I", "Z"})
    string_index = {value: i for i, value in enumerate(strings)}
    type_index = {value: i for i, value in enumerate(types)}
    protos = sorted({proto for _, proto, _ in method_specs})
    proto_index = {value: i for i, value in enumerate(protos)}

    # Header and fixed-width tables.
    string_ids_off = 112
    type_ids_off = string_ids_off + 4 * len(strings)
    proto_ids_off = type_ids_off + 4 * len(types)
    method_specs.sort(key=lambda item: (type_index[owner], string_index[item[0]], proto_index[item[1]]))
    method_ids_off = proto_ids_off + 12 * len(protos)
    class_defs_off = method_ids_off + 8 * len(method_specs)
    cursor = class_defs_off + (64 if duplicate_class else 32)

    # String data first; all strings here are ASCII, a valid MUTF-8 subset.
    string_data = bytearray()
    string_offsets = []
    for value in strings:
        string_offsets.append(cursor + len(string_data))
        raw = value.encode("ascii")
        string_data.extend(uleb(len(value)) + raw + b"\0")
    cursor += len(string_data)

    # Type lists for non-empty argument lists.
    type_list_offsets = {}
    type_lists = bytearray()
    for proto in protos:
        args = proto[1:proto.index(")")]
        arg_types = []
        while args:
            end = args.index(";") + 1 if args.startswith("L") else 1
            arg_types.append(args[:end])
            args = args[end:]
        if arg_types:
            while (cursor + len(type_lists)) % 4:
                type_lists.append(0)
            type_list_offsets[proto] = cursor + len(type_lists)
            type_lists.extend(struct.pack("<I", len(arg_types)))
            type_lists.extend(b"".join(struct.pack("<H", type_index[t]) for t in arg_types))
            if len(arg_types) & 1:
                type_lists.extend(b"\0\0")
        else:
            type_list_offsets[proto] = 0
    cursor += len(type_lists)

    # Every concrete definition points to a small, aligned code_item.
    code_data = bytearray()
    code_offsets = {}
    for name, proto, _ in method_specs:
        if name + proto in abstract:
            code_offsets[name + proto] = 0
            continue
        while (cursor + len(code_data)) % 4:
            code_data.append(0)
        code_offsets[name + proto] = cursor + len(code_data)
        # registers, ins, outs, tries, debug_info_off, insns_size, one nop.
        code_data.extend(struct.pack("<HHHHIIH", 1, 0, 0, 0, 0, 1, 0))
    cursor += len(code_data)

    # Class data groups are delta-indexed direct (static) then virtual methods.
    class_data_off = cursor
    indexed = [(method_specs.index(spec), spec) for spec in defined_specs]
    direct, virtual = [], []
    for index, spec in indexed:
        name, proto, _ = spec
        is_static = bool(T.REQUIRED.get(name + proto)) and static_ok
        (direct if is_static else virtual).append((index, spec))
    direct.sort(key=lambda item: item[0])
    virtual.sort(key=lambda item: item[0])
    class_data = bytearray(uleb(0) + uleb(0) + uleb(len(direct)) + uleb(len(virtual)))
    for group in (direct, virtual):
        previous = 0
        for index, (name, proto, is_abstract) in group:
            class_data.extend(uleb(index - previous))
            previous = index
            flags = 0x1
            if T.REQUIRED.get(name + proto) and static_ok:
                flags |= 0x8
            if is_abstract:
                flags |= 0x100
            if method_flags and name + proto in method_flags:
                flags = method_flags[name + proto]
            class_data.extend(uleb(flags))
            class_data.extend(uleb(code_offsets[name + proto]))

    # Class data begins immediately after the aligned code items.
    data_blob = bytes(string_data + type_lists + code_data + class_data)
    file_size = cursor + len(class_data)
    header = bytearray(112)
    header[:8] = b"dex\n039\0"
    struct.pack_into("<I", header, 32, file_size)
    struct.pack_into("<I", header, 36, 112)
    struct.pack_into("<I", header, 40, 0x12345678)
    struct.pack_into("<II", header, 56, len(strings), string_ids_off)
    struct.pack_into("<II", header, 64, len(types), type_ids_off)
    struct.pack_into("<II", header, 72, len(protos), proto_ids_off)
    struct.pack_into("<II", header, 88, len(method_specs), method_ids_off)
    class_count = 2 if duplicate_class else 1
    struct.pack_into("<II", header, 96, class_count, class_defs_off)
    string_ids = b"".join(struct.pack("<I", off) for off in string_offsets)
    type_ids = b"".join(struct.pack("<I", string_index[value]) for value in types)
    proto_ids = bytearray()
    for proto in protos:
        args = proto[1:proto.index(")")]
        # The parser only consumes return type and parameter-list offset.
        proto_ids.extend(struct.pack("<III", string_index["V"],
                                     type_index[proto[proto.index(")") + 1:]],
                                     type_list_offsets[proto]))
    method_ids = b"".join(struct.pack("<HHI", type_index[owner], proto_index[proto],
                                         string_index[name])
                           for name, proto, _ in method_specs)
    class_def = struct.pack("<8I", type_index[owner], 0x1,
                            type_index["Ljava/lang/Object;"], 0, 0xffffffff,
                            0, class_data_off, 0)
    if duplicate_class:
        class_def += class_def
    return (bytes(header) + string_ids + type_ids + bytes(proto_ids) + method_ids +
            class_def + data_blob)


class LegacyServiceStateCompatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.android = self.root / "android"
        self.state = self.root / "state"
        source = self.android / T.SOURCE
        source.parent.mkdir(parents=True)
        self.original = b"class ServiceState {\n" + T.ANCHOR + b"    // end\n}\n"
        source.write_bytes(self.original)
        self.state.mkdir()
        self.hash_patch = mock.patch.object(T, "ORIGINAL_SHA256", T.LEG1.sha(self.original))
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_source_apply_verify_and_rollback_are_exact_and_idempotent(self):
        applied = T.source_action(self.android, self.state, "apply")
        path = self.android / T.SOURCE
        backup = self.state / "backup-ServiceState.java"
        expected = self.original.replace(T.ANCHOR, T.SHIM + T.ANCHOR, 1)
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertTrue(applied["configuration_changed"])
        self.assertFalse(T.source_action(self.android, self.state, "apply")["configuration_changed"])
        self.assertEqual(T.source_action(self.android, self.state, "verify-source")["status"], "PASS")
        self.assertEqual(T.source_action(self.android, self.state, "rollback")["source_state"], "original")
        self.assertEqual(path.read_bytes(), self.original)
        self.assertFalse(T.source_action(self.android, self.state, "rollback")["configuration_changed"])

    def test_source_unknown_hash_or_anchor_refuses_without_backup_or_overwrite(self):
        path = self.android / T.SOURCE
        path.write_bytes(self.original + b"user change")
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            T.source_action(self.android, self.state, "apply")
        self.assertFalse((self.state / "backup-ServiceState.java").exists())
        self.assertEqual(path.read_bytes(), self.original + b"user change")

    def test_source_unrelated_edit_and_backup_drift_refuse_without_overwrite(self):
        T.source_action(self.android, self.state, "apply")
        path = self.android / T.SOURCE
        path.write_bytes(path.read_bytes() + b"user change")
        changed = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "unrelated ServiceState edit"):
            T.source_action(self.android, self.state, "rollback")
        self.assertEqual(path.read_bytes(), changed)
        path.write_bytes(self.original)
        backup = self.state / "backup-ServiceState.java"
        backup.write_bytes(self.original + b"drift")
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            T.source_action(self.android, self.state, "apply")
        self.assertEqual(path.read_bytes(), self.original)

    def test_source_symlink_is_rejected_without_touching_target(self):
        path = self.android / T.SOURCE
        target = self.root / "target.java"
        target.write_bytes(self.original)
        path.unlink()
        try:
            path.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "symlink refused"):
            T.source_action(self.android, self.state, "apply")
        self.assertEqual(target.read_bytes(), self.original)
        self.assertFalse((self.state / "backup-ServiceState.java").exists())

    def make_jar(self, dexes):
        path = self.root / "framework.jar"
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in dexes:
                archive.writestr(name, data)
        return path

    def test_synthetic_dex_requires_defined_public_concrete_methods_with_correct_staticness(self):
        report = T.verify_framework(self.make_jar([("classes.dex", synthetic_dex())]))
        self.assertTrue(report["service_state_legacy_abi_verified"])
        for omitted in ("getMobileDataRoaming()Z", "getMobileDataRegState()I",
                        "getRilMobileDataRadioTechnology()I", "getVoiceRoamingType()I",
                        "getDataRoamingType()I", "isPsOnlyReg()Z",
                        "getNetworkRegistrationInfo(II)Landroid/telephony/NetworkRegistrationInfo;",
                        "rilRadioTechnologyToNetworkType(I)I"):
            with self.subTest(omitted=omitted), self.assertRaisesRegex(ValueError, "missing/invalid"):
                T.verify_framework(self.make_jar([("classes.dex", synthetic_dex(omit=(omitted,)))]))
        with self.assertRaisesRegex(ValueError, "missing/invalid"):
            T.verify_framework(self.make_jar([("classes.dex", synthetic_dex(static_ok=False))]))
        with self.assertRaisesRegex(ValueError, "missing/invalid"):
            T.verify_framework(self.make_jar([("classes.dex", synthetic_dex(abstract=("getMobileDataRoaming()Z",)))]))

    def test_dex_references_only_duplicate_class_and_duplicate_zip_dex_rejected(self):
        required = "getMobileDataRoaming()Z"
        data = synthetic_dex(omit=(required,))
        # Keep method_ids present while omitting the class-data definition: references alone do not pass.
        with self.assertRaisesRegex(ValueError, "missing/invalid"):
            T.verify_framework(self.make_jar([("classes.dex", data)]))
        with self.assertRaisesRegex(ValueError, "missing/duplicate ServiceState"):
            T.verify_framework(self.make_jar([("classes.dex", synthetic_dex(duplicate_class=True))]))
        path = self.root / "framework.jar"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("classes.dex", synthetic_dex())
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr("classes.dex", synthetic_dex())
        with self.assertRaisesRegex(ValueError, "missing/duplicate framework DEX"):
            T.verify_framework(path)

    def test_nonpublic_abstract_native_and_conflicting_flags_cannot_pass(self):
        for flags in (0, 2, 4, 3, 5, 0x401, 0x101, 9):
            with self.subTest(flags=flags), self.assertRaisesRegex(ValueError, "missing/invalid"):
                T.verify_framework(self.make_jar([("classes.dex", synthetic_dex(
                    method_flags={"getMobileDataRoaming()Z": flags}))]))

    def test_dex_malformed_table_and_code_bounds_are_rejected(self):
        valid = synthetic_dex()
        malformed = bytearray(valid)
        struct.pack_into("<I", malformed, 32, len(valid) + 1)
        with self.assertRaisesRegex(ValueError, "invalid DEX header"):
            T.dex_definitions(bytes(malformed))
        malformed = bytearray(valid)
        struct.pack_into("<I", malformed, 100, len(valid) + 64)
        with self.assertRaisesRegex(ValueError, "DEX table bounds"):
            T.dex_definitions(bytes(malformed))
        definitions = T.dex_definitions(valid)[0]
        code_off = next(code for _, _, code in definitions.values() if code)
        malformed = bytearray(valid)
        struct.pack_into("<I", malformed, code_off + 12, len(valid))
        with self.assertRaisesRegex(ValueError, "DEX code-item bounds"):
            T.dex_definitions(bytes(malformed))
        with self.assertRaisesRegex(ValueError, "truncated"):
            T.dex_definitions(valid[:70])

    def test_optional_installed_framework_jar_checks_legacy_method(self):
        installed = os.environ.get("SS1_FRAMEWORK_JAR")
        if not installed:
            self.skipTest("set SS1_FRAMEWORK_JAR to an existing installed framework.jar")
        self.assertTrue(Path(installed).is_file(), "SS1_FRAMEWORK_JAR must point to an existing jar")
        # A future user rebuild must remain usable with the same test command.
        try:
            result = T.verify_framework(installed)
        except ValueError as exc:
            self.assertIn("missing/invalid: getMobileDataRoaming()Z", str(exc))
        else:
            self.assertTrue(result["service_state_legacy_abi_verified"])


if __name__ == "__main__":
    unittest.main()
