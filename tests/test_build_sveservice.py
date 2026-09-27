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
