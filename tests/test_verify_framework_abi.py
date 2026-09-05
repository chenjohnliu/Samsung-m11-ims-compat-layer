import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.verify_framework_abi import VerificationError, verify


CLASS_A = "com.example.IFirst"
CLASS_B = "com.example.ISecond"
ABI_A = 'Compiled from "IFirst.java"\npublic interface com.example.IFirst {\n  public abstract void first();\n}\n'
ABI_B = 'Compiled from "ISecond.java"\npublic interface com.example.ISecond {\n  public abstract int second();\n}\n'


class FrameworkAbiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.jar = self.root / "framework.jar"
        self.jar.write_bytes(b"synthetic framework identity only")
        (self.root / "first.txt").write_text(ABI_A, encoding="utf-8")
        (self.root / "second.txt").write_text(ABI_B, encoding="utf-8")
        self.config = self.root / "build.json"
        self.write_config(hashlib.sha256(self.jar.read_bytes()).hexdigest())

    def tearDown(self):
        self.temp.cleanup()

    def write_config(self, golden):
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "toolchain": {"golden_framework_minus_apex": {"sha256": golden}},
                    "abi_fixture_root": ".",
                    "abi_fixtures": {CLASS_A: "first.txt", CLASS_B: "second.txt"},
                }
            ),
            encoding="utf-8",
        )

    @staticmethod
    def runner(outputs, failure=None):
        def run(command):
            class_name = command[-1]
            if failure == class_name:
                return subprocess.CompletedProcess(command, 7, "", "synthetic javap failure")
            return subprocess.CompletedProcess(command, 0, outputs[class_name], "")
        return run

    def test_golden_hash_and_abi(self):
        report = verify(
            self.jar, self.config, "golden", "synthetic-javap",
            self.runner({CLASS_A: ABI_A.replace("\n", "\r\n"), CLASS_B: ABI_B}),
        )
        self.assertEqual(report["classification"], "golden")
        self.assertTrue(all(item["match"] for item in report["abi"]))

    def test_compatible_mode_accepts_hash_difference_with_exact_abi(self):
        self.write_config("0" * 64)
        report = verify(
            self.jar, self.config, "compatible", "synthetic-javap",
            self.runner({CLASS_A: ABI_A, CLASS_B: ABI_B}),
        )
        self.assertEqual(report["classification"], "compatible-abi-only")
        self.assertFalse(report["golden_hash_match"])

    def test_golden_mode_rejects_hash_difference(self):
        self.write_config("0" * 64)
        with self.assertRaisesRegex(VerificationError, "hash mismatch"):
            verify(
                self.jar, self.config, "golden", "synthetic-javap",
                self.runner({CLASS_A: ABI_A, CLASS_B: ABI_B}),
            )

    def test_abi_mismatch_fails_closed(self):
        with self.assertRaisesRegex(VerificationError, "ABI mismatch"):
            verify(
                self.jar, self.config, "golden", "synthetic-javap",
                self.runner({CLASS_A: ABI_A + "changed\n", CLASS_B: ABI_B}),
            )

    def test_javap_failure_fails_closed(self):
        with self.assertRaisesRegex(VerificationError, "javap failed"):
            verify(
                self.jar, self.config, "golden", "synthetic-javap",
                self.runner({CLASS_A: ABI_A, CLASS_B: ABI_B}, failure=CLASS_B),
            )

    def test_invalid_config_is_rejected(self):
        self.write_config("NOT-A-HASH")
        with self.assertRaisesRegex(VerificationError, "64 lowercase hex"):
            verify(
                self.jar, self.config, "golden", "synthetic-javap",
                self.runner({CLASS_A: ABI_A, CLASS_B: ABI_B}),
            )

    def test_fixture_path_escape_is_rejected(self):
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["abi_fixtures"] = {CLASS_A: "../outside.txt"}
        self.config.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(VerificationError, "not safe root-relative"):
            verify(self.jar, self.config, "golden", "synthetic-javap", self.runner({}))


if __name__ == "__main__":
    unittest.main()
