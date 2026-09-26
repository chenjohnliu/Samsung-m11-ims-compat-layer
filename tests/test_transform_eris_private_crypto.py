import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_eris_private_crypto.py"
CANONICAL = ROOT / "devices" / "m11q" / "eris-private-crypto-contract.json"


def load():
    spec = importlib.util.spec_from_file_location("transform_eris_private_crypto", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load()


def elf(soname, needed, slack=8):
    strings = b"\0"
    offsets = {}
    for value in [*needed, soname]:
        offsets[value] = len(strings)
        strings += value.encode() + b"\0" + (b"\0" * slack)
    phoff, load_off, dynamic_off, strtab_off = 52, 0, 0x100, 0x200
    size = strtab_off + len(strings)
    data = bytearray(size)
    data[:6] = b"\x7fELF\x01\x01"
    struct.pack_into("<H", data, 16, 3)
    struct.pack_into("<H", data, 18, 40)
    struct.pack_into("<I", data, 28, phoff)
    struct.pack_into("<HH", data, 42, 32, 2)
    struct.pack_into("<IIIIIIII", data, phoff, 1, load_off, 0, 0, size, size, 5, 0x1000)
    dynamic_size = (len(needed) + 4) * 8
    struct.pack_into("<IIIIIIII", data, phoff + 32, 2, dynamic_off, dynamic_off,
                     dynamic_off, dynamic_size, dynamic_size, 4, 4)
    rows = [(5, strtab_off), (10, len(strings)), (14, offsets[soname])]
    rows += [(1, offsets[item]) for item in needed]
    rows += [(0, 0)]
    for index, row in enumerate(rows):
        struct.pack_into("<II", data, dynamic_off + index * 8, *row)
    data[strtab_off:] = strings
    return bytes(data)


class ErisPrivateCryptoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.inputs = self.base / "inputs"
        self.inputs.mkdir()
        self.outputs = self.base / "outputs"
        self.report = self.base / "report.json"
        definitions = [
            ("libcrypto.so", "libcrypto.so", ["libc.so", "libm.so", "libdl.so"],
             "liberc.so", ["libc.so", "libm.so", "libdl.so"], [("libcrypto.so", "liberc.so")]),
            ("libssl.so", "libssl.so", ["libcrypto.so", "libc.so", "libm.so", "libdl.so"],
             "libers.so", ["liberc.so", "libc.so", "libm.so", "libdl.so"],
             [("libcrypto.so", "liberc.so"), ("libssl.so", "libers.so")]),
            ("liberis_strongswan.so", "liberis_strongswan.so",
             ["libz.so", "libssl.so", "libcrypto.so", "libdl.so", "libc++.so", "libc.so", "libm.so"],
             "liberis_strongswan.so",
             ["libz.so", "libers.so", "liberc.so", "libdl.so", "libc++.so", "libc.so", "libm.so"],
             [("libcrypto.so", "liberc.so"), ("libssl.so", "libers.so")]),
        ]
        contract = json.loads(CANONICAL.read_text(encoding="utf-8"))
        expected = {}
        for item, definition in zip(contract["targets"], definitions):
            name, soname, needed, out_soname, out_needed, replacements = definition
            source = elf(soname, needed)
            item["input_sha256"] = hashlib.sha256(source).hexdigest()
            item["soname_before"], item["needed_before"] = soname, needed
            item["soname_after"], item["needed_after"] = out_soname, out_needed
            item["replacements"] = [{"old": old, "new": new, "occurrences": 1}
                                    for old, new in replacements]
            provisional = dict(item)
            provisional["output_sha256"] = "0" * 64
            output = source
            identity = MODULE.elf_identity(output)
            start, end = identity["strtab"]
            table = output[start:end]
            for old, new in replacements:
                old_b, new_b = old.encode() + b"\0", new.encode() + b"\0"
                table = table.replace(old_b, new_b.ljust(len(old_b), b"\0"), 1)
            output = output[:start] + table + output[end:]
            item["output_sha256"] = hashlib.sha256(output).hexdigest()
            (self.inputs / name).write_bytes(source)
            expected[name] = (item["input_sha256"], item["output_name"], item["output_sha256"])
        self.contract = self.base / "contract.json"
        self.contract.write_text(json.dumps(contract), encoding="utf-8")
        self.patch = mock.patch.object(MODULE, "EXPECTED_TARGETS", expected)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_transforms_only_dynamic_names_and_reports_hashes(self):
        result = MODULE.transform(self.contract, self.inputs, self.outputs, self.report)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual({p.name for p in self.outputs.iterdir()},
                         {"liberc.so", "libers.so", "liberis_strongswan.so"})
        contract = json.loads(self.contract.read_text())
        for item in contract["targets"]:
            data = (self.outputs / item["output_name"]).read_bytes()
            identity = MODULE.elf_identity(data)
            self.assertEqual(identity["soname"], item["soname_after"])
            self.assertEqual(identity["needed"], item["needed_after"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["output_sha256"])
        report = self.report.read_text(encoding="utf-8")
        self.assertNotIn(str(self.base), report)

    def test_hash_drift_repeat_and_overwrite_fail_closed(self):
        target = self.inputs / "libcrypto.so"
        target.write_bytes(target.read_bytes() + b"x")
        with self.assertRaisesRegex(MODULE.TransformError, "input hash drift"):
            MODULE.transform(self.contract, self.inputs, self.outputs, self.report)
        target.write_bytes(elf("libcrypto.so", ["libc.so", "libm.so", "libdl.so"]))
        MODULE.transform(self.contract, self.inputs, self.outputs, self.report)
        with self.assertRaisesRegex(MODULE.TransformError, "overwrite"):
            MODULE.transform(self.contract, self.inputs, self.outputs, self.report)
        contract = json.loads(self.contract.read_text())
        with self.assertRaisesRegex(MODULE.TransformError, "already transformed"):
            MODULE.transform_one(contract["targets"][0], (self.outputs / "liberc.so").read_bytes())

    def test_contract_contains_metadata_not_payload(self):
        text = CANONICAL.read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("D:\\", text)
        self.assertLess(len(text), 8000)


if __name__ == "__main__":
    unittest.main()
