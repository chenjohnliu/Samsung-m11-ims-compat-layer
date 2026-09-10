import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_bh1_sms_icc_type.py"
CANONICAL = ROOT / "devices" / "m11q" / "bh1-sms-icc-type-contract.json"


def load():
    spec = importlib.util.spec_from_file_location("transform_bh1_sms_icc_type", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load()
SOURCE = f""".class public final {MODULE.OWNER}
.super Ljava/lang/Object;
.method private canFallback(I)Z
    .locals 1
    {MODULE.LEGACY}
    move-result v4
    const/4 v0, 0x0
    return v0
.end method
.method private canFallbackForTimeout()Z
    .locals 1
    {MODULE.LEGACY}
    move-result v4
    const/4 v0, 0x0
    return v0
.end method
.method public untouched()V
    .locals 0
    return-void
.end method
"""


class Bh1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "smali"
        self.target = self.source / MODULE.TARGET_PATH
        self.target.parent.mkdir(parents=True)
        self.target.write_text(SOURCE, encoding="utf-8", newline="")
        raw = json.loads(CANONICAL.read_text(encoding="utf-8"))
        digest = hashlib.sha256(self.target.read_bytes()).hexdigest()
        raw["targets"][0]["input_sha256"] = digest
        self.patch = mock.patch.object(MODULE, "EXPECTED_INPUT_SHA256", digest)
        self.patch.start()
        self.contract = self.base / "contract.json"
        self.contract.write_text(json.dumps(raw), encoding="utf-8")
        self.overlay = self.base / "overlay"
        self.report = self.base / "report.json"

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def run_transform(self, identical=False):
        return MODULE.transform(self.contract, self.source, self.overlay,
                                self.report, identical)

    def test_exact_two_calls_and_stock_semantics(self):
        self.run_transform()
        text = (self.overlay / MODULE.TARGET_PATH).read_text(encoding="utf-8")
        self.assertNotIn(MODULE.LEGACY, text)
        self.assertEqual(text.count(MODULE.COMPAT), 2)
        self.assertIn("ril.ICC_TYPE0", text)
        self.assertIn("ril.ICC_TYPE1", text)
        self.assertIn("Landroid/os/SystemProperties;->get", text)
        self.assertIn("Ljava/lang/Integer;->parseInt", text)
        self.assertIn(".method public untouched()V", text)

    def test_hash_identity_partial_and_nonoverwrite_fail_closed(self):
        self.target.write_text(SOURCE + "\n", encoding="utf-8", newline="")
        with self.assertRaisesRegex(MODULE.TransformError, "input hash drift"):
            self.run_transform()
        self.target.write_text(SOURCE, encoding="utf-8", newline="")
        self.run_transform()
        with self.assertRaisesRegex(MODULE.TransformError, "overwrite"):
            self.run_transform()
        self.assertFalse(self.run_transform(True)["changed"])

    def test_contract_contains_no_stock_implementation(self):
        text = CANONICAL.read_text(encoding="utf-8")
        for forbidden in ("invoke-", "const-string", "/home/"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
