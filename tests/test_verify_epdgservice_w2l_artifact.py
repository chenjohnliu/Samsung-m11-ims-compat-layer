import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ec2_artifact_tests", ROOT / "tools/verify_epdgservice_w2l_artifact.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class ArtifactTests(unittest.TestCase):
    def test_signed_container_changes_do_not_hide_old_dex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pins = root / "pins.json"
            pins.write_text(json.dumps({"schema_version": 1, "transformation_id": "EC2-active-w2l-trial",
                                       "unsigned_apk_sha256": "a" * 64,
                                       "classes_dex_sha256": hashlib.sha256(b"EC2").hexdigest()}))
            for name, dex in (("current", b"EC2"), ("old", b"EC1")):
                path = root / (name + ".apk")
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("META-INF/CERT.RSA", b"ROM signature")
                    archive.writestr("classes.dex", dex)
                if name == "current":
                    self.assertTrue(M.verify(path, pins)["ec2_dex_verified"])
                else:
                    with self.assertRaisesRegex(ValueError, "NOT EC2"):
                        M.verify(path, pins)

    def test_extra_dex_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pins = root / "pins.json"
            pins.write_text(json.dumps({"schema_version": 1, "transformation_id": "EC2-active-w2l-trial",
                                       "unsigned_apk_sha256": "a" * 64,
                                       "classes_dex_sha256": hashlib.sha256(b"EC2").hexdigest()}))
            path = root / "extra.apk"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("classes.dex", b"EC2")
                archive.writestr("classes2.dex", b"unexpected")
            with self.assertRaisesRegex(ValueError, "inventory"):
                M.verify(path, pins)


if __name__ == "__main__":
    unittest.main()
