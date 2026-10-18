#!/usr/bin/env python3
"""Preflight every indexed crDroid project before optionally applying source patches.

No downloads, commits, ROM builds, resets or cleanup. Successful --apply leaves
the changes staged for review. A runtime or I/O failure stops with changes intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "devices/m11q/crdroid-source-index.json"


def inside(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if not relative or "\\" in relative or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"unsafe relative path: {relative!r}")
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root.resolve()) or any(
            p.is_symlink() for p in [target, *target.parents] if p != root.parent):
        raise ValueError(f"path escapes root or uses a symlink: {relative}")
    return target


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], env=env,
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=120)
    if result.returncode:
        raise ValueError(f"{repo}: git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def clean(repo: Path) -> str:
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo.resolve():
        raise ValueError(f"not an independent project checkout: {repo}")
    if git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError(f"dirty source/index or untracked files: {repo}; preserve and review first")
    return git(repo, "rev-parse", "HEAD^{tree}")


def preflight(root: Path, entry: dict) -> dict:
    repo = inside(root, entry["path"])
    tree = clean(repo)
    steps = entry["patches"]
    expected = entry["base_tree"]
    for step in steps:
        if step["before_tree"] != expected:
            raise ValueError(f"broken tree chain: {entry['path']}")
        patch = inside(ROOT, step["path"])
        if hashlib.sha256(patch.read_bytes()).hexdigest() != step["sha256"]:
            raise ValueError(f"patch SHA-256 mismatch: {step['path']}")
        expected = step["after_tree"]
    if expected != entry["final_tree"]:
        raise ValueError(f"final tree chain mismatch: {entry['path']}")
    # A clean checkout of an earlier checkpoint can apply only the suffix.
    trees = [entry["base_tree"], *[step["after_tree"] for step in steps]]
    if tree not in trees:
        raise ValueError(f"unsupported tree in {entry['path']}: {tree}")
    remaining = steps[trees.index(tree):]
    env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="crdroid-source-preflight-") as temp:
        env["GIT_INDEX_FILE"] = str(Path(temp) / "index")
        git(repo, "read-tree", tree, env=env)
        for step in remaining:
            patch = str(inside(ROOT, step["path"]))
            git(repo, "apply", "--cached", "--binary", patch, env=env)
            actual = git(repo, "write-tree", env=env)
            if actual != step["after_tree"]:
                raise ValueError(f"result tree mismatch: {step['path']}: {actual}")
        if git(repo, "write-tree", env=env) != entry["final_tree"]:
            raise ValueError(f"preflight final tree mismatch: {entry['path']}")
    return {"path": entry["path"], "input_tree": tree,
            "final_tree": entry["final_tree"],
            "patches": [step["path"] for step in remaining], "status": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="apply after all projects pass")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    report = {"status": "FAIL", "rom_build_run": False, "projects": [], "applied": []}
    try:
        if any(os.environ.get(key) for key in ("GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE")):
            raise ValueError("unset GIT_INDEX_FILE, GIT_DIR and GIT_WORK_TREE before preflight")
        entries = json.loads(INDEX.read_text(encoding="utf-8"))["projects"]
        if not entries or len({e["path"] for e in entries}) != len(entries):
            raise ValueError("empty/duplicate project index")
        # Complete the whole batch before touching any real index or source file.
        report["projects"] = [preflight(root, entry) for entry in entries]
        if args.apply:
            for plan in report["projects"]:
                repo = inside(root, plan["path"])
                if clean(repo) != plan["input_tree"]:
                    raise ValueError(f"source changed after preflight: {plan['path']}")
                for patch in plan["patches"]:
                    git(repo, "apply", "--index", "--binary", str(inside(ROOT, patch)))
                    report["applied"].append({"project": plan["path"], "patch": patch})
                if git(repo, "write-tree") != plan["final_tree"]:
                    raise ValueError(f"applied tree mismatch: {plan['path']}")
        report["status"] = "PASS"
        report["mode"] = "apply_staged" if args.apply else "preflight_only"
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        report["error"] = str(error)
        report["recovery"] = "Preserve source and staged changes; review report. No reset or deletion was run."
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(args.report),
                      "error": report.get("error")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
