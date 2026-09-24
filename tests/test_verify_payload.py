import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.verify_payload import load_manifest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_payload.py"
FIELDS = ["stock_path", "destination", "stock_sha256", "stock_size",
          "architecture", "licensing_class", "action"]


class PayloadVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.extracted = self.base / "extracted"
        self.manifest = self.base / "manifest.tsv"

    def tearDown(self):
        self.temp.cleanup()

    def write_fixture(self, rows):
        for row in rows:
            path = self.extracted / row["stock_path"].lstrip("/")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(row.pop("content"))
        with self.manifest.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def row(path, destination, action, content):
        return {"stock_path": path, "destination": destination,
                "stock_sha256": hashlib.sha256(content).hexdigest(), "stock_size": len(content),
                "architecture": "test", "licensing_class": "fixture", "action": action,
                "content": content}

    def invoke(self, *arguments):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.extracted), *map(str, arguments),
             "--manifest", str(self.manifest)], text=True, capture_output=True, check=False)
        return completed, json.loads(completed.stdout)

    def test_verify_only_has_no_destination_effect(self):
        self.write_fixture([self.row("/system/bin/a", "ims/proprietary/bin/a", "copy", b"alpha")])
        completed, report = self.invoke()
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(report["verified"])
        self.assertEqual(report["summary"]["copied"], 0)

    def test_copy_separates_stock_apk(self):
        rows = [self.row("/system/bin/a", "ims/proprietary/bin/a", "copy", b"alpha"),
                self.row("/system/priv-app/x/x.apk", "ims/proprietary/priv-app/x/x.apk",
                         "patch-to-stage1", b"stock-apk"),
                self.row("/system/app/sveservice/sveservice.apk",
                         "ims/proprietary/app/sveservice/sveservice.apk",
                         "transform-input", b"stock-sve-apk"),
                self.row("/system/framework/framework-res.apk", "build-inputs/framework-res.apk",
                         "build-input", b"framework")]
        self.write_fixture(rows)
        destination = self.base / "destination"
        stock = self.base / "stock-input"
        completed, report = self.invoke(destination, "--copy", "--stock-input-dir", stock)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual((destination / "ims/proprietary/bin/a").read_bytes(), b"alpha")
        self.assertFalse((destination / "ims/proprietary/priv-app/x/x.apk").exists())
        self.assertEqual((stock / "system/priv-app/x/x.apk").read_bytes(), b"stock-apk")
        self.assertFalse((destination / "ims/proprietary/app/sveservice/sveservice.apk").exists())
        self.assertEqual((stock / "system/app/sveservice/sveservice.apk").read_bytes(),
                         b"stock-sve-apk")
        self.assertEqual((stock / "build-inputs/framework-res.apk").read_bytes(), b"framework")
        self.assertEqual(report["summary"]["copied"], 4)

    def test_hash_mismatch_is_reported_and_not_copied(self):
        row = self.row("/system/bin/a", "ims/a", "copy", b"expected")
        self.write_fixture([row])
        (self.extracted / "system/bin/a").write_bytes(b"tampered")
        destination = self.base / "destination"
        completed, report = self.invoke(destination, "--copy")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(report["files"][0]["status"], "sha256-mismatch")
        self.assertFalse(destination.exists())

    def test_rejects_traversal_and_duplicate_destination(self):
        rows = [self.row("/system/bin/a", "../escape", "copy", b"a")]
        self.write_fixture(rows)
        completed, report = self.invoke()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("unsafe destination", report["error"])

        rows = [self.row("/system/bin/a", "ims/same", "copy", b"a"),
                self.row("/system/bin/b", "IMS/SAME", "copy", b"b")]
        self.write_fixture(rows)
        completed, report = self.invoke()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("duplicate destination", report["error"])

    def test_existing_different_destination_is_not_overwritten(self):
        self.write_fixture([self.row("/system/bin/a", "ims/a", "copy", b"good")])
        destination = self.base / "destination"
        target = destination / "ims/a"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"keep-me")
        completed, report = self.invoke(destination, "--copy")
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(target.read_bytes(), b"keep-me")
        self.assertEqual(report["files"][0]["status"], "destination-conflict")

    def test_stage3_manifest_tracks_stock_inputs_not_generated_outputs(self):
        rows = load_manifest(ROOT / "devices" / "m11q" / "payload-manifest.tsv")
        by_source = {row["stock_path"]: row for row in rows}
        self.assertEqual(by_source["/system/priv-app/EpdgService/EpdgService.apk"]["action"],
                         "transform-input")
        self.assertEqual(by_source["/system/app/sveservice/sveservice.apk"]["action"],
                         "transform-input")
        self.assertEqual(by_source["/system/lib/libAudioFWInterface.so"]["action"],
                         "transform-input")
        self.assertEqual(by_source["/system/bin/eris"]["action"], "copy")
        self.assertNotIn("/system/etc/mnomap.json", by_source)
        destinations = {row["destination"] for row in rows}
        self.assertNotIn("ims/proprietary/app/sveservice/lib/arm/libm11q_sve_compat.so",
                         destinations)


if __name__ == "__main__":
    unittest.main()
