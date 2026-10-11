from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "replay_cherish_source_checkpoint.py"
MANIFEST = ROOT / "platform/checkpoints/cherish-20261012/manifest.json"


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True,
        check=True, env=env,
    )
    return completed.stdout.strip()


class SourceCheckpointReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.project_paths = [
            "frameworks/base", "frameworks/opt/net/ims", "frameworks/opt/telephony",
            "packages/services/Telephony", "system/netd", "packages/services/Telecomm",
            "packages/services/Mms", "hardware/qcom-caf/msm8953/audio",
            "hardware/qcom-caf/msm8953/display",
            "vendor/qcom/opensource/commonsys-intf/display", "device/cherish/sepolicy",
        ]
        self.repos = {}
        for project_path in self.project_paths:
            repo = self.source / project_path
            repo.mkdir(parents=True)
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "test@example.invalid")
            git(repo, "config", "user.name", "Checkpoint Test")
            (repo / "file.txt").write_text("before\n", encoding="utf-8")
            git(repo, "add", "file.txt")
            git(repo, "commit", "-q", "-m", "base")
            self.repos[project_path] = repo
        self.repo = self.repos["frameworks/base"]
        self.base_commit = git(self.repo, "rev-parse", "HEAD")
        self.base_commits = {
            path: git(repo, "rev-parse", "HEAD") for path, repo in self.repos.items()
        }
        self.base_tree = git(self.repo, "rev-parse", "HEAD^{tree}")
        (self.repo / "file.txt").write_text("after\n", encoding="utf-8")
        patch_result = subprocess.run(
            ["git", "-C", str(self.repo), "diff", "--binary"],
            text=False, capture_output=True, check=True,
        )
        self.patch_bytes = patch_result.stdout
        self.patch = self.root / "checkpoint" / "frameworks__base.patch"
        self.patch.parent.mkdir(parents=True)
        self.patch.write_bytes(self.patch_bytes)
        git(self.repo, "add", "file.txt")
        self.patched_tree = git(self.repo, "write-tree")
        self.index_snapshots = {}
        for repo in self.repos.values():
            index_path = repo / ".git" / "index"
            self.index_snapshots[index_path] = index_path.read_bytes()
            # These untracked files demonstrate replay leaves live worktree state alone.
            (repo / "local-note.txt").write_text("keep me\n", encoding="utf-8")
            (repo / "UntrackedProbe.java").write_text("class UntrackedProbe {}\n", encoding="utf-8")
        self.base_manifest = self.root / "checkpoint" / "base-manifest.xml"
        self.base_manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest_projects = "".join(f'<project path="{path}" />' for path in self.project_paths)
        self.base_manifest_bytes = f'<manifest revision="test-revision">{manifest_projects}</manifest>\n'.encode()
        self.base_manifest.write_bytes(self.base_manifest_bytes)

    def tearDown(self):
        self.temp.cleanup()

    def manifest_data(self, *, patch_path="frameworks__base.patch", patch_hash=None,
                      base_commit=None, patched_tree=None, changed_paths=None):
        projects = []
        # The public manifest has 11 required source projects. Fixture entries use
        # harmless no-op diffs for the other paths; execution tests below validate one project.
        paths = self.project_paths
        for path in paths:
            projects.append({
                "path": path,
                "source_url": "https://example.invalid/source",
                "manifest_revision": "test-revision",
                "base_commit": base_commit or self.base_commits[path],
                "base_tree": self.base_tree,
                "patched_tree": patched_tree or self.patched_tree,
                "patch": patch_path if path == "frameworks/base" else "frameworks__base.patch",
                "sha256": patch_hash or hashlib.sha256(self.patch_bytes).hexdigest(),
                "changed_paths": changed_paths or ["file.txt"],
                "role": "test source patch",
            })
        return {
            "format_version": 1,
            "status": "user_build_and_voice_call_validated",
            "rom_build_ran_by_agent": False,
            "user_reported_build_success": True,
            "user_reported_boot_success": True,
            "user_reported_normal_voice_call_success": True,
            "base_manifest": {
                "path": "base-manifest.xml",
                "sha256": hashlib.sha256(self.base_manifest_bytes).hexdigest(),
                "project_count": len(projects),
            },
            "projects": projects,
        }

    def invoke(self, data):
        manifest = self.root / "checkpoint" / "manifest.json"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--source-root", str(self.source),
             "--manifest", str(manifest)], text=True, capture_output=True, check=False,
        )

    def assert_live_state_unchanged(self):
        for repo in self.repos.values():
            self.assertEqual(git(repo, "rev-parse", "HEAD"), self.base_commits[repo.relative_to(self.source).as_posix()])
            expected_file = "after\n" if repo == self.repo else "before\n"
            self.assertEqual((repo / "file.txt").read_text(encoding="utf-8"), expected_file)
            self.assertEqual((repo / "local-note.txt").read_text(encoding="utf-8"), "keep me\n")
            self.assertEqual((repo / "UntrackedProbe.java").read_text(encoding="utf-8"), "class UntrackedProbe {}\n")
        for index_path, snapshot in self.index_snapshots.items():
            self.assertEqual(index_path.read_bytes(), snapshot)

    def test_replays_and_reverses_using_temporary_index(self):
        completed = self.invoke(self.manifest_data())
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len(report["projects"]), 11)
        self.assertFalse(report["live_worktree_verified"])
        self.assert_live_state_unchanged()

    def test_rejects_patch_hash_mismatch(self):
        data = self.manifest_data(patch_hash="0" * 64)
        completed = self.invoke(data)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("SHA-256 mismatch", json.loads(completed.stdout)["error"])
        self.assert_live_state_unchanged()

    def test_rejects_wrong_base_commit(self):
        data = self.manifest_data(base_commit="1" * 40)
        completed = self.invoke(data)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("base commit mismatch", json.loads(completed.stdout)["error"])
        self.assert_live_state_unchanged()

    def test_rejects_wrong_result_tree(self):
        data = self.manifest_data(patched_tree="2" * 40)
        completed = self.invoke(data)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("patched tree mismatch", json.loads(completed.stdout)["error"])
        self.assert_live_state_unchanged()

    def test_rejects_unsafe_checkpoint_path(self):
        data = self.manifest_data(patch_path="../escape.patch")
        completed = self.invoke(data)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("unsafe patch path", json.loads(completed.stdout)["error"])
        self.assert_live_state_unchanged()

    def test_rejects_changed_path_mismatch(self):
        data = self.manifest_data(changed_paths=["different.txt"])
        completed = self.invoke(data)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("changed path mismatch", json.loads(completed.stdout)["error"])
        self.assert_live_state_unchanged()

    def test_rejects_base_manifest_hash_mismatch(self):
        data = self.manifest_data()
        data["base_manifest"]["sha256"] = "0" * 64
        completed = self.invoke(data)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("base manifest SHA-256 mismatch", json.loads(completed.stdout)["error"])
        self.assert_live_state_unchanged()


@unittest.skipUnless(MANIFEST.is_file(), "public checkpoint manifest not produced yet")
class PublishedManifestCoverageTests(unittest.TestCase):
    def test_published_manifest_covers_checkpoint_projects_and_source_closure(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["format_version"], 1)
        self.assertEqual(data["status"], "user_build_and_voice_call_validated")
        self.assertFalse(data["rom_build_ran_by_agent"])
        self.assertTrue(data["user_reported_build_success"])
        self.assertTrue(data["user_reported_boot_success"])
        self.assertTrue(data["user_reported_normal_voice_call_success"])
        self.assertIn(len(data["projects"]), (13, 14))
        paths = {project["path"] for project in data["projects"]}
        required = {
            "frameworks/base", "frameworks/opt/net/ims", "frameworks/opt/telephony",
            "packages/services/Telephony", "system/netd", "packages/services/Telecomm",
            "packages/services/Mms", "hardware/qcom-caf/msm8953/audio",
            "hardware/qcom-caf/msm8953/display",
            "vendor/qcom/opensource/commonsys-intf/display", "device/cherish/sepolicy",
        }
        optional = {"device/samsung/m11q", "vendor/cherish", "build/make"}
        self.assertTrue(required.issubset(paths))
        self.assertEqual(paths - required, paths.intersection(optional))
        self.assertTrue({"device/samsung/m11q", "vendor/cherish"}.issubset(paths))
        self.assertEqual(len(paths), 11 + len(paths.intersection(optional)))
        changed = {project["path"]: set(project["changed_paths"]) for project in data["projects"]}
        framework_paths = changed["frameworks/base"]
        mms_paths = changed["packages/services/Mms"]
        self.assertTrue(any("SubscriptionInfo" in path or "TelephonyManager" in path
                            for path in framework_paths))
        self.assertEqual(mms_paths, {"src/com/android/mms/service/MmsService.java"})
        self.assertTrue({
            "mms/java/com/android/internal/telephony/IMms.aidl",
            "services/core/java/com/android/server/MmsServiceBroker.java",
        }.issubset(framework_paths), "framework Mms/IMms companion sources are missing")
        self.assertTrue(any("Telephony" in path for path in changed["packages/services/Telephony"]))
        telecom_paths = changed["packages/services/Telecomm"]
        self.assertEqual(telecom_paths, {
            "res/values/config.xml",
            "src/com/android/server/telecom/CallAudioManager.java",
            "src/com/android/server/telecom/CallAudioModeStateMachine.java",
            "src/com/android/server/telecom/SamsungImsAudioHandover.java",
            "src/com/android/server/telecom/SamsungImsAudioTransition.java",
        }, "Telecomm audio handover helpers are missing or unexpected")
        expected_build_fixes = {
            "hardware/qcom-caf/msm8953/audio": {"hal/Android.mk"},
            "hardware/qcom-caf/msm8953/display": {"gpu_tonemapper/glengine.cpp"},
            "vendor/qcom/opensource/commonsys-intf/display": {"gralloc/gralloc_priv.h"},
            "device/cherish/sepolicy": {"common/public/property.te"},
        }
        for project_path, required_paths in expected_build_fixes.items():
            self.assertTrue(required_paths.issubset(changed[project_path]),
                            f"build prerequisite missing from {project_path}")
        base_manifest = data["base_manifest"]
        self.assertEqual(base_manifest["project_count"], 1200)
        base_path = MANIFEST.parent / base_manifest["path"]
        self.assertEqual(hashlib.sha256(base_path.read_bytes()).hexdigest(), base_manifest["sha256"])
        xml_root = ET.parse(base_path).getroot()
        xml_count = sum(1 for node in xml_root.iter() if node.tag.rsplit("}", 1)[-1] == "project")
        self.assertEqual(xml_count, base_manifest["project_count"])


if __name__ == "__main__":
    unittest.main()
