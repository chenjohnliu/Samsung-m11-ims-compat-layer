"""Regression checks for the public Cherish source-index verifier."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.verify_cherish_source_index import ValidationError, validate_index_data


class CherishSourceIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = REPO_ROOT / "devices" / "m11q" / "cherish-source-index.json"
        cls.index = json.loads(path.read_text(encoding="utf-8-sig"))

    def mutated_index(self) -> dict:
        return copy.deepcopy(self.index)

    def validate(self, data: dict) -> None:
        validate_index_data(data, REPO_ROOT)

    def test_repository_index_and_artifacts_pass_offline(self) -> None:
        result = validate_index_data(self.mutated_index(), REPO_ROOT)
        self.assertEqual(result, {"projects": 14, "patches": 18, "reference_only": 1, "forks_checked": 0})

    def test_patch_hash_drift_is_rejected(self) -> None:
        data = self.mutated_index()
        entry = next(p for p in data["projects"] if p["path"] == "frameworks/base")
        entry["patches"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "patch metadata differs"):
            self.validate(data)

    def test_broken_ordered_tree_chain_is_rejected(self) -> None:
        data = self.mutated_index()
        entry = next(p for p in data["projects"] if p["path"] == "packages/services/Telecomm")
        entry["patches"][2]["before_tree"] = "0" * 40
        with self.assertRaisesRegex(ValidationError, "patch metadata differs|broken patch tree chain"):
            self.validate(data)

    def test_mms_reference_patch_cannot_be_applied_again(self) -> None:
        data = self.mutated_index()
        entry = next(p for p in data["projects"] if p["path"] == "packages/services/Mms")
        entry["patches"].append(copy.deepcopy(entry["reference_only_patches"][0]))
        with self.assertRaisesRegex(ValidationError, "ordered patch count mismatch"):
            self.validate(data)

    def test_fork_commit_mapping_drift_is_rejected(self) -> None:
        data = self.mutated_index()
        entry = next(p for p in data["projects"] if p["path"] == "frameworks/opt/telephony")
        entry["synchronized_fork"]["commits"][1]["parent"] = "0" * 40
        with self.assertRaisesRegex(ValidationError, "fork commit parent mapping drift"):
            self.validate(data)

    def test_wrong_repository_or_branch_is_rejected(self) -> None:
        for field, value in (("repository", "https://github.com/example/wrong.git"),
                             ("branch", "m11q-vowifi-audio-path")):
            with self.subTest(field=field):
                data = self.mutated_index()
                entry = next(p for p in data["projects"] if p["path"] == "packages/services/Telecomm")
                entry["synchronized_fork"][field] = value
                with self.assertRaisesRegex(ValidationError, "synchronized fork .* mismatch"):
                    self.validate(data)


if __name__ == "__main__":
    unittest.main()
