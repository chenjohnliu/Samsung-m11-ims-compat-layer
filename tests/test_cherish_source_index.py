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
        self.assertEqual(result, {"projects": 14, "patches": 24, "reference_only": 1, "forks_checked": 0})

    def test_shared_device_route_uses_m11q_volte_without_duplicate_local_patches(self) -> None:
        data = self.mutated_index()
        device = next(p for p in data["projects"] if p["path"] == "device/samsung/m11q")
        self.assertEqual(data["checkpoint_manifests"][-1],
                         "platform/checkpoints/m11q-shared-20261023/manifest.json")
        self.assertEqual(device["source_route"], "patch_recipe")
        self.assertIsNone(device["synchronized_fork"])
        self.assertEqual(device["base_commit"], "a42e98add2d431b5d677b4ec6e51f5f02ca3e0e7")
        self.assertEqual(device["base_tree"], "3f4fb779d9c4d07a6357806acf1771a9a7fa5087")
        self.assertEqual(len(device["patches"]), 1)
        self.assertTrue(device["patches"][0]["path"].startswith(
            "platform/checkpoints/m11q-shared-20261023/"))
        self.assertEqual(device["historical_synchronized_fork"]["branch"],
                         "cherish-13-m11q-ims")
        self.assertEqual(device["maintained_shared_branch"]["branch"], "m11q-volte")

    def test_shared_device_pin_drift_is_rejected(self) -> None:
        data = self.mutated_index()
        device = next(p for p in data["projects"] if p["path"] == "device/samsung/m11q")
        device["base_commit"] = "0f1da5855d27841d53743cd878ecd2d09679a941"
        with self.assertRaisesRegex(ValidationError, "source base mismatch for device/samsung/m11q"):
            self.validate(data)

    def test_local_supplement_tree_chain_cannot_be_reordered(self) -> None:
        data = self.mutated_index()
        entry = next(p for p in data["projects"] if p["path"] == "frameworks/base")
        entry["patches"][-1]["before_tree"] = "0" * 40
        with self.assertRaisesRegex(ValidationError, "patch metadata differs"):
            self.validate(data)

    def test_api_supplement_cannot_be_omitted_from_manifest_order(self) -> None:
        data = self.mutated_index()
        data["checkpoint_manifests"].pop()
        with self.assertRaisesRegex(ValidationError, "checkpoint_manifests"):
            self.validate(data)

    def test_api_supplement_cannot_be_omitted_from_patch_chain(self) -> None:
        data = self.mutated_index()
        entry = next(p for p in data["projects"] if p["path"] == "frameworks/base")
        entry["patches"].pop()
        with self.assertRaisesRegex(ValidationError, "ordered patch count mismatch"):
            self.validate(data)

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
