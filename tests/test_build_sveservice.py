import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "build_sveservice.py"
CONFIG = ROOT / "devices" / "m11q" / "sveservice-build.json"


def load():
    spec = importlib.util.spec_from_file_location("build_sveservice", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load()


class SveBuilderTests(unittest.TestCase):
    def test_public_config_is_strict_and_contains_no_private_paths(self):
        config = MODULE.load_config(CONFIG)
        self.assertEqual(config["output"]["classes_dex_sha256"],
                         "f1294ce50783bbec6ad84fbd377a9436f70954a2bcd9a4b7e258b3a4552df4f4")
        self.assertEqual(config["output"]["changed_entries"],
                         sorted(MODULE.SIGNATURES | {"classes.dex"}))
        text = CONFIG.read_text(encoding="utf-8").lower()
        for forbidden in ("/home/", "d:\\", "private_backup", "stage3_repro_closure"):
            self.assertNotIn(forbidden, text)

    def test_source_verified_uses_actual_dex_header_not_historical_size(self):
        def dex(size):
            data = bytearray(size)
            data[:8] = b"dex\n039\x00"
            data[32:36] = size.to_bytes(4, "little")
            data[36:40] = (0x70).to_bytes(4, "little")
            data[40:44] = (0x12345678).to_bytes(4, "little")
            return data
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "classes.dex"
            path.write_bytes(dex(0x80))
            self.assertEqual(MODULE.verify_dex_header(path), 0x80)
            expected = {"classes_dex_size": 0x70, "classes_dex_sha256": "a" * 64,
                        "unsigned_apk_sha256": "b" * 64}
            MODULE.verify_serialized_output(path, "c" * 64, "d" * 64, expected, True)
            with self.assertRaisesRegex(MODULE.BuildError, "size drift"):
                MODULE.verify_serialized_output(path, "c" * 64, "d" * 64, expected, False)
            path.write_bytes(b"dex\n039\x00" + b"\0" * 20)
            with self.assertRaisesRegex(MODULE.BuildError, "invalid or truncated"):
                MODULE.verify_dex_header(path)

    def test_source_verified_skips_only_serialized_hash_pins(self):
        data = bytearray(0x70)
        data[:8] = b"dex\n039\x00"
        data[32:36] = (0x70).to_bytes(4, "little")
        data[36:40] = (0x70).to_bytes(4, "little")
        data[40:44] = (0x12345678).to_bytes(4, "little")
        expected = {"classes_dex_size": 0x70, "classes_dex_sha256": "a" * 64,
                    "unsigned_apk_sha256": "b" * 64}
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "classes.dex"
            path.write_bytes(data)
            with self.assertRaisesRegex(MODULE.BuildError, "pin mismatch"):
                MODULE.verify_serialized_output(path, "c" * 64, "d" * 64, expected, False)
            MODULE.verify_serialized_output(path, "c" * 64, "d" * 64, expected, True)
            wrong_size = {**expected, "classes_dex_size": 0x80}
            with self.assertRaisesRegex(MODULE.BuildError, "size drift"):
                MODULE.verify_serialized_output(path, "c" * 64, "d" * 64, wrong_size, False)

    def test_source_roundtrip_checks_every_class_and_instructions(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            before, after = root / "before", root / "after"
            before.mkdir(); after.mkdir()
            text = ".class public LExample;\n.super Ljava/lang/Object;\n.method public m()V\n return-void\n.end method\n"
            (before / "Example.smali").write_text(text, encoding="utf-8")
            (after / "Example.smali").write_text(text, encoding="utf-8")
            self.assertEqual(MODULE.verify_source_roundtrip(before, after), 1)
            (after / "Example.smali").write_text(text.replace("return-void", "nop\n return-void"), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.BuildError, "round-trip drift"):
                MODULE.verify_source_roundtrip(before, after)

    def test_stock_verifier_rejects_unpinned_apk(self):
        config = MODULE.load_config(CONFIG)
        with tempfile.TemporaryDirectory() as name:
            candidate = Path(name) / "stock.apk"
            with zipfile.ZipFile(candidate, "w") as archive:
                archive.writestr("classes.dex", b"not-stock")
            with self.assertRaisesRegex(MODULE.BuildError, "stock APK identity mismatch"):
                MODULE.verify_stock(candidate, config)

    def test_config_rejects_output_or_toolchain_drift(self):
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "config.json"
            raw["toolchain"]["apktool"]["version"] = "different"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.BuildError, "apktool determinism"):
                MODULE.load_config(path)

    def test_output_and_report_collision_is_rejected_before_tool_execution(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            same = base / "collision.apk"
            with self.assertRaisesRegex(MODULE.BuildError, "different paths"):
                MODULE.build(CONFIG, same, same, "java", same, same)


if __name__ == "__main__":
    unittest.main()
