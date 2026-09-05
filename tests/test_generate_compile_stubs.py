import copy
import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path


TOOL = Path(__file__).parents[1] / "tools" / "generate_compile_stubs.py"
SPEC = importlib.util.spec_from_file_location("generate_compile_stubs", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


CLASS = "Lvendor/example/Backend;"
BASE_METHODS = [
    {"name": "answer", "descriptor": "(I)Z", "access": ["public"], "throws": []},
    {"name": "checked", "descriptor": "()V", "access": ["public"],
     "throws": ["Ljava/io/IOException;"]},
]
HOOK = {"name": "projectHook", "descriptor": "()Ljava/lang/Object;",
        "access": ["public", "static"], "throws": [],
        "provenance": "project-added test hook", "verify_in_smali": True}


def contract():
    return {
        "schema_version": 1,
        "purpose": "test",
        "roots": ["stock"],
        "classes": [{
            "descriptor": CLASS,
            "root": "stock",
            "access": ["public"],
            "super": "Ljava/lang/Object;",
            "java_super": None,
            "java_kind": "class",
            "stock_methods": copy.deepcopy(BASE_METHODS),
            "project_hooks": [copy.deepcopy(HOOK)],
        }],
    }


def smali(extra="", answer=".method public answer(I)Z", checked_access="public",
          superclass="Ljava/lang/Object;"):
    return f""".class public {CLASS}
.super {superclass}

.field private secret:Ljava/lang/String;

{answer}
    .locals 1
    const-string v0, \"PROPRIETARY_INSTRUCTION_SENTINEL\"
    return v0
.end method

.method {checked_access} checked()V
    .annotation system Ldalvik/annotation/Throws;
        value = {{
            Ljava/io/IOException;
        }}
    .end annotation
    .param p0, \"SECRET_PARAMETER_NAME\"
    .line 123
    return-void
.end method

.method public static projectHook()Ljava/lang/Object;
    const-string v0, \"HOOK_IMPLEMENTATION_SENTINEL\"
    return-object v0
.end method
{extra}"""


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "decoded"
        self.source = self.root / "vendor" / "example" / "Backend.smali"
        self.source.parent.mkdir(parents=True)
        self.source.write_text(smali(), encoding="utf-8")
        self.contract_path = self.base / "contract.json"
        self.contract_path.write_text(json.dumps(contract()), encoding="utf-8")
        self.output = self.base / "generated"
        self.report = self.base / "report.json"

    def tearDown(self):
        self.temp.cleanup()

    def run_generate(self, allow_identical=False):
        return MODULE.generate(self.contract_path, {"stock": self.root}, self.output,
                               self.report, allow_identical)

    def test_pass_and_never_leaks_implementation_metadata(self):
        result = self.run_generate()
        java = (self.output / "vendor/example/Backend.java").read_text(encoding="utf-8")
        self.assertEqual(result["method_provenance_counts"],
                         {"stock-extracted": 2, "project-added-hook": 1})
        self.assertIn("ABI source: stock-extracted", java)
        self.assertIn("ABI source: project-added-hook", java)
        self.assertIn("throws java.io.IOException", java)
        for forbidden in ("PROPRIETARY_INSTRUCTION_SENTINEL", ".field", ".line",
                          "SECRET_PARAMETER_NAME", "HOOK_IMPLEMENTATION_SENTINEL"):
            self.assertNotIn(forbidden, java)
        self.assertFalse(result["safety"]["candidate_dex_eligible"])

    def test_missing_method_fails_closed(self):
        self.source.write_text(smali(answer=".method public other(I)Z"), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "exactly one answer"):
            self.run_generate()

    def test_duplicate_method_fails_closed(self):
        duplicate = "\n.method public answer(I)Z\n    return p0\n.end method\n"
        self.source.write_text(smali(extra=duplicate), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "exactly one answer"):
            self.run_generate()

    def test_descriptor_drift_fails_closed(self):
        self.source.write_text(smali(answer=".method public answer(J)Z"), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "exactly one answer"):
            self.run_generate()

    def test_access_drift_fails_closed(self):
        self.source.write_text(smali(checked_access="private"), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "access drift"):
            self.run_generate()

    def test_checked_exception_drift_fails_closed(self):
        text = smali().replace("Ldalvik/annotation/Throws;", "Ldalvik/annotation/Other;")
        self.source.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "throws drift"):
            self.run_generate()

    def test_project_hook_must_be_present_in_patched_smali(self):
        start = smali().index(".method public static projectHook")
        text = smali()[:start]
        self.source.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "projectHook"):
            self.run_generate()

    def test_observed_superclass_is_verified_but_not_implicitly_inherited(self):
        value = contract()
        value["classes"][0]["super"] = "Lvendor/example/PrivateBinderStub;"
        self.contract_path.write_text(json.dumps(value), encoding="utf-8")
        self.source.write_text(
            smali(superclass="Lvendor/example/PrivateBinderStub;"), encoding="utf-8")
        self.run_generate()
        java = (self.output / "vendor/example/Backend.java").read_text(encoding="utf-8")
        self.assertNotIn("PrivateBinderStub", java)

    def test_unsafe_contract_descriptor_is_rejected(self):
        value = contract()
        value["classes"][0]["descriptor"] = "L../../escape;"
        self.contract_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "unsafe class descriptor"):
            self.run_generate()

    def test_unsafe_method_type_descriptor_is_rejected(self):
        value = contract()
        value["classes"][0]["stock_methods"][0]["descriptor"] = "()L../../escape;"
        self.contract_path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "unsafe class descriptor"):
            self.run_generate()

    def test_symlink_escape_is_rejected_when_supported(self):
        outside = self.base / "outside.smali"
        outside.write_text(smali(), encoding="utf-8")
        self.source.unlink()
        try:
            self.source.symlink_to(outside)
        except OSError:
            self.skipTest("symlink creation unavailable")
        with self.assertRaisesRegex(MODULE.ContractError, "unsafe or missing smali path"):
            self.run_generate()

    def test_existing_output_refused_by_default(self):
        self.run_generate()
        with self.assertRaisesRegex(MODULE.ContractError, "refusing to overwrite"):
            self.run_generate()

    def test_identical_output_is_idempotent_only_when_opted_in(self):
        first = self.run_generate()
        second = self.run_generate(allow_identical=True)
        self.assertEqual(first, second)

    def test_conflicting_output_is_never_replaced(self):
        self.run_generate()
        target = self.output / "vendor/example/Backend.java"
        target.write_text("conflict", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "conflicts"):
            self.run_generate(allow_identical=True)
        self.assertEqual(target.read_text(encoding="utf-8"), "conflict")

    def test_wrong_or_duplicate_root_names_are_rejected(self):
        with self.assertRaisesRegex(MODULE.ContractError, "root names"):
            MODULE.generate(self.contract_path, {"other": self.root}, self.output, self.report)
        with self.assertRaisesRegex(SystemExit, "2"):
            MODULE.main([
                "--contract", str(self.contract_path), "--smali-root", f"stock={self.root}",
                "--smali-root", f"stock={self.root}", "--output", str(self.output),
                "--report", str(self.report)])

    def test_repository_contract_covers_six_classes_and_separates_hooks(self):
        public_contract = MODULE.load_contract(
            Path(__file__).parents[1] / "devices/m11q/compile-stub-contract.json")
        self.assertEqual(len(public_contract["classes"]), 6)
        hooks = [(cls["descriptor"], method["name"])
                 for cls in public_contract["classes"]
                 for group, method in cls["methods"] if group == "project_hooks"]
        self.assertEqual(hooks, [
            ("Lcom/sec/internal/google/GoogleImsService;", "getInstanceIfReady"),
            ("Lcom/sec/internal/google/GoogleImsService;", "getModernIncomingIdentity"),
        ])
        java_supers = {cls["descriptor"]: cls["java_super"]
                       for cls in public_contract["classes"]}
        self.assertIsNone(java_supers["Lcom/sec/internal/google/GoogleImsService;"])
        self.assertEqual(
            java_supers["Lcom/sec/internal/google/ImsCallSessionImpl;"],
            "Lcom/android/ims/internal/IImsCallSession$Stub;")

    def test_existing_report_cannot_cause_partial_output(self):
        self.report.write_text("conflict", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContractError, "existing report"):
            self.run_generate(allow_identical=True)
        self.assertFalse(self.output.exists())

    def test_report_write_failure_rolls_back_new_output(self):
        with mock.patch.object(MODULE, "_write_file_atomic",
                               side_effect=OSError("synthetic report failure")):
            with self.assertRaisesRegex(OSError, "synthetic report failure"):
                self.run_generate()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())


if __name__ == "__main__":
    unittest.main()
