import argparse
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_imsservice_w2l_trial as B
import stage_imsservice_w2l_trial as S
import verify_ims_w2l_trial_artifacts as V


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Bv1ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def pins(self, data=b"new"):
        obj = {"schema_version": 1, "transformation_id": B.IDENTITY,
               "classes_dex_sha256": digest(data), "unsigned_apk_sha256": digest(data)}
        return self.write("pins.json", json.dumps(obj).encode()), obj

    def test_pins_reject_wrong_identity_and_placeholder(self):
        path, obj = self.pins()
        self.assertEqual(B.load_pins(path), obj)
        for key, bad in (("transformation_id", "other"), ("classes_dex_sha256", "pending")):
            changed = {**obj, key: bad}
            path.write_text(json.dumps(changed))
            with self.assertRaises(B.BuildError):
                B.load_pins(path)

    def test_primary_inventory_and_instruction_drift_rejected(self):
        body = b".class public Lcom/sec/Test;\n.super Ljava/lang/Object;\n.method public static value()I\n.locals 1\nconst/4 v0, 0x1\nreturn v0\n.end method\n"
        self.write("before/com/sec/Test.smali", body)
        final = self.write("after/com/sec/Test.smali", body)
        contract = {"targets": [{"path": "com/sec/Test.smali", "redecoded_sha256": digest(body)}], "additions": []}
        self.assertEqual(B.verify_envelope(self.root / "before", self.root / "after", contract)[0], 1)
        final.write_bytes(body.replace(b"0x1", b"0x2"))
        with self.assertRaisesRegex(B.BuildError, "instruction/metadata"):
            B.verify_envelope(self.root / "before", self.root / "after", contract, True)
        final.write_bytes(body)
        self.write("after/com/sec/Extra.smali", body)
        with self.assertRaisesRegex(B.BuildError, "inventory"):
            B.verify_envelope(self.root / "before", self.root / "after", contract)

    def test_native_reference_resolution_rejects_private_member(self):
        helper = b".class public Lcom/sec/Helper;\n.super Ljava/lang/Object;\n.method public static check()V\n.locals 0\ninvoke-static {}, Lcom/sec/Native;->value()V\nreturn-void\n.end method\n"
        self.write("smali/com/sec/Helper.smali", helper)
        native = self.write("smali/com/sec/Native.smali", b".class public Lcom/sec/Native;\n.super Ljava/lang/Object;\n.method private static value()V\n.locals 0\nreturn-void\n.end method\n")
        contract = {"additions": [{"path": "com/sec/Helper.smali"}]}
        with self.assertRaisesRegex(B.BuildError, "inaccessible"):
            B.verify_references(self.root / "smali", contract)
        native.write_bytes(native.read_bytes().replace(b"private static", b"public static"))
        self.assertEqual(B.verify_references(self.root / "smali", contract)["resolved_samsung_helper_references"], 1)

    def test_string_index_width_preserves_literal_and_register(self):
        text = '.class public LX;\n.super Ljava/lang/Object;\n.method public static value()V\n.locals 1\nconst-string v0, "phone"\nreturn-void\n.end method\n'
        wide = text.replace("const-string v0", "const-string/jumbo v0")
        self.assertEqual(B.normalized_smali(text), B.normalized_smali(wide))
        self.assertNotEqual(B.normalized_smali(text), B.normalized_smali(wide.replace('"phone"', '"other"')))

    def test_package_visible_native_fields_are_inventoried(self):
        path = self.write("smali/com/sec/Native.smali", b".class Lcom/sec/Native;\n.super Ljava/lang/Object;\n.field mLinkProperties:Ljava/lang/Object;\n")
        classes = B.REFS.inventory(path.parents[2])
        self.assertEqual(B.REFS.resolve(classes, "Lcom/sec/Native;", "mLinkProperties:Ljava/lang/Object;"), ("Lcom/sec/Native;", []))

    def staging_fixture(self):
        pins_path, pins = self.pins()
        candidate = self.write("candidate.apk", b"new")
        source = self.write("android/" + S.APK_RELATIVE, b"old")
        epdg = self.write("android/" + S.EC2.APK_RELATIVE, b"epdg")
        self.write("android/device/samsung/m11q/ims/proprietary/framework/imsmanager.jar", b"manager")
        report = {"status": "PASS", "mode": "strict", "observed_build_pins": pins,
                  "output": {"strict_pins_verified": True, "artifact_published": True,
                             "all_redecoded_classes_verified": True, "unrelated_zip_entries_preserved": True,
                             "classes2_dex_sha256": B.BRIDGE_DEX}}
        report_path = self.write("report.json", json.dumps(report).encode())
        args = argparse.Namespace(android_root=self.root / "android", apk=candidate, pins=pins_path,
                                  build_report=report_path, backup=self.root / "backup.apk")
        return args, source, epdg, report

    def test_stage_preserves_original_and_refreshes_incremental_timestamp(self):
        args, source, epdg, _ = self.staging_fixture()
        os.utime(source, (100, 100))
        with mock.patch.object(B, "BASE_APK", digest(b"old")), mock.patch.object(B, "IMSMANAGER_SHA256", digest(b"manager")), mock.patch.object(S, "CURRENT_EPDG_APK", digest(epdg.read_bytes())), mock.patch.dict(S.EC2.SOURCE_HASHES, {}, clear=True):
            result = S.stage(args)
            self.assertFalse(result["already_staged"])
            self.assertEqual(source.read_bytes(), b"new")
            self.assertEqual(args.backup.read_bytes(), b"old")
            self.assertGreater(source.stat().st_mtime, 100)
            self.assertTrue(S.stage(args)["already_staged"])

    def test_stage_incomplete_report_and_unknown_source_leave_bytes_untouched(self):
        args, source, epdg, report = self.staging_fixture()
        report["output"]["unrelated_zip_entries_preserved"] = False
        args.build_report.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "strict BV1 report"):
            S.stage(args)
        self.assertEqual(source.read_bytes(), b"old")
        report["output"]["unrelated_zip_entries_preserved"] = True
        args.build_report.write_text(json.dumps(report))
        with mock.patch.object(B, "IMSMANAGER_SHA256", digest(b"manager")), mock.patch.object(S, "CURRENT_EPDG_APK", digest(epdg.read_bytes())), mock.patch.dict(S.EC2.SOURCE_HASHES, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "unknown IMS source"):
                S.stage(args)
        self.assertFalse(args.backup.exists())

    def test_combined_gate_checks_both_ims_dex_entries(self):
        import zipfile
        pins, _ = self.pins(b"primary")
        apk = self.root / "signed.apk"
        def package(bridge):
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("classes.dex", b"primary")
                archive.writestr("classes2.dex", bridge)
                archive.writestr("META-INF/CERT.RSA", b"rom-signature")
        package(b"bridge")
        with mock.patch.object(V.EC2, "verify", return_value={"ec2_dex_verified": True, "classes_dex_sha256": "epdg"}), mock.patch.object(B, "BRIDGE_DEX", digest(b"bridge")):
            self.assertTrue(V.verify(self.root / "epdg", apk, pins)["bv1_verified"])
            package(b"wrong-bridge")
            with self.assertRaisesRegex(ValueError, "revision mismatch"):
                V.verify(self.root / "epdg", apk, pins)

    def test_combined_legacy_gate_requires_prefix_fixed_epdg(self):
        import legacy_epdg_prefix_compat as LG2
        import zipfile
        pins, _ = self.pins(b"primary")
        apk = self.root / "signed-lg2.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("classes.dex", b"primary")
            archive.writestr("classes2.dex", b"bridge")
        prefix_pins = self.root / "lg2-pins.json"
        with mock.patch.object(LG2, "verify_apk", return_value={
                "classes_dex_sha256": "lg2"}) as gate, mock.patch.object(
                V.EC2, "verify") as old_gate, mock.patch.object(B, "BRIDGE_DEX", digest(b"bridge")):
            result = V.verify(self.root / "epdg", apk, pins, epdg_prefix_pins=prefix_pins)
            self.assertTrue(result["legacy_epdg_prefix_verified"])
            self.assertFalse(result["ec2_r2_verified"])
            old_gate.assert_not_called()
            gate.assert_called_once_with(self.root / "epdg", prefix_pins)
            gate.side_effect = LG2.BuildError("packaged LG2 classes.dex pin mismatch")
            with self.assertRaisesRegex(LG2.BuildError, "LG2 classes.dex"):
                V.verify(self.root / "epdg", apk, pins, epdg_prefix_pins=prefix_pins)


if __name__ == "__main__":
    unittest.main()
