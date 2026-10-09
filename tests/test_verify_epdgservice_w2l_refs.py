import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ec2_refs_tests", ROOT / "tools/verify_epdgservice_w2l_refs.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class ReferenceTests(unittest.TestCase):
    def test_inventory_accepts_package_private_anonymous_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Anonymous.smali"
            path.write_text(".class Lcom/sec/Anonymous;\n.super Ljava/lang/Object;\n", encoding="utf-8")
            self.assertEqual(M.inventory(Path(tmp))["Lcom/sec/Anonymous;"]["flags"], [])

    def test_inherited_member_resolution_is_exact(self):
        classes = {"LChild;": {"super": "LBase;", "members": {}},
                   "LBase;": {"super": None, "members": {"method(I)V": ["protected"]}}}
        self.assertEqual(M.resolve(classes, "LChild;", "method(I)V"), ("LBase;", ["protected"]))
        with self.assertRaises(ValueError):
            M.resolve(classes, "LChild;", "method()V")


if __name__ == "__main__":
    unittest.main()
