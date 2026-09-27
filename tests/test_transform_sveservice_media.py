import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_sveservice_media.py"
CANONICAL = ROOT / "devices" / "m11q" / "sveservice-media-contract.json"


def load():
    spec = importlib.util.spec_from_file_location("transform_sveservice_media", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load()
JNI_FIXTURE = f""".class public {MODULE.JNI_OWNER}
.super {MODULE.JNI_SUPER}
.method {MODULE.CLINIT}
    .locals 1
{MODULE.LOAD_SVEJNI}
    return-void
.end method
.method public untouched()V
    .locals 0
    return-void
.end method
"""
IMPL_FIXTURE = f""".class public {MODULE.IMPL_OWNER}
.super {MODULE.IMPL_SUPER}
.method {MODULE.CREATE}
    .locals 12
    .line 277
{MODULE.CREATE_NATIVE}
    return v0
.end method
.method {MODULE.START}
    .locals 1
    .line 284
{MODULE.START_NATIVE}
    return v0
.end method
.method public untouched()V
    .locals 0
    return-void
.end method
"""


class SveTransformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "private" / "smali"
        fixtures = {MODULE.JNI_PATH: JNI_FIXTURE, MODULE.IMPL_PATH: IMPL_FIXTURE}
        for relative, text in fixtures.items():
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="")

        raw = json.loads(CANONICAL.read_text(encoding="utf-8"))
        expected = {}
        for item in raw["targets"]:
            text = fixtures[item["path"]]
            before = MODULE._methods(text)
            updated = (MODULE._update_jni(text, before) if item["path"] == MODULE.JNI_PATH
                       else MODULE._update_impl(text, before))
            item["input_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            item["output_sha256"] = hashlib.sha256(updated.encode()).hexdigest()
            after = MODULE._methods(updated)
            for method in item["methods"]:
                method["input_sha256"] = hashlib.sha256(
                    before[method["signature"]].encode()).hexdigest()
                method["output_sha256"] = hashlib.sha256(
                    after[method["signature"]].encode()).hexdigest()
            expected[item["path"]] = {key: value for key, value in item.items()
                                      if key != "path"}
        self.contract = self.base / "contract.json"
        self.contract.write_text(json.dumps(raw), encoding="utf-8")
        self.expected_patch = mock.patch.object(MODULE, "EXPECTED_TARGETS", expected)
        self.expected_patch.start()
        self.overlay = self.base / "overlay"
        self.report = self.base / "report.json"

    def tearDown(self):
        self.expected_patch.stop()
        self.temp.cleanup()

    def run_transform(self, allow_identical=False):
        return MODULE.transform(self.contract, self.source, self.overlay,
                                self.report, allow_identical)

    def test_applies_loader_before_svejni_and_only_expected_methods(self):
        self.run_transform()
        jni = (self.overlay / MODULE.JNI_PATH).read_text(encoding="utf-8")
        self.assertLess(jni.index("m11q_sve_compat"), jni.index('const-string v0, "svejni"'))
        self.assertEqual(MODULE._methods(jni)["public untouched()V"],
                         MODULE._methods(JNI_FIXTURE)["public untouched()V"])

        impl = (self.overlay / MODULE.IMPL_PATH).read_text(encoding="utf-8")
        methods = MODULE._methods(impl)
        self.assertEqual(methods[MODULE.CREATE].count("M11qSveDiag"), 2)
        self.assertEqual(methods[MODULE.START].count("M11qSveDiag"), 2)
        self.assertIn("    .locals 4\n", methods[MODULE.START])
        self.assertEqual(methods["public untouched()V"],
                         MODULE._methods(IMPL_FIXTURE)["public untouched()V"])

    def test_hash_drift_partial_apply_and_repeated_apply_fail_closed(self):
        target = self.source / MODULE.JNI_PATH
        target.write_text(JNI_FIXTURE + "\n", encoding="utf-8", newline="")
        with self.assertRaisesRegex(MODULE.TransformError, "input hash drift"):
            self.run_transform()
        target.write_text(JNI_FIXTURE, encoding="utf-8", newline="")
        self.run_transform()
        patched = (self.overlay / MODULE.JNI_PATH).read_text(encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "already or partially"):
            MODULE._update_jni(patched, MODULE._methods(patched))
        partial = IMPL_FIXTURE.replace("    .line 277\n", MODULE.CREATE_ENTER + "    .line 277\n")
        with self.assertRaisesRegex(MODULE.TransformError, "already or partially"):
            MODULE._update_impl(partial, MODULE._methods(partial))

    def test_nonoverwrite_identical_and_contract_metadata_are_safe(self):
        self.run_transform()
        with self.assertRaisesRegex(MODULE.TransformError, "overwrite"):
            self.run_transform()
        self.assertFalse(self.run_transform(True)["changed"])
        contract = CANONICAL.read_text(encoding="utf-8").lower()
        for forbidden in (".line ", "invoke-", "const-string", "/home/", "d:\\"):
            self.assertNotIn(forbidden, contract)

    def test_contract_rejects_target_or_artifact_drift(self):
        raw = json.loads(self.contract.read_text(encoding="utf-8"))
        drifted = copy.deepcopy(raw)
        drifted["artifact"]["stock_apk_size"] += 1
        self.contract.write_text(json.dumps(drifted), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "artifact contract drift"):
            MODULE.load_contract(self.contract)


if __name__ == "__main__":
    unittest.main()
