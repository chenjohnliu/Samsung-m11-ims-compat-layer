"""Safety and staging checks for the crDroid source-index applier."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import apply_crdroid_source_index as apply_index


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], env=env, check=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout.strip()


class ApplyCrDroidSourceIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=REPO_ROOT)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.patch_root = self.root / "index-root"
        self.patch_root.mkdir()
        self.index_path = self.root / "source-index.json"
        self.report_path = self.root / "report.json"
        self.projects: list[dict] = []
        self.repos: dict[str, Path] = {}
        self.index_snapshots: dict[Path, bytes] = {}
        self._add_project("project-one")
        self._add_project("project-two")
        self._write_index()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _add_project(self, name: str, *, patch_count: int = 2) -> dict:
        repo = self.source / name
        repo.mkdir(parents=True)
        git(repo, "init", "-q")
        git(repo, "config", "core.autocrlf", "false")
        git(repo, "config", "user.email", "index-test@example.invalid")
        git(repo, "config", "user.name", "Source Index Test")
        (repo / "base.txt").write_text("base\n", encoding="utf-8", newline="\n")
        git(repo, "add", "base.txt")
        git(repo, "commit", "-q", "-m", "base")
        base_commit = git(repo, "rev-parse", "HEAD")
        base_tree = git(repo, "rev-parse", "HEAD^{tree}")
        steps = []

        for number in range(1, patch_count + 1):
            if number == 1:
                (repo / "base.txt").write_text("first patch\n", encoding="utf-8", newline="\n")
            else:
                (repo / f"added-{number}.txt").write_text(
                    f"patch {number}\n", encoding="utf-8", newline="\n"
                )
            git(repo, "add", "-A")
            patch_bytes = subprocess.run(
                ["git", "-C", str(repo), "diff", "--cached", "--binary", "HEAD", "--"],
                check=True, capture_output=True,
            ).stdout
            relative_patch = f"patches/{name}-{number}.patch"
            patch_path = self.patch_root / relative_patch
            patch_path.parent.mkdir(parents=True, exist_ok=True)
            patch_path.write_bytes(patch_bytes)
            after_tree = git(repo, "write-tree")
            git(repo, "commit", "-q", "-m", f"patch {number}")
            steps.append({
                "path": relative_patch,
                "sha256": hashlib.sha256(patch_bytes).hexdigest(),
                "before_tree": base_tree if number == 1 else steps[-1]["after_tree"],
                "after_tree": after_tree,
            })

        final_tree = steps[-1]["after_tree"]
        git(repo, "reset", "--hard", base_commit)
        self.repos[name] = repo
        self.index_snapshots[repo / ".git" / "index"] = (repo / ".git" / "index").read_bytes()
        entry = {
            "path": name,
            "base_tree": base_tree,
            "final_tree": final_tree,
            "patches": steps,
        }
        self.projects.append(entry)
        return entry

    def _write_index(self) -> None:
        self.index_path.write_text(json.dumps({"projects": self.projects}, indent=2), encoding="utf-8")

    def invoke(self, *, apply: bool = False) -> tuple[int, dict]:
        argv = ["apply_crdroid_source_index.py", "--source-root", str(self.source),
                "--report", str(self.report_path)]
        if apply:
            argv.append("--apply")
        with mock.patch.object(apply_index, "ROOT", self.patch_root), \
                mock.patch.object(apply_index, "INDEX", self.index_path), \
                mock.patch.object(apply_index.tempfile, "tempdir", str(self.root)), \
                mock.patch.object(sys, "argv", argv):
            result = apply_index.main()
        return result, json.loads(self.report_path.read_text(encoding="utf-8"))

    def assert_original_state_unchanged(self) -> None:
        for name, repo in self.repos.items():
            with self.subTest(project=name):
                self.assertEqual(git(repo, "status", "--porcelain", "--untracked-files=all"), "")
                self.assertEqual(git(repo, "rev-parse", "HEAD^{tree}"),
                                 next(p for p in self.projects if p["path"] == name)["base_tree"])
                self.assertEqual((repo / "base.txt").read_text(encoding="utf-8"), "base\n")
        for index_path, snapshot in self.index_snapshots.items():
            self.assertEqual(index_path.read_bytes(), snapshot)

    def test_read_only_preflight_preserves_worktrees_and_indexes(self) -> None:
        code, report = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["mode"], "preflight_only")
        self.assertEqual(len(report["projects"]), 2)
        self.assert_original_state_unchanged()

    def test_apply_stages_both_projects_at_exact_final_trees(self) -> None:
        code, report = self.invoke(apply=True)
        self.assertEqual(code, 0)
        self.assertEqual(report["mode"], "apply_staged")
        self.assertEqual(len(report["applied"]), 4)
        for entry in self.projects:
            repo = self.repos[entry["path"]]
            self.assertEqual(git(repo, "write-tree"), entry["final_tree"])
            statuses = git(repo, "status", "--porcelain").splitlines()
            self.assertTrue(statuses)
            self.assertTrue(all(line[1:2] == " " and line[0:1] in {"A", "M"}
                                for line in statuses), statuses)

    def test_accepts_clean_checkout_at_recorded_intermediate_tree(self) -> None:
        entry = self.projects[0]
        repo = self.repos[entry["path"]]
        first = entry["patches"][0]
        git(repo, "apply", "--index", "--binary", str(self.patch_root / first["path"]))
        git(repo, "commit", "-q", "-m", "recorded intermediate")
        intermediate_index = (repo / ".git" / "index").read_bytes()
        code, report = self.invoke()
        self.assertEqual(code, 0, report.get("error"))
        plan = next(p for p in report["projects"] if p["path"] == entry["path"])
        self.assertEqual(plan["input_tree"], first["after_tree"])
        self.assertEqual(plan["patches"], [entry["patches"][1]["path"]])
        self.assertEqual((repo / ".git" / "index").read_bytes(), intermediate_index)

    def test_wrong_second_project_tree_refuses_before_first_mutation(self) -> None:
        self.projects[1]["patches"][1]["after_tree"] = "a" * 40
        self.projects[1]["final_tree"] = "a" * 40
        self._write_index()
        code, report = self.invoke(apply=True)
        self.assertEqual(code, 1)
        self.assertIn("result tree mismatch", report["error"])
        self.assert_original_state_unchanged()

    def test_tampered_patch_hash_is_rejected_without_mutation(self) -> None:
        self.projects[0]["patches"][0]["sha256"] = "0" * 64
        self._write_index()
        code, report = self.invoke(apply=True)
        self.assertEqual(code, 1)
        self.assertIn("patch SHA-256 mismatch", report["error"])
        self.assert_original_state_unchanged()

    def test_unsafe_project_and_patch_paths_are_rejected(self) -> None:
        for field, value in (("project", "../outside"), ("patch", "../outside.patch")):
            with self.subTest(field=field):
                if field == "project":
                    self.projects[0]["path"] = value
                else:
                    self.projects[0]["patches"][0]["path"] = value
                self._write_index()
                code, report = self.invoke(apply=True)
                self.assertEqual(code, 1)
                self.assertIn("unsafe relative path", report["error"])
                if field == "project":
                    self.projects[0]["path"] = "project-one"
                else:
                    self.projects[0]["patches"][0]["path"] = "patches/project-one-1.patch"
                self._write_index()
                self.assert_original_state_unchanged()


if __name__ == "__main__":
    unittest.main()
