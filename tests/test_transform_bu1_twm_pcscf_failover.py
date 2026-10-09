import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_bu1_twm_pcscf_failover.py"
CONTRACT = ROOT / "devices" / "m11q" / "bu1-twm-pcscf-failover-trial-contract.json"
FIXTURE = ROOT.parent / "work" / "bt1_transform_input" / "decoded" / "res" / "raw" / "imsprofile.json"


def load():
    spec = importlib.util.spec_from_file_location("transform_bu1", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load()


class TransformBu1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_repository_contract_and_fixture_apply_only_twm_normal_profile(self):
        if not FIXTURE.is_file():
            self.skipTest("private decoded stock fixture is unavailable")
        output = self.base / "imsprofile.json"
        result = MODULE.transform(CONTRACT, FIXTURE, output)
        self.assertTrue(result["changed"])
        before = json.loads(FIXTURE.read_text(encoding="utf-8"))["profile"]
        after = json.loads(output.read_text(encoding="utf-8"))["profile"]
        self.assertEqual(len(before), len(after))
        changed = []
        for old, new in zip(before, after):
            if old != new:
                changed.append((old, new))
        self.assertEqual(len(changed), 1)
        old, new = changed[0]
        self.assertEqual(old["name"], "TWM Mobile VoLTE")
        expected = copy.deepcopy(old)
        expected["timer"] = MODULE.TRIAL_TIMER
        self.assertEqual(new, expected)
        self.assertNotIn("reg_retry_base_time", new)

    def test_rejects_emergency_or_retry_policy_drift(self):
        if not FIXTURE.is_file():
            self.skipTest("private decoded stock fixture is unavailable")
        text = FIXTURE.read_text(encoding="utf-8")
        identity = '      "name": "TWM Mobile VoLTE",'
        emergency = text.replace(identity, identity + '\n      "emergency_support": true,', 1)
        source = self.base / "emergency.json"
        source.write_text(emergency, encoding="utf-8")
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        import hashlib
        raw["target"]["input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        contract = self.base / "contract.json"
        contract.write_text(json.dumps(raw), encoding="utf-8")
        old_hash = MODULE.EXPECTED_INPUT_SHA256
        MODULE.EXPECTED_INPUT_SHA256 = raw["target"]["input_sha256"]
        try:
            with self.assertRaisesRegex(MODULE.TransformError, "emergency"):
                MODULE.transform(contract, source, self.base / "out.json")
        finally:
            MODULE.EXPECTED_INPUT_SHA256 = old_hash

    def test_nonoverwrite_and_allow_identical(self):
        if not FIXTURE.is_file():
            self.skipTest("private decoded stock fixture is unavailable")
        output = self.base / "imsprofile.json"
        MODULE.transform(CONTRACT, FIXTURE, output)
        with self.assertRaisesRegex(MODULE.TransformError, "overwrite"):
            MODULE.transform(CONTRACT, FIXTURE, output)
        result = MODULE.transform(CONTRACT, FIXTURE, output, allow_identical=True)
        self.assertFalse(result["changed"])


if __name__ == "__main__":
    unittest.main()
