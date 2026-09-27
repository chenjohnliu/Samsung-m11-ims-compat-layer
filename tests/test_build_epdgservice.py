import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "build_epdgservice.py"


def load():
    spec = importlib.util.spec_from_file_location("build_epdgservice", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


M = load()


class EpdgBuilderTests(unittest.TestCase):
    def test_public_builder_has_strict_final_pins(self):
        for digest in (M.APKTOOL_SHA256, M.JAVA_SHA256, M.FINAL_DEX_SHA256, M.FINAL_APK_SHA256):
            self.assertEqual(len(digest), 64)
            int(digest, 16)
        source = TOOL.read_text(encoding="utf-8").lower()
        for forbidden in ("private_backup", "stock_analysis", "stage3_repro_closure", "/home/", "d:\\"):
            self.assertNotIn(forbidden, source)

    def test_smali_inventory_is_stable_and_rejects_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(M.BuildError, "empty"):
                M._smali_inventory(root)
            target = root / "a" / "Example.smali"
            target.parent.mkdir()
            target.write_text(".class public LExample;\n", encoding="utf-8")
            found = M._smali_inventory(root)
            self.assertEqual(set(found), {"a/Example.smali"})
            self.assertEqual(found["a/Example.smali"], M.sha256_file(target))


if __name__ == "__main__":
    unittest.main()
