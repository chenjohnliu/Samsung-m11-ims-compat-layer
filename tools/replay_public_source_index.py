#!/usr/bin/env python3
"""Fetch fixed public source bases and replay every patch in the Cherish index.

Only Git objects are fetched. Each project uses a shallow, blob-filtered bare
repository; replay and reverse replay happen in disposable Git indexes, so no
source worktree or index is changed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlparse
from urllib.request import urlopen


def git(repo: Path, *args: str, env: dict[str, str] | None = None, timeout: int = 120) -> str:
    cmd = ["git", "--git-dir", str(repo), *args]
    try:
        result = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace",
                                capture_output=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Git command timed out after {timeout}s: {' '.join(cmd)}") from error
    if result.returncode:
        raise RuntimeError(f"{' '.join(cmd)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def project_repo(source_root: Path, project_path: str) -> Path:
    path = PurePosixPath(project_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"unsafe project path: {project_path!r}")
    if re.match(r"^[A-Za-z]:", path.parts[0]):
        raise RuntimeError(f"unsafe project path: {project_path!r}")
    result = source_root.joinpath(*path.parts).resolve()
    if not result.is_relative_to(source_root.resolve()):
        raise RuntimeError(f"project path escapes source root: {project_path!r}")
    return result


def checked_file(root: Path, value: str, label: str) -> Path:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeError(f"unsafe {label}: {value!r}")
    if re.match(r"^[A-Za-z]:", path.parts[0]):
        raise RuntimeError(f"unsafe {label}: {value!r}")
    result = root.joinpath(*path.parts).resolve()
    if not result.is_relative_to(root.resolve()):
        raise RuntimeError(f"{label} escapes repository root: {value!r}")
    return result


def patch_source_paths(patch: Path) -> list[str]:
    paths = []
    for line in patch.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("--- "):
            continue
        value = line[4:].split("\t", 1)[0]
        if value == "/dev/null":
            continue
        if value.startswith("a/"):
            value = value[2:]
        elif value.startswith('"'):
            raise RuntimeError(f"quoted patch path needs manual handling: {value}")
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"unsafe patch source path: {value!r}")
        paths.append(value)
    return list(dict.fromkeys(paths))


def tree_blob(repo: Path, tree: str, path: str) -> str | None:
    result = subprocess.run(["git", "--git-dir", str(repo), "ls-tree", "-z", tree, "--", path],
                            capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"cannot inspect {path} in tree {tree}: {result.stderr.decode(errors='replace').strip()}")
    if not result.stdout:
        return None
    record = result.stdout.split(b"\0", 1)[0]
    metadata = record.split(b"\t", 1)[0].split()
    if len(metadata) != 3 or metadata[1] != b"blob":
        return None
    return metadata[2].decode("ascii")


def fetch_public_blob(source_url: str, commit: str, path: str) -> bytes:
    parsed = urlparse(source_url)
    if parsed.hostname == "github.com":
        parts = parsed.path.strip("/").removesuffix(".git").split("/")
        if len(parts) != 2:
            raise RuntimeError(f"cannot form raw public URL from {source_url}")
        url = f"https://raw.githubusercontent.com/{parts[0]}/{parts[1]}/{commit}/{quote(path, safe='/')}"
        is_gitiles = False
    elif parsed.hostname == "android.googlesource.com":
        url = f"{source_url.rstrip('/')}/+/{commit}/{quote(path, safe='/')}?format=TEXT"
        is_gitiles = True
    else:
        raise RuntimeError(f"unsupported public source host for blob fallback: {source_url}")
    try:
        with urlopen(url, timeout=30) as response:
            data = response.read(64 * 1024 * 1024 + 1)
    except Exception as error:
        raise RuntimeError(f"public source blob retrieval failed for {path} at {commit}: {error}") from error
    if len(data) > 64 * 1024 * 1024:
        raise RuntimeError(f"public source blob exceeds 64 MiB safety limit: {path}")
    if is_gitiles:
        try:
            data = base64.b64decode(data.strip(), validate=True)
        except ValueError as error:
            raise RuntimeError(f"invalid Gitiles base64 response for {path}") from error
    return data


def ensure_patch_blobs(repo: Path, source_url: str, base_commit: str,
                       current_tree: str, patch: Path, paths: list[str]) -> None:
    base_tree = git(repo, "rev-parse", f"{base_commit}^{{tree}}")
    env = os.environ.copy()
    env["GIT_NO_LAZY_FETCH"] = "1"
    for path in paths:
        oid = tree_blob(repo, current_tree, path)
        if oid is None:
            continue
        present = subprocess.run(["git", "--git-dir", str(repo), "cat-file", "-e", oid],
                                 env=env, capture_output=True, timeout=30)
        if present.returncode == 0:
            continue
        base_oid = tree_blob(repo, base_tree, path)
        if base_oid != oid:
            raise RuntimeError(f"missing patch input blob is not present at fixed base: {path} ({oid})")
        data = fetch_public_blob(source_url, base_commit, path)
        header = f"blob {len(data)}\0".encode("ascii")
        object_hash = hashlib.sha1(header + data).hexdigest()
        if object_hash != oid:
            raise RuntimeError(f"raw public bytes do not match fixed base tree for {path}: expected={oid} actual={object_hash}")
        written = subprocess.run(["git", "--git-dir", str(repo), "hash-object", "-w", "--stdin"],
                                 input=data, capture_output=True, timeout=120)
        if written.returncode or written.stdout.decode("ascii", errors="replace").strip() != oid:
            raise RuntimeError(f"could not install verified public blob {oid} for {path}")


def replay_project(root: Path, source_root: Path, entry: dict, discover_trees: bool = False) -> dict:
    name = entry["path"]
    if not discover_trees:
        if not entry.get("base_tree") or not entry.get("final_tree"):
            raise RuntimeError(f"{name}: strict replay requires pinned base_tree and final_tree")
        if any(not p.get("before_tree") or not p.get("after_tree") for p in entry["patches"]):
            raise RuntimeError(f"{name}: strict replay requires before_tree and after_tree for every patch")
    repo = project_repo(source_root, name)
    repo.parent.mkdir(parents=True, exist_ok=True)
    repo.mkdir(exist_ok=True)
    is_bare = subprocess.run(["git", "--git-dir", str(repo), "rev-parse", "--is-bare-repository"],
                             text=True, capture_output=True)
    expected_remote = entry["source_url"].removesuffix(".git") + ".git"
    if is_bare.returncode != 0 or is_bare.stdout.strip() != "true":
        if any(repo.iterdir()):
            raise RuntimeError(f"refusing non-empty, non-bare source destination: {repo}")
        subprocess.run(["git", "init", "--bare", str(repo)], check=True, capture_output=True)
        git(repo, "remote", "add", "origin", expected_remote)
    elif git(repo, "remote", "get-url", "origin") != expected_remote:
        raise RuntimeError(f"source destination has unexpected origin: {repo}")
    no_lazy = os.environ.copy()
    no_lazy["GIT_NO_LAZY_FETCH"] = "1"
    local_base = subprocess.run(["git", "--git-dir", str(repo), "cat-file", "-e",
                                 f"{entry['base_commit']}^{{commit}}"],
                                env=no_lazy, capture_output=True, timeout=30)
    if local_base.returncode != 0:
        git(repo, "fetch", "--filter=blob:none", "--no-tags", "--depth=1", "origin", entry["base_commit"])
    base = git(repo, "rev-parse", f"{entry['base_commit']}^{{commit}}")
    if base != entry["base_commit"]:
        raise RuntimeError(f"{name}: fetched base commit differs: {base}")
    base_tree = git(repo, "rev-parse", f"{base}^{{tree}}")
    if entry.get("base_tree") and base_tree != entry["base_tree"]:
        raise RuntimeError(f"{name}: base tree mismatch expected={entry['base_tree']} actual={base_tree}")

    steps = entry["patches"]
    if not steps:
        if not discover_trees and entry.get("final_tree") != base_tree:
            raise RuntimeError(f"{name}: no-patch final tree must equal pinned base tree {base_tree}")
        return {"path": name, "source_url": entry["source_url"], "base_commit": base,
                "base_tree": base_tree, "final_tree": base_tree,
                "expected_final_tree": entry.get("final_tree") or None,
                "patches": [], "reverse_tree": base_tree,
                "verification_note": "No patches; final source tree is the pinned commit tree.",
                "status": "DISCOVERED" if discover_trees else "PASS"}
    with tempfile.TemporaryDirectory(prefix="public-index-replay-", dir=source_root) as tmp:
        index = Path(tmp) / "index"
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(index)
        # Some upstream trees contain names Windows rejects as NTFS paths.
        # This is confined to the temporary index; no worktree is materialized.
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "core.protectNTFS"
        env["GIT_CONFIG_VALUE_0"] = "false"
        git(repo, "read-tree", base, env=env)
        outcomes = []
        for position, step in enumerate(steps, 1):
            patch = checked_file(root, step["path"], "patch path")
            if not patch.is_file():
                raise RuntimeError(f"{name}: missing patch {step['path']}")
            actual_digest = sha256(patch)
            if actual_digest != step["sha256"]:
                raise RuntimeError(f"{name}: patch hash mismatch {step['path']}")
            before = git(repo, "write-tree", "--missing-ok", env=env)
            if not discover_trees and before != step["before_tree"]:
                raise RuntimeError(f"{name} step {position}: before tree mismatch expected={step['before_tree']} actual={before}")
            ensure_patch_blobs(repo, entry["source_url"], base, before, patch,
                               patch_source_paths(patch))
            patch_abs = str(patch.resolve())
            git(repo, "apply", "--cached", "--check", "--binary", patch_abs, env=env)
            git(repo, "apply", "--cached", "--binary", patch_abs, env=env)
            after = git(repo, "write-tree", "--missing-ok", env=env)
            if not discover_trees and after != step["after_tree"]:
                raise RuntimeError(f"{name} step {position}: after tree mismatch expected={step['after_tree']} actual={after}")
            outcomes.append({"patch": step["path"], "sha256": actual_digest,
                             "before_tree": before, "after_tree": after})
        final_tree = git(repo, "write-tree", "--missing-ok", env=env)
        if not discover_trees and final_tree != entry["final_tree"]:
            raise RuntimeError(f"{name}: final tree mismatch expected={entry['final_tree']} actual={final_tree}")
        for step in reversed(steps):
            git(repo, "apply", "--cached", "--reverse", "--binary",
                str(checked_file(root, step["path"], "patch path")), env=env)
        reversed_tree = git(repo, "write-tree", "--missing-ok", env=env)
        if reversed_tree != base_tree:
            raise RuntimeError(f"{name}: reverse replay mismatch expected={base_tree} actual={reversed_tree}")
    return {"path": name, "source_url": entry["source_url"], "base_commit": base,
            "base_tree": base_tree, "final_tree": final_tree,
            "expected_final_tree": entry["final_tree"], "patches": outcomes,
            "reverse_tree": reversed_tree, "status": "DISCOVERED" if discover_trees else "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--index", type=Path, default=Path("devices/m11q/cherish-source-index.json"),
                        help="index file relative to --repo-root, or an absolute path")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--discover-trees", action="store_true",
                        help="compute replay tree hashes without asserting expected hashes; report status DISCOVERED")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    source_root = args.source_root.resolve()
    autocrlf = subprocess.run(["git", "-C", str(root), "config", "--get", "core.autocrlf"],
                              text=True, capture_output=True)
    if autocrlf.returncode == 0 and autocrlf.stdout.strip().lower() == "true":
        raise RuntimeError("core.autocrlf=true can rewrite patch bytes; set it to false and refresh tracked files before replay")
    index_arg = args.index
    index_path = index_arg.resolve() if index_arg.is_absolute() else (root / index_arg).resolve()
    if not index_path.is_relative_to(root):
        raise RuntimeError("index path must be inside --repo-root")
    if not source_root.is_relative_to(root):
        raise RuntimeError("source-root must be inside the isolated public audit clone")
    rel_source_root = source_root.relative_to(root)
    ignore_check = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--no-index", str(rel_source_root)],
                                  capture_output=True)
    if ignore_check.returncode != 0:
        raise RuntimeError("source-root must be ignored by this clone's .git/info/exclude before fetches begin")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    entries = index.get("projects")
    if not isinstance(entries, list) or not entries or len({item.get("path") for item in entries}) != len(entries):
        raise RuntimeError("source index must contain unique project entries")
    report_path = checked_file(root, str(args.report), "report path") if not args.report.is_absolute() else args.report.resolve()
    if not report_path.is_relative_to(root):
        raise RuntimeError("report path must be inside --repo-root")
    report = {"status": "RUNNING", "source_index": str(index_path),
              "source_root": str(source_root),
              "verification": "public fixed base fetch; full base/final/reverse tree hashes in temporary indexes",
              "verification_mode": "DISCOVER_TREES" if args.discover_trees else "STRICT",
              "rom_build_run": False, "projects": []}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for entry in entries:
        report["in_progress"] = entry.get("path")
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        try:
            if not args.discover_trees:
                if not entry.get("base_tree") or not entry.get("final_tree"):
                    raise RuntimeError(f"{entry.get('path')}: strict replay requires pinned base_tree and final_tree")
                if any(not p.get("before_tree") or not p.get("after_tree") for p in entry["patches"]):
                    raise RuntimeError(f"{entry.get('path')}: strict replay requires before_tree and after_tree for every patch")
            report["projects"].append(replay_project(root, source_root, entry, args.discover_trees))
        except Exception as error:
            report["projects"].append({"path": entry.get("path"), "status": "FAIL", "error": str(error)})
            report.update(status="FAIL", error=str(error), projects_verified=len(report["projects"]) - 1)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            raise
        report["projects_verified"] = len(report["projects"])
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report.pop("in_progress", None)
    report.update(status="DISCOVERED" if args.discover_trees else "PASS",
                  projects_verified=len(report["projects"]))
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "projects_verified": report["projects_verified"],
                      "report": str(args.report.resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, indent=2))
        raise SystemExit(1)
