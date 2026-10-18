"""Offline integrity tests for public source-index replay."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]

from tools import replay_public_source_index as replay


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", "--git-dir", str(repo), *args], env=env, check=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout.strip()


def work_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


class PublicSourceIndexReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=REPO_ROOT)
        self.root = Path(self.temp.name)
        self.source_root = self.root / "out" / "source"
        self.bare = self.source_root / "sample-project"
        self.bare.parent.mkdir(parents=True)
        self.source_url = "https://github.com/example/sample-project.git"
        self.work = self.root / "working-copy"
        self.work.mkdir()
        work_git(self.work, "init", "-q")
        work_git(self.work, "config", "core.autocrlf", "false")
        work_git(self.work, "config", "user.email", "replay-test@example.invalid")
        work_git(self.work, "config", "user.name", "Replay Test")
        (self.work / "base.txt").write_bytes(b"base content\n")
        work_git(self.work, "add", "base.txt")
        work_git(self.work, "commit", "-q", "-m", "fixed base")
        self.base_tree = work_git(self.work, "rev-parse", "HEAD^{tree}")

        subprocess.run(["git", "init", "--bare", str(self.bare)], check=True,
                       capture_output=True, text=True)
        base_blob = subprocess.run(
            ["git", "--git-dir", str(self.bare), "hash-object", "-w", "--stdin"],
            input=b"base content\n", check=True, capture_output=True,
        ).stdout.decode("ascii").strip()
        tree_input = f"100644 blob {base_blob}\tbase.txt\n".encode("ascii")
        bare_tree = subprocess.run(
            ["git", "--git-dir", str(self.bare), "mktree"], input=tree_input,
            check=True, capture_output=True,
        ).stdout.decode("ascii").strip()
        self.assertEqual(bare_tree, self.base_tree)
        commit_env = {
            "GIT_AUTHOR_NAME": "Replay Test", "GIT_AUTHOR_EMAIL": "replay-test@example.invalid",
            "GIT_COMMITTER_NAME": "Replay Test", "GIT_COMMITTER_EMAIL": "replay-test@example.invalid",
        }
        self.base_commit = subprocess.run(
            ["git", "--git-dir", str(self.bare), "commit-tree", bare_tree, "-m", "fixed base"],
            env=commit_env, check=True, capture_output=True,
        ).stdout.decode("ascii").strip()
        git(self.bare, "update-ref", "refs/heads/main", self.base_commit)
        git(self.bare, "remote", "add", "origin", self.source_url)

        patch_root = self.root / "patches"
        patch_root.mkdir()
        steps = []
        for number in (1, 2):
            if number == 1:
                (self.work / "base.txt").write_bytes(b"first patch\n")
            else:
                (self.work / "new.txt").write_bytes(b"second patch\n")
            work_git(self.work, "add", "-A")
            patch_bytes = subprocess.run(
                ["git", "-C", str(self.work), "diff", "--cached", "--binary", "HEAD", "--"],
                check=True, capture_output=True,
            ).stdout
            relative = f"patches/step-{number}.patch"
            (self.root / relative).write_bytes(patch_bytes)
            after_tree = work_git(self.work, "write-tree")
            steps.append({
                "path": relative,
                "sha256": hashlib.sha256(patch_bytes).hexdigest(),
                "before_tree": self.base_tree if number == 1 else steps[-1]["after_tree"],
                "after_tree": after_tree,
            })
            work_git(self.work, "commit", "-q", "-m", f"patch {number}")

        self.entry = {
            "path": "sample-project",
            "source_url": self.source_url,
            "base_commit": self.base_commit,
            "base_tree": self.base_tree,
            "final_tree": steps[-1]["after_tree"],
            "patches": steps,
        }
        self.patches = patch_root

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_project(self, entry: dict) -> dict:
        with mock.patch.object(replay.tempfile, "tempdir", str(self.root)):
            return replay.replay_project(self.root, self.source_root, entry)

    def test_replays_pinned_chain_and_reverse_matches_fixed_base(self) -> None:
        result = self.run_project(copy.deepcopy(self.entry))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["base_tree"], self.entry["base_tree"])
        self.assertEqual(result["final_tree"], self.entry["final_tree"])
        self.assertEqual(result["reverse_tree"], self.entry["base_tree"])
        self.assertEqual(len(result["patches"]), 2)
        self.assertEqual(git(self.bare, "rev-parse", "refs/heads/main^{tree}"), self.entry["base_tree"])

    def test_incorrect_expected_final_tree_is_rejected(self) -> None:
        entry = copy.deepcopy(self.entry)
        entry["final_tree"] = "0" * 40
        with self.assertRaisesRegex(RuntimeError, "final tree mismatch"):
            self.run_project(entry)

    def test_missing_or_null_tree_pins_are_rejected_in_strict_mode(self) -> None:
        mutations = (
            ("base_tree", None), ("base_tree", "__missing__"),
            ("final_tree", None), ("final_tree", "__missing__"),
            ("before_tree", None), ("before_tree", "__missing__"),
            ("after_tree", None), ("after_tree", "__missing__"),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                entry = copy.deepcopy(self.entry)
                if field in {"base_tree", "final_tree"}:
                    if value == "__missing__":
                        entry.pop(field)
                    else:
                        entry[field] = value
                else:
                    if value == "__missing__":
                        entry["patches"][0].pop(field)
                    else:
                        entry["patches"][0][field] = value
                with self.assertRaises((RuntimeError, KeyError)):
                    self.run_project(entry)

    def test_unsafe_project_and_patch_paths_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unsafe project path"):
            replay.project_repo(self.source_root, "../outside")
        for value in ("../outside.patch", r"patches\..\outside.patch", "/outside.patch"):
            with self.subTest(path=value):
                with self.assertRaisesRegex(RuntimeError, "unsafe patch path"):
                    replay.checked_file(self.root, value, "patch path")

    def test_missing_base_blob_is_fetched_only_when_raw_bytes_match_pinned_oid(self) -> None:
        blob_oid = replay.tree_blob(self.bare, self.entry["base_tree"], "base.txt")
        self.assertIsNotNone(blob_oid)
        object_path = self.bare / "objects" / blob_oid[:2] / blob_oid[2:]
        self.assertTrue(object_path.is_file(), "fixture commit should keep the base blob available")

        original_run = subprocess.run

        def report_missing_blob(args, *positional, **keywords):
            command = [str(part) for part in args]
            if command[-3:] == ["cat-file", "-e", blob_oid]:
                return subprocess.CompletedProcess(args, 1, b"", b"fixture reports blob missing")
            return original_run(args, *positional, **keywords)

        with mock.patch.object(replay.subprocess, "run", side_effect=report_missing_blob), \
                mock.patch.object(replay, "fetch_public_blob", return_value=b"base content\n") as fetch:
            result = self.run_project(copy.deepcopy(self.entry))
        self.assertEqual(result["status"], "PASS")
        fetch.assert_called_once_with(self.source_url, self.base_commit, "base.txt")

        with mock.patch.object(replay.subprocess, "run", side_effect=report_missing_blob), \
                mock.patch.object(replay, "fetch_public_blob", return_value=b"wrong bytes\n") as fetch:
            with self.assertRaisesRegex(RuntimeError, "raw public bytes do not match fixed base tree"):
                self.run_project(copy.deepcopy(self.entry))
        fetch.assert_called_once_with(self.source_url, self.base_commit, "base.txt")


if __name__ == "__main__":
    unittest.main()
