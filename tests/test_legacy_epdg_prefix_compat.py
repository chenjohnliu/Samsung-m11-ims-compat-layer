import argparse
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "tools"))
import legacy_epdg_prefix_compat as T


def canonical(extra=""):
    return ".class public Lcom/sec/epdg/EpdgUtils;\n" + T.ORIGINAL_METHOD + "\n\n" + T.LEGACY_HELPER + "\n" + extra


class LegacyEpdgPrefixCompatTests(unittest.TestCase):
    def test_patch_changes_only_exact_method_and_uses_existing_helper(self):
        source = canonical(".method public preserved()V\n return-void\n.end method\n")
        with mock.patch.object(T, "INPUT_SHA256", T.sha(source)):
            result = T.patch(source)
        self.assertEqual(result, source.replace(T.ORIGINAL_METHOD, T.PATCHED_METHOD, 1))
        self.assertIn("isIwlanLegacyMode()Z", result)
        self.assertEqual(result.count('const-string v0, "epdg_data"'), 1)
        self.assertEqual(result.count('const-string v0, "ril.data.intfprefix"'), 1)
        self.assertIn(".method public preserved()V\n return-void", result)

    def test_input_method_and_helper_drift_fail_closed(self):
        source = canonical()
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            T.patch(source)
        for changed, message in ((source.replace("epdg_data", "other", 1), "anchor"),
                                 (source.replace("legacy", "legacy-x", 1), "helper")):
            with self.subTest(message=message), mock.patch.object(T, "INPUT_SHA256", T.sha(changed)):
                with self.assertRaisesRegex(ValueError, message):
                    T.patch(changed)

    def test_mode_model_preserves_ap_assist_default_and_unknown(self):
        self.assertEqual(T.modeled_prefix("legacy", "rmnet_data"), "rmnet_data")
        self.assertEqual(T.modeled_profile_id("rmnet_data1", "legacy", "rmnet_data"), 2)
        self.assertEqual(T.modeled_prefix("AP-assisted", "rmnet_data"), "epdg_data")
        self.assertEqual(T.modeled_profile_id("epdg_data1", "AP-assisted", "rmnet_data"), 2)
        self.assertEqual(T.modeled_prefix(None, "rmnet_data"), "epdg_data")
        self.assertEqual(T.modeled_prefix("unexpected", "rmnet_data"), "epdg_data")
        self.assertEqual(T.modeled_profile_id("rmnet_data1", None, "rmnet_data"), -3)

    def test_legacy_property_default_and_bad_interface_model(self):
        self.assertEqual(T.modeled_prefix("legacy"), "rmnet")
        self.assertEqual(T.modeled_profile_id("rmnet1", "legacy"), 2)
        self.assertEqual(T.modeled_profile_id("rmnet_data1", "legacy"), -3)

    def test_build_pin_loader_is_strict(self):
        pins = {"schema_version": 1, "transformation_id": T.TRANSFORMATION_ID,
                "classes_dex_sha256": "a" * 64, "unsigned_apk_sha256": "b" * 64}
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp) / "pins.json"
            path.write_text(json.dumps(pins), encoding="utf-8")
            with mock.patch.object(T.BASE, "_regular", side_effect=lambda value, _label: value):
                self.assertEqual(T.load_pins(path), pins)
            for value in (None, "pending", "Z" * 64):
                with self.subTest(value=value):
                    bad = {**pins, "classes_dex_sha256": value}
                    path.write_text(json.dumps(bad), encoding="utf-8")
                    with mock.patch.object(T.BASE, "_regular", side_effect=lambda item, _label: item):
                        with self.assertRaises(T.BuildError):
                            T.load_pins(path)

    def test_verify_apk_gates_dex_and_reports_unsigned_identity(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            apk = root / "epdg.apk"
            dex = b"lg2-dex"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("classes.dex", dex)
                archive.writestr("resource", b"kept")
            pins = {"schema_version": 1, "transformation_id": T.TRANSFORMATION_ID,
                    "classes_dex_sha256": T.hashlib.sha256(dex).hexdigest(),
                    "unsigned_apk_sha256": T.BASE.sha256_file(apk)}
            path = root / "pins.json"
            path.write_text(json.dumps(pins), encoding="utf-8")
            with mock.patch.object(T.BASE, "_regular", side_effect=lambda value, _label: value):
                result = T.verify_apk(apk, path)
            self.assertEqual(result["classes_dex_sha256"], pins["classes_dex_sha256"])
            self.assertTrue(result["unsigned_apk_byte_identical"])
            pins["classes_dex_sha256"] = "d" * 64
            path.write_text(json.dumps(pins), encoding="utf-8")
            with mock.patch.object(T.BASE, "_regular", side_effect=lambda value, _label: value):
                with self.assertRaisesRegex(T.BuildError, "classes.dex pin mismatch"):
                    T.verify_apk(apk, path)

    def test_discovery_and_strict_output_contract(self):
        parser = T.parser()
        common = ["--base-apk", "base.apk", "--apktool-jar", "apktool.jar",
                  "--java", "java", "--report", "report.json"]
        discovered = parser.parse_args(common + ["--discover-pins"])
        self.assertTrue(discovered.discover_pins)
        self.assertIsNone(discovered.output)
        strict = parser.parse_args(common + ["--output", "out.apk", "--pins", "pins.json"])
        self.assertFalse(strict.discover_pins)
        self.assertEqual(strict.output, Path("out.apk"))

    def test_source_verified_only_bypasses_serialized_output_hashes(self):
        pins = {"schema_version": 1, "transformation_id": T.TRANSFORMATION_ID,
                "classes_dex_sha256": "a" * 64, "unsigned_apk_sha256": "b" * 64}
        changed = {**pins, "classes_dex_sha256": "c" * 64, "unsigned_apk_sha256": "d" * 64}
        with self.assertRaisesRegex(T.BuildError, "pin drift"):
            T.verify_output_pins(changed, pins)
        T.verify_output_pins(changed, pins, True)
        with self.assertRaisesRegex(T.BuildError, "identity drift"):
            T.verify_output_pins({**changed, "transformation_id": "other"}, pins, True)

    def test_source_verified_parser_is_opt_in_and_requires_explicit_receipt_arg(self):
        common = ["--base-apk", "base.apk", "--apktool-jar", "apktool.jar",
                  "--java", "java", "--report", "report.json", "--output", "out.apk"]
        strict = T.parser().parse_args(common)
        self.assertFalse(strict.source_verified)
        self.assertIsNone(strict.source_receipt)
        source = T.parser().parse_args(common + ["--source-verified", "--source-receipt", "ec2.json"])
        self.assertTrue(source.source_verified)
        self.assertEqual(source.source_receipt, Path("ec2.json"))

    def test_fixed_input_and_base_pins_are_promoted_hashes(self):
        for value in (T.INPUT_SHA256, T.BASE_APK_SHA256, T.BASE_DEX_SHA256,
                      T.BASE.APKTOOL_SHA256, T.BASE.JAVA_SHA256):
            self.assertEqual(len(value), 64)
            int(value, 16)


if __name__ == "__main__":
    unittest.main()
