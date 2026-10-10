#!/usr/bin/env python3
"""Publish upstream-only IMS commits as reproducible, tree-verified patch series.

Does not build Android, alter source worktrees, or push upstream repositories.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


FIRST_COMMITS = {
    "frameworks/base": "8f1bd8bc5969308e261f1ad2a8d55a8c0f0fa503",
    "frameworks/opt/net/ims": "f4c719f119848dbfeeca2c214cedd13cb4fd076a",
    "frameworks/opt/telephony": "2832747fc1e92bc34ae740b6f09957620d23d715",
    "packages/services/Telephony": "04cde10d1966ba35d1fb8fc2193867283465c487",
    "system/netd": "91016fbe38db8c2bc08f7476c173648a5124c526",
}


def git(repo, *args, env=None):
    return subprocess.check_output(["git", "-C", str(repo), *args], env=env).decode().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--android-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {"format": 1, "rom_build_run": False, "repositories": []}
    for relative, first in FIRST_COMMITS.items():
        repo = args.android_root / relative
        if git(repo, "status", "--porcelain"):
            raise RuntimeError(f"Refusing dirty repository: {relative}")
        base = git(repo, "rev-parse", first + "^")
        head = git(repo, "rev-parse", "HEAD")
        commits = git(repo, "rev-list", "--reverse", f"{base}..{head}").splitlines()
        if not commits or commits[0] != first:
            raise RuntimeError(f"Unexpected checkpoint ancestry: {relative}")
        if git(repo, "rev-list", "--merges", f"{base}..{head}"):
            raise RuntimeError(f"Merge commits are not supported: {relative}")
        destination = args.output / relative.replace("/", "__")
        destination.mkdir()
        patches = git(repo, "format-patch", "--binary", "--full-index", "--no-signature",
                      "--output-directory", str(destination), f"{base}..{head}").splitlines()
        with tempfile.TemporaryDirectory(prefix="ims-patch-index-") as temporary:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
            git(repo, "read-tree", base, env=env)
            for patch in patches:
                git(repo, "apply", "--cached", "--whitespace=error", patch, env=env)
            replay_tree = git(repo, "write-tree", env=env)
        expected_tree = git(repo, "rev-parse", "HEAD^{tree}")
        if replay_tree != expected_tree:
            raise RuntimeError(f"Patch replay tree mismatch: {relative}")
        manifest["repositories"].append({
            "path": relative, "base_commit": base, "head_commit": head,
            "head_tree": expected_tree, "replay_tree_verified": True,
            "commits": commits,
            "patches": [{"path": str(Path(p).relative_to(args.output)),
                         "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
                        for p in patches],
        })
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "repositories": len(FIRST_COMMITS),
                      "patches": sum(len(r["patches"]) for r in manifest["repositories"]),
                      "replay_tree_verified": True, "rom_build_run": False}))


if __name__ == "__main__":
    main()
