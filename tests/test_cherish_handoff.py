import hashlib
import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HANDOFF_PATH = ROOT / "devices/m11q/cherish-android13-handoff.json"


def load_handoff():
    return json.loads(HANDOFF_PATH.read_text(encoding="utf-8"))


class CherishAndroid13HandoffTests(unittest.TestCase):
    def test_handoff_is_an_unresolved_source_inventory_not_a_deployment_lock(self):
        handoff = load_handoff()
        self.assertEqual(handoff["target"]["rom"], "CherishOS")
        self.assertEqual(handoff["target"]["android_version"], 13)
        self.assertIsNone(handoff["target"]["manifest_revision"])
        self.assertIsNone(handoff["target"]["base_revision"])
        self.assertEqual(handoff["target"]["resolution_status"], "unresolved")
        self.assertEqual(handoff["readiness"]["published_source_inventory"], "present")
        self.assertEqual(handoff["readiness"]["target_integration"], "pending")
        self.assertFalse(handoff["readiness"]["dependency_closure"])
        for key in ("port_applied", "build_performed", "build_runtime_current_port_validated", "deployable"):
            self.assertFalse(handoff["readiness"][key], key)

    def test_all_local_evidence_references_exist(self):
        for relative in load_handoff()["required_evidence_paths"]:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())

    def test_repository_pins_are_full_and_unique(self):
        repos = load_handoff()["source_repositories"]
        expected = {
            "Samsung-m11-ims-compat-layer": "https://github.com/chenjohnliu/Samsung-m11-ims-compat-layer.git",
            "android_device_samsung_m11q": "https://github.com/chenjohnliu/android_device_samsung_m11q.git",
            "proprietary_vendor_samsung_m11q": "https://github.com/chenjohnliu/proprietary_vendor_samsung_m11q.git",
            "android_packages_services_Telecomm": "https://github.com/chenjohnliu/android_packages_services_Telecomm.git",
            "android_kernel_samsung_sdm450": "https://github.com/chenjohnliu/android_kernel_samsung_sdm450.git",
        }
        mapping = {repo["name"]: repo["url"] for repo in repos}
        names = [repo["name"] for repo in repos]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(repos), 5)
        self.assertEqual(mapping, expected)
        for repo in repos:
            with self.subTest(repo=repo["name"]):
                self.assertRegex(repo["revision"], r"^[0-9a-f]{40}$")
                self.assertTrue(repo["url"].startswith("https://github.com/"))

    def test_historical_artifact_pins_match_public_contracts(self):
        handoff = load_handoff()
        artifacts = {
            item["id"]: item
            for item in handoff["artifact_references"]["historical_unsigned_outputs"]
        }
        for item in artifacts.values():
            contract = json.loads((ROOT / item["contract_path"]).read_text(encoding="utf-8"))
            with self.subTest(artifact=item["id"]):
                expected = contract.get("unsigned_apk_sha256")
                if expected is None:
                    expected = contract["final_dex_invariants"]["unsigned_apk_sha256"]
                self.assertEqual(expected, item["unsigned_apk_sha256"])
                if "classes_dex_sha256" in item:
                    self.assertEqual(contract["classes_dex_sha256"], item["classes_dex_sha256"])

    def test_global_wfc_resource_pin_matches_policy_not_an_apk_claim(self):
        handoff = load_handoff()["artifact_references"]["global_wfc_v2"]
        policy = json.loads((ROOT / handoff["policy_path"]).read_text(encoding="utf-8"))
        self.assertEqual(policy["policy"], handoff["policy"])
        self.assertEqual(policy["vendor_sha256"], handoff["vendor_xml_sha256"])
        self.assertIsNone(handoff["unsigned_apk_sha256"])

    def test_input_policy_excludes_other_build_outputs_and_secrets(self):
        raw = load_handoff()["raw_input_policy"]
        self.assertFalse(raw["original_inputs_are_in_git"])
        self.assertEqual(
            set(raw["forbidden_input_categories"]),
            {
                "other_rom_checkout",
                "other_rom_outputs",
                "private_patched_apk",
                "saved_decoded_tree",
                "signing_keys_from_other_build",
            },
        )
        serialized = HANDOFF_PATH.read_text(encoding="utf-8").lower().replace("\\", "/")
        self.assertNotRegex(serialized, r"[a-z]:/[^\"\s]*crdroid")
        self.assertNotIn("/home/user/android/crdroid", serialized)

    def test_er1_input_provenance_gap_is_explicit_and_matches_contract(self):
        handoff = load_handoff()
        closure = handoff["dependency_closure"]
        self.assertFalse(closure["complete"])
        self.assertFalse(closure["raw_cwk3_manifest_covers_blocked_inputs"])
        contract = json.loads((ROOT / "devices/m11q/eris-private-crypto-contract.json").read_text(encoding="utf-8"))
        unresolved = {item["input_name"]: item for item in closure["blocked_input_provenance"]}
        self.assertEqual(set(unresolved), {"libcrypto.so", "libssl.so"})
        for target in contract["targets"][:2]:
            item = unresolved[target["input_name"]]
            with self.subTest(input=target["input_name"]):
                self.assertEqual(item["input_sha256"], target["input_sha256"])
                self.assertEqual(item["elf_class"], target["elf_class"])
                self.assertEqual(item["elf_machine"], target["elf_machine"])
                self.assertEqual(item["provenance_status"], "unresolved")
                comparison = item["cwk3_stock_comparison"]
                self.assertEqual(
                    comparison["stock_image_sha256"],
                    "9136dc82d36367b09ff373af3b1adbfa75cedd1bf06f8648bf82069bc6f21b8d",
                )
                self.assertNotEqual(comparison["observed_cwk3_system_library_sha256"], target["input_sha256"])
                self.assertFalse(comparison["matches_er1_input_pin"])
        self.assertIn("Excluding ER1 changes the port payload", closure["resolution_required"])
        self.assertIn("runtime validation", closure["resolution_required"])
        manifest = (ROOT / "devices/m11q/payload-manifest.tsv").read_text(encoding="utf-8")
        self.assertNotIn("libcrypto.so", manifest)
        self.assertNotIn("libssl.so", manifest)

    def test_sms_bridge_inventory_matches_the_public_build_contract(self):
        handoff = load_handoff()
        paths = handoff["public_source_inventory"]["ims_sms_bridge_java_sources"]
        build = json.loads((ROOT / "devices/m11q/imsservice-build.json").read_text(encoding="utf-8"))
        expected = {f"bridge/java/{path}" for path in build["bridge_source"]["files"]}
        self.assertEqual(len(paths), 7)
        self.assertEqual(set(paths), expected)

    def test_declared_published_sources_and_verifiers_exist(self):
        inventory = load_handoff()["public_source_inventory"]
        paths = [
            path
            for key, values in inventory.items()
            if key != "interpretation" and isinstance(values, list)
            for path in values
        ]
        for relative in paths:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())

    def test_systemui_fix_pin_matches_the_published_patch_blob(self):
        handoff = load_handoff()["compatibility_source"]["systemui_corrective_patch"]
        patch = ROOT / handoff["path"]
        self.assertTrue(patch.is_file())
        digest = hashlib.sha256(patch.read_bytes()).hexdigest()
        self.assertEqual(handoff["sha256"], digest)
        self.assertEqual(handoff["wsl_source_commit_prefix"], "2521273")
        documented_commit = "2521273c19652476c4ee7392c4c4607ff6949c84"
        self.assertEqual(handoff["wsl_source_commit_full_sha"], documented_commit)
        evidence = ROOT / handoff["wsl_source_commit_evidence"]
        self.assertTrue(evidence.is_file())
        self.assertIn(documented_commit, evidence.read_text(encoding="utf-8"))
        actual_commit = subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "rev-parse", "66e8fa9"],
            text=True,
        ).strip()
        self.assertEqual(handoff["compatibility_repository_commit"], actual_commit)


if __name__ == "__main__":
    unittest.main()
