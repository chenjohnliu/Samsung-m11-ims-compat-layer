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
import stage_legacy_epdg_prefix as S


def sha(data):
    return hashlib.sha256(data).hexdigest()


class StageLegacyPrefixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.android = self.root / "android"
        self.target = self.android / S.APK_RELATIVE
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"ec2")
        self.config = "device/samsung/m11q/system.prop"
        (self.android / self.config).write_bytes(b"legacy")
        self.pins = {"schema_version": 1, "transformation_id": "LG2-legacy-epdg-prefix",
                     "unsigned_apk_sha256": sha(b"lg2"), "classes_dex_sha256": sha(b"dex")}
        self.apk = self.root / "candidate.apk"
        self.apk.write_bytes(b"lg2")
        self.report = self.root / "report.json"
        self.payload = {"status": "PASS", "mode": "strict", "observed_build_pins": self.pins,
                        "output": {k: True for k in ("strict_pins_verified", "artifact_published",
                            "all_redecoded_classes_verified", "unrelated_zip_entries_preserved")}}
        self.report.write_text(json.dumps(self.payload))
        self.args = argparse.Namespace(android_root=self.android, state_dir=self.root / "state",
            apk=self.apk, pins=self.root / "pins.json", build_report=self.report,
            backup=self.root / "backup.apk", rollback=False)
        patches = [mock.patch.object(S, "BASE_APK", sha(b"ec2")),
                   mock.patch.object(S.LG2, "load_pins", return_value=self.pins),
                   mock.patch.object(S.LG2, "verify_apk", return_value={}),
                   mock.patch.object(S.LEG1, "bundle", return_value=(
                       {self.config: b"original"}, {self.config: b"legacy"})),
                   mock.patch.dict(S.LEG1.PREREQUISITES, {}, clear=True)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_stage_idempotent_backup_mtime_and_rollback(self):
        os.utime(self.target, (100, 100))
        self.assertFalse(S.stage(self.args)["already_staged"])
        self.assertEqual(self.target.read_bytes(), b"lg2")
        self.assertEqual(self.args.backup.read_bytes(), b"ec2")
        self.assertGreater(self.target.stat().st_mtime, 100)
        self.assertTrue(S.stage(self.args)["already_staged"])
        self.args.rollback = True
        S.stage(self.args)
        self.assertEqual(self.target.read_bytes(), b"ec2")
        self.assertEqual((self.android / self.config).read_bytes(), b"legacy")

    def test_incomplete_report_and_candidate_drift_do_not_write(self):
        self.payload["output"]["all_redecoded_classes_verified"] = False
        self.report.write_text(json.dumps(self.payload))
        with self.assertRaisesRegex(ValueError, "complete strict"):
            S.stage(self.args)
        self.payload["output"]["all_redecoded_classes_verified"] = True
        self.report.write_text(json.dumps(self.payload))
        self.apk.write_bytes(b"unknown")
        with self.assertRaisesRegex(ValueError, "APK pin drift"):
            S.stage(self.args)
        self.assertEqual(self.target.read_bytes(), b"ec2")
        self.assertFalse(self.args.backup.exists())

    def test_unknown_source_configuration_and_backup_are_refused(self):
        self.target.write_bytes(b"unknown")
        with self.assertRaisesRegex(ValueError, "unknown source"):
            S.stage(self.args)
        self.target.write_bytes(b"ec2")
        (self.android / self.config).write_bytes(b"other")
        with self.assertRaisesRegex(ValueError, "exact LEG1"):
            S.stage(self.args)
        (self.android / self.config).write_bytes(b"legacy")
        self.args.backup.write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "backup drift"):
            S.stage(self.args)
        self.assertEqual(self.target.read_bytes(), b"ec2")

    def test_overlapping_backup_and_missing_rollback_backup_are_refused(self):
        self.args.rollback = True
        with self.assertRaisesRegex(ValueError, "rollback requires"):
            S.stage(self.args)
        self.args.backup = self.target
        with self.assertRaisesRegex(ValueError, "overlapping"):
            S.stage(self.args)


if __name__ == "__main__":
    unittest.main()
