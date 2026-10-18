import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_imsservice as IMS
import source_verified_receipt as RECEIPT


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SourceVerifiedReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.apk = self.root / "stage.apk"
        self.write_apk(self.apk, {"classes.dex": b"primary", "classes2.dex": b"bridge"})
        self.classification = {"source_classification_verified": True,
                               "source": "fixture", "verified": True}

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write_apk(path, entries):
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in entries.items():
                archive.writestr(name, content)

    def report(self, path=None, **overrides):
        receipt = RECEIPT.make_source_verified_receipt(
            "imsservice-source-verified", self.apk,
            {"classes.dex": digest(b"primary"), "classes2.dex": digest(b"bridge")},
            self.classification)
        payload = {"status": "SOURCE_VERIFIED", "strict_pins_verified": False,
                   "source_invariants_verified": True, "runtime_validated": False,
                   "release_eligible": False, "source_verified_receipt": receipt}
        payload.update(overrides)
        path = path or self.root / "receipt.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path, payload

    def test_exact_input_and_source_stage_are_bound_to_receipt(self):
        report, payload = self.report()
        checked = RECEIPT.verify_source_verified_input(
            report, self.apk, "imsservice-source-verified", ["imsservice-source-verified"])
        self.assertEqual(checked["artifact"], payload["source_verified_receipt"]["artifact"])
        self.assertEqual(checked["report_sha256"], digest(report.read_bytes()))

    def test_wrong_stage_or_chain_is_rejected(self):
        report, _ = self.report()
        with self.assertRaisesRegex(RECEIPT.ReceiptError, "stage chain"):
            RECEIPT.verify_source_verified_input(
                report, self.apk, "bv1-source-verified", ["imsservice-source-verified", "bv1-source-verified"])
        with self.assertRaisesRegex(RECEIPT.ReceiptError, "stage chain"):
            RECEIPT.verify_source_verified_input(
                report, self.apk, "imsservice-source-verified", ["unexpected-root"])

    def test_edited_apk_and_dex_are_rejected(self):
        report, _ = self.report()
        changed = self.root / "changed.apk"
        self.write_apk(changed, {"classes.dex": b"edited", "classes2.dex": b"bridge"})
        with self.assertRaisesRegex(RECEIPT.ReceiptError, "APK does not match"):
            RECEIPT.verify_source_verified_input(
                report, changed, "imsservice-source-verified", ["imsservice-source-verified"])

    def test_verified_chain_extension_binds_previous_report(self):
        root_report, _ = self.report()
        upstream = RECEIPT.verify_source_verified_input(
            root_report, self.apk, "imsservice-source-verified", ["imsservice-source-verified"])
        downstream = RECEIPT.make_source_verified_receipt(
            "bv1-source-verified", self.apk,
            {"classes.dex": digest(b"primary"), "classes2.dex": digest(b"bridge")},
            {"source_classification_verified": True,
             "root_source_classification": upstream["source_classification"]},
            upstream)
        self.assertEqual(downstream["stage_chain"], [
            "imsservice-source-verified", "bv1-source-verified"])
        self.assertEqual(downstream["source_provenance"]["upstream_report_sha256"],
                         digest(root_report.read_bytes()))
        derived_report = self.root / "bv1.json"
        derived_report.write_text(json.dumps({"status": "SOURCE_VERIFIED",
            "strict_pins_verified": False, "source_invariants_verified": True,
            "runtime_validated": False, "release_eligible": False,
            "source_verified_receipt": downstream}), encoding="utf-8")
        checked = RECEIPT.verify_source_verified_input(
            derived_report, self.apk, "bv1-source-verified",
            ["imsservice-source-verified", "bv1-source-verified"])
        self.assertEqual(checked["source_provenance"]["upstream_stage"],
                         "imsservice-source-verified")

    def test_false_invariants_and_unclassified_receipts_are_rejected(self):
        for field, value in (("source_invariants_verified", False),
                             ("strict_pins_verified", True),
                             ("runtime_validated", True),
                             ("release_eligible", True)):
            report, _ = self.report(path=self.root / f"{field}.json", **{field: value})
            with self.subTest(field=field), self.assertRaisesRegex(RECEIPT.ReceiptError, "flags"):
                RECEIPT.verify_source_verified_input(
                    report, self.apk, "imsservice-source-verified", ["imsservice-source-verified"])
        report, payload = self.report(path=self.root / "false-classification.json")
        payload["source_verified_receipt"]["source_classification"][
            "source_classification_verified"] = False
        report.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(RECEIPT.ReceiptError, "classification"):
            RECEIPT.verify_source_verified_input(
                report, self.apk, "imsservice-source-verified", ["imsservice-source-verified"])
        self.classification["source_classification_verified"] = False
        with self.assertRaisesRegex(RECEIPT.ReceiptError, "classification"):
            RECEIPT.make_source_verified_receipt(
                "imsservice-source-verified", self.apk,
                {"classes.dex": digest(b"primary"), "classes2.dex": digest(b"bridge")},
                self.classification)

    def test_one_dex_receipt_is_supported_and_extra_dex_is_not(self):
        single = self.root / "single.apk"
        self.write_apk(single, {"classes.dex": b"one"})
        receipt = RECEIPT.make_source_verified_receipt(
            "sveservice-sv1-source-verified", single,
            {"classes.dex": digest(b"one")}, self.classification)
        report = self.root / "single.json"
        report.write_text(json.dumps({"status": "SOURCE_VERIFIED",
            "strict_pins_verified": False, "source_invariants_verified": True,
            "runtime_validated": False, "release_eligible": False,
            "source_verified_receipt": receipt}), encoding="utf-8")
        checked = RECEIPT.verify_source_verified_input(
            report, single, "sveservice-sv1-source-verified", ["sveservice-sv1-source-verified"])
        self.assertEqual(set(checked["artifact"]["dex_sha256"]), {"classes.dex"})
        with self.assertRaisesRegex(RECEIPT.ReceiptError, "inventory"):
            self.write_apk(self.root / "extra.apk", {
                "classes.dex": b"one", "classes2.dex": b"two", "classes3.dex": b"bad"})
            RECEIPT.make_source_verified_receipt(
                "sveservice-sv1-source-verified", self.root / "extra.apk",
                {"classes.dex": digest(b"one")}, self.classification)

    def test_source_verified_mode_requires_output_and_strict_stays_default(self):
        config = {"final_dex_invariants": {"pin_state": "needs-promotion"}}
        with self.assertRaisesRegex(IMS.BuildError, "requires --output"):
            IMS._validate_mode(type("Args", (), {"mode": "source-verified", "output": None})(), config)
        self.assertEqual(IMS.parser().parse_args([
            "--stock-apk", "s", "--framework-res-apk", "f", "--imsmanager-jar", "i",
            "--framework-jar", "fw", "--apktool-jar", "a", "--java", "j",
            "--javac", "jc", "--javap", "jp", "--r8-jar", "r", "--zipalign", "z",
            "--report", "report"]).mode, "strict")
        observed = {"dex_sha256": {"classes.dex": "a" * 64, "classes2.dex": "b" * 64},
                    "apk_sha256": "c" * 64}
        with self.assertRaisesRegex(IMS.BuildError, "classes.dex hash mismatch"):
            IMS._verify_pinned_invariants(observed, {"final_dex_invariants": {
                "entries": {"classes.dex": "0" * 64, "classes2.dex": "b" * 64},
                "unsigned_apk_sha256": "c" * 64}})

    def test_primary_roundtrip_ignores_only_string_index_width(self):
        before = self.root / "before"
        after = self.root / "after"
        before_file = before / "example/Test.smali"
        after_file = after / "example/Test.smali"
        before_file.parent.mkdir(parents=True)
        after_file.parent.mkdir(parents=True)
        source = (".class public Lexample/Test;\n.super Ljava/lang/Object;\n"
                  '.method public value()V\n.locals 1\nconst-string v0, "same"\n'
                  "return-void\n.end method\n")
        before_file.write_text(source, encoding="utf-8")
        after_file.write_text(source.replace("const-string v0", "const-string/jumbo v0"), encoding="utf-8")
        normalizer = IMS._module("test_primary_roundtrip", "tools/build_imsservice_w2l_trial.py")
        self.assertEqual(IMS._verify_primary_roundtrip(before, after, normalizer), 1)
        after_file.write_text(source.replace('"same"', '"changed"'), encoding="utf-8")
        with self.assertRaisesRegex(IMS.BuildError, "roundtrip drift"):
            IMS._verify_primary_roundtrip(before, after, normalizer)


if __name__ == "__main__":
    unittest.main()
