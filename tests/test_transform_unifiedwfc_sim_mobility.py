import hashlib
import importlib.util
import json
import struct
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_unifiedwfc_sim_mobility.py"
CONTRACT = ROOT / "devices" / "m11q" / "unifiedwfc-sim-mobility-contract.json"


def load():
    spec = importlib.util.spec_from_file_location("transform_unifiedwfc_sim_mobility", TOOL)
    module = importlib.util.module_from_spec(spec); assert spec.loader
    spec.loader.exec_module(module); return module


MODULE = load()


class UnifiedWfcTests(unittest.TestCase):
    def test_replacement_is_return_false_plus_zero_fill(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        method = contract["method"]
        replacement = struct.pack("<HH", 0x0012, 0x000f) + b"\0" * (method["code_units"] * 2 - 4)
        self.assertEqual(hashlib.sha256(replacement).hexdigest(), method["code_output_sha256"])
        self.assertEqual(struct.unpack_from("<H", replacement, 0)[0], 0x0012)
        self.assertEqual(struct.unpack_from("<H", replacement, 2)[0], 0x000f)

    def test_contract_is_pinned_and_privacy_safe(self):
        contract = MODULE.load_contract(CONTRACT)
        self.assertEqual(contract["method"]["occurrences"], 1)
        text = CONTRACT.read_text(encoding="utf-8")
        for forbidden in ("/home/", "D:\\", ".smali", "invoke-", "const-string"):
            self.assertNotIn(forbidden, text)

    def test_uleb_rejects_truncated_and_oversized_values(self):
        with self.assertRaisesRegex(MODULE.TransformError, "truncated"):
            MODULE._uleb(b"\x80", 0)
        with self.assertRaisesRegex(MODULE.TransformError, "oversized"):
            MODULE._uleb(b"\x80" * 5, 0)

    def test_patch_is_hash_shape_and_occurrence_pinned(self):
        offset, count = 48, 6
        original_code = b"\x34\x12" * count
        data = bytearray(96)
        data[:8] = b"dex\n035\0"
        struct.pack_into("<I", data, 32, 96)
        struct.pack_into("<HHHHII", data, offset, 5, 2, 4, 0, 0, count)
        data[offset + 16:offset + 16 + len(original_code)] = original_code
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        method = contract["method"]
        method.update({"code_units": count,
                       "code_input_sha256": hashlib.sha256(original_code).hexdigest()})
        replacement = struct.pack("<HH", 0x0012, 0x000f) + b"\0" * (len(original_code) - 4)
        method["code_output_sha256"] = hashlib.sha256(replacement).hexdigest()
        contract["entry_input_sha256"] = hashlib.sha256(data).hexdigest()
        expected = bytearray(data)
        expected[offset + 16:offset + 16 + len(original_code)] = replacement
        expected[12:32] = hashlib.sha1(expected[32:]).digest()
        import zlib
        struct.pack_into("<I", expected, 8, zlib.adler32(expected[12:]) & 0xffffffff)
        contract["entry_output_sha256"] = hashlib.sha256(expected).hexdigest()
        fake = mock.Mock()
        fake.code_offsets.return_value = [offset]
        with mock.patch.object(MODULE, "Dex", return_value=fake):
            self.assertEqual(MODULE.patch_dex(bytes(data), contract), bytes(expected))
            fake.code_offsets.return_value = []
            with self.assertRaisesRegex(MODULE.TransformError, "occurrence"):
                MODULE.patch_dex(bytes(data), contract)
            with self.assertRaisesRegex(MODULE.TransformError, "already transformed"):
                MODULE.patch_dex(bytes(expected), contract)


if __name__ == "__main__":
    unittest.main()
