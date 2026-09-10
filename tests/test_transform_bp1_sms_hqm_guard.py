import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_bp1_sms_hqm_guard.py"
CANONICAL = ROOT / "devices" / "m11q" / "bp1-sms-hqm-telemetry-guard-contract.json"


def load():
    spec = importlib.util.spec_from_file_location("transform_bp1_sms_hqm_guard", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load()
FIXTURE = f""".class public {MODULE.OWNER}
.super Ljava/lang/Object;
.field private static final LOG_TAG:Ljava/lang/String;
.method {MODULE.METHOD}
    .locals 19
    {MODULE.LOOKUP}

    move-result-object v7

    .line 335
    if-eqz v7, :cond_6
    :cond_6
    return-void
.end method
.method public untouched()V
    .locals 0
    return-void
.end method
"""


class Bp1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "private" / "smali"
        self.target = self.source / MODULE.TARGET_PATH
        self.target.parent.mkdir(parents=True)
        self.target.write_text(FIXTURE, encoding="utf-8", newline="")
        raw = json.loads(CANONICAL.read_text(encoding="utf-8"))
        digest = hashlib.sha256(self.target.read_bytes()).hexdigest()
        raw["targets"][0]["input_sha256"] = digest
        self.hash_patch = mock.patch.object(MODULE, "EXPECTED_INPUT_SHA256", digest)
        self.hash_patch.start()
        self.contract = self.base / "contract.json"
        self.contract.write_text(json.dumps(raw), encoding="utf-8")
        self.overlay = self.base / "overlay"
        self.report = self.base / "report.json"

    def tearDown(self):
        self.hash_patch.stop()
        self.temp.cleanup()

    def run_transform(self, allow_identical=False):
        return MODULE.transform(self.contract, self.source, self.overlay,
                                self.report, allow_identical)

    def test_guard_is_narrow_and_preserves_other_methods(self):
        self.run_transform()
        updated = (self.overlay / MODULE.TARGET_PATH).read_text(encoding="utf-8")
        body = MODULE._methods(updated, MODULE.METHOD)[0]
        self.assertIn("Ljava/lang/RuntimeException;", body)
        self.assertNotIn(".catch Ljava/lang/Throwable;", body)
        self.assertIn(MODULE.MARKER, body)
        self.assertIn("const/4 v7, 0x0", body)
        self.assertEqual(MODULE._methods(updated, "public untouched()V")[0],
                         MODULE._methods(FIXTURE, "public untouched()V")[0])

    def test_hash_anchor_and_already_applied_fail_closed(self):
        self.target.write_text(FIXTURE + "\n", encoding="utf-8", newline="")
        with self.assertRaisesRegex(MODULE.TransformError, "input hash drift"):
            self.run_transform()
        self.target.write_text(FIXTURE, encoding="utf-8", newline="")
        self.run_transform()
        patched = (self.overlay / MODULE.TARGET_PATH).read_text(encoding="utf-8")
        self.target.write_text(patched, encoding="utf-8", newline="")
        other_overlay, other_report = self.base / "other", self.base / "other.json"
        with self.assertRaisesRegex(MODULE.TransformError, "already or partially"):
            MODULE._identity(patched, json.loads(self.contract.read_text())["targets"][0])

    def test_nonoverwrite_identical_and_contract_are_safe(self):
        self.run_transform()
        with self.assertRaisesRegex(MODULE.TransformError, "overwrite"):
            self.run_transform()
        self.assertFalse(self.run_transform(True)["changed"])
        text = CANONICAL.read_text(encoding="utf-8")
        for forbidden in (".line ", "invoke-", "const-string", "/home/"):
            self.assertNotIn(forbidden, text.lower())


if __name__ == "__main__":
    unittest.main()
