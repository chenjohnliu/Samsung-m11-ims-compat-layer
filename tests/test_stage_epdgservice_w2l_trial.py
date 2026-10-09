import argparse
import hashlib
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ec2_stage_tests", ROOT / "tools/stage_epdgservice_w2l_trial.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.old = b"old EC1"
        self.new = b"new EC2"
        self.old_hash = hashlib.sha256(self.old).hexdigest()
        new_hash = hashlib.sha256(self.new).hexdigest()
        self.pins = {"schema_version": 1, "transformation_id": "EC2-active-w2l-trial",
                     "classes_dex_sha256": "a" * 64, "unsigned_apk_sha256": new_hash}
        self.report = {"status": "PASS", "mode": "strict", "observed_build_pins": self.pins,
                       "output": {"strict_pins_verified": True, "artifact_published": True,
                                  "all_redecoded_classes_verified": True}}
        self.target = self.root / M.APK_RELATIVE
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(self.old)
        self.args = argparse.Namespace(android_root=self.root, apk=self.root / "new.apk",
                                       pins=self.root / "pins.json", build_report=self.root / "report.json",
                                       backup=self.root / "backup.apk")
        self.args.apk.write_bytes(self.new)
        self.args.pins.write_text(json.dumps(self.pins))
        self.args.build_report.write_text(json.dumps(self.report))
        self.guard = self.root / "framework-source"
        self.guard.write_bytes(b"verified source")
        self.constants = patch.multiple(M, EC1_APK_SHA256=self.old_hash,
                                        SOURCE_HASHES={"framework-source": hashlib.sha256(b"verified source").hexdigest()})
        self.constants.start()
        self.addCleanup(self.constants.stop)

    def test_atomic_stage_retains_verified_backup_and_is_idempotent(self):
        self.assertFalse(M.stage(self.args)["already_staged"])
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(self.args.backup.read_bytes(), self.old)
        self.assertTrue(M.stage(self.args)["already_staged"])

    def test_replacement_preserves_mode_but_not_old_ec1_timestamp(self):
        old = 1600000000
        os.chmod(self.target, 0o640)
        os.utime(self.target, (old, old))
        M.stage(self.args)
        self.assertGreater(self.target.stat().st_mtime, old)
        self.assertGreaterEqual(self.target.stat().st_mtime_ns, self.args.apk.stat().st_mtime_ns)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)

    def test_correct_content_with_stale_mtime_is_repaired_once(self):
        M.stage(self.args)
        os.utime(self.target, (1600000000, 1600000000))
        result = M.stage(self.args)
        self.assertTrue(result["already_staged"])
        self.assertTrue(result["source_mtime_refreshed"])
        self.assertGreaterEqual(self.target.stat().st_mtime_ns, self.args.apk.stat().st_mtime_ns)
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(self.args.backup.read_bytes(), self.old)
        stamp = self.target.stat().st_mtime_ns
        self.assertFalse(M.stage(self.args)["source_mtime_refreshed"])
        self.assertEqual(self.target.stat().st_mtime_ns, stamp)

    def test_unrecognized_target_is_never_overwritten(self):
        self.target.write_bytes(b"user edit")
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            M.stage(self.args)
        self.assertEqual(self.target.read_bytes(), b"user edit")
        self.assertFalse(self.args.backup.exists())

    def test_known_previous_trial_upgrade_requires_original_backup(self):
        previous = b"previous EC2"
        self.target.write_bytes(previous)
        previous_hash = hashlib.sha256(previous).hexdigest()
        with patch.object(M, "PREVIOUS_EC2_APK_SHA256", previous_hash):
            with self.assertRaisesRegex(ValueError, "backup"):
                M.stage(self.args)
            self.assertEqual(self.target.read_bytes(), previous)
            self.args.backup.write_bytes(self.old)
            self.assertFalse(M.stage(self.args)["already_staged"])
        self.assertEqual(self.target.read_bytes(), self.new)
        self.assertEqual(self.args.backup.read_bytes(), self.old)

    def test_changed_framework_stops_before_staging(self):
        self.guard.write_bytes(b"later source change")
        with self.assertRaisesRegex(ValueError, "prerequisite"):
            M.stage(self.args)
        self.assertEqual(self.target.read_bytes(), self.old)

    def test_discovery_report_cannot_be_installed(self):
        self.report["mode"] = "pin-discovery"
        self.args.build_report.write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError, "strict build"):
            M.stage(self.args)
        self.assertEqual(self.target.read_bytes(), self.old)


if __name__ == "__main__":
    unittest.main()
