#!/usr/bin/env python3
"""Read-only verification of a public Cherish source checkpoint patch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any
import xml.etree.ElementTree as ET


DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "platform/checkpoints/cherish-20261012/manifest.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
EXPECTED_PROJECTS = {
    "frameworks/base",
    "frameworks/opt/net/ims",
    "frameworks/opt/telephony",
    "packages/services/Telephony",
    "system/netd",
    "packages/services/Telecomm",
    "packages/services/Mms",
    "hardware/qcom-caf/msm8953/audio",
    "hardware/qcom-caf/msm8953/display",
    "vendor/qcom/opensource/commonsys-intf/display",
    "device/cherish/sepolicy",
}
CHECKPOINT_ADDITIONS = {"device/samsung/m11q", "vendor/cherish", "build/make"}


class CheckpointError(Exception):
    pass


def run_git(source_root: Path, args: list[str], env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            env=env,
        )
    except OSError as error:
        raise CheckpointError(f"cannot run git: {error}") from error
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise CheckpointError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def safe_relative(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise CheckpointError(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CheckpointError(f"unsafe {label}: {value!r}")
    if path.parts and re.match(r"^[A-Za-z]:", path.parts[0]):
        raise CheckpointError(f"unsafe {label}: {value!r}")
    return path


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckpointError(f"cannot read manifest {path}: {error}") from error
    if not isinstance(data, dict) or data.get("format_version") != 1:
        raise CheckpointError("manifest format_version must be 1")
    if data.get("status") != "user_build_and_voice_call_validated":
        raise CheckpointError("manifest status must record the user's successful build, boot, and voice-call validation")
    if data.get("rom_build_ran_by_agent") is not False:
        raise CheckpointError("manifest must state that the agent did not run a ROM build")
    for key in ("user_reported_build_success", "user_reported_boot_success", "user_reported_normal_voice_call_success"):
        if data.get(key) is not True:
            raise CheckpointError(f"manifest must record {key}=true")
    base_manifest = data.get("base_manifest")
    if not isinstance(base_manifest, dict):
        raise CheckpointError("manifest base_manifest must be an object")
    for key in ("path", "sha256"):
        if not isinstance(base_manifest.get(key), str) or not base_manifest[key]:
            raise CheckpointError(f"base_manifest is missing {key}")
    base_path = safe_relative(base_manifest["path"], "base manifest path")
    if not SHA256.fullmatch(base_manifest["sha256"]):
        raise CheckpointError("base_manifest has invalid SHA-256")
    project_count = base_manifest.get("project_count")
    if not isinstance(project_count, int) or isinstance(project_count, bool) or project_count <= 0:
        raise CheckpointError("base_manifest project_count must be a positive integer")
    projects = data.get("projects")
    if not isinstance(projects, list) or not projects:
        raise CheckpointError("manifest projects must be a non-empty array")
    seen: set[str] = set()
    for project in projects:
        if not isinstance(project, dict):
            raise CheckpointError("each project entry must be an object")
        project_path = str(safe_relative(project.get("path"), "project path"))
        if project_path in seen:
            raise CheckpointError(f"duplicate project path: {project_path}")
        seen.add(project_path)
        for key in ("source_url", "manifest_revision", "base_commit", "base_tree", "patched_tree", "patch", "sha256", "role"):
            if not isinstance(project.get(key), str) or not project[key]:
                raise CheckpointError(f"project {project_path} is missing {key}")
        if not SHA256.fullmatch(project["sha256"]):
            raise CheckpointError(f"project {project_path} has invalid patch SHA-256")
        if not OBJECT_ID.fullmatch(project["base_commit"]):
            raise CheckpointError(f"project {project_path} has invalid base commit object id")
        if not OBJECT_ID.fullmatch(project["base_tree"]) or not OBJECT_ID.fullmatch(project["patched_tree"]):
            raise CheckpointError(f"project {project_path} has invalid tree object id")
        if not isinstance(project.get("changed_paths"), list) or not project["changed_paths"]:
            raise CheckpointError(f"project {project_path} changed_paths must be a non-empty array")
        normalized = [str(safe_relative(path, "changed path")) for path in project["changed_paths"]]
        if len(set(normalized)) != len(normalized):
            raise CheckpointError(f"project {project_path} has duplicate changed paths")
        project["_changed_paths"] = sorted(normalized)
        project["_patch_path"] = safe_relative(project["patch"], "patch path")
    allowed = EXPECTED_PROJECTS | CHECKPOINT_ADDITIONS
    if not EXPECTED_PROJECTS.issubset(seen):
        missing = sorted(EXPECTED_PROJECTS - seen)
        raise CheckpointError(f"manifest must cover all 11 required source projects (missing={missing})")
    unexpected = sorted(seen - allowed)
    if unexpected:
        raise CheckpointError(f"manifest contains unexpected project paths: {unexpected}")
    base_path_abs = (path.resolve().parent / Path(*base_path.parts)).resolve()
    if not base_path_abs.is_relative_to(path.resolve().parent) or not base_path_abs.is_file():
        raise CheckpointError(f"base manifest is missing or escapes checkpoint root: {base_manifest['path']}")
    base_digest = hashlib.sha256(base_path_abs.read_bytes()).hexdigest()
    if base_digest != base_manifest["sha256"]:
        raise CheckpointError(f"base manifest SHA-256 mismatch: expected={base_manifest['sha256']} actual={base_digest}")
    try:
        xml_root = ET.parse(base_path_abs).getroot()
    except ET.ParseError as error:
        raise CheckpointError(f"base manifest is not valid XML: {error}") from error
    xml_project_count = sum(1 for node in xml_root.iter() if node.tag.rsplit("}", 1)[-1] == "project")
    if xml_project_count != project_count:
        raise CheckpointError(f"base manifest XML project count mismatch: expected={project_count} actual={xml_project_count}")
    return data


def verify_project(source_root: Path, manifest_dir: Path, project: dict[str, Any]) -> dict[str, Any]:
    name = project["path"]
    repo = (source_root / Path(*PurePosixPath(name).parts)).resolve()
    root = source_root.resolve()
    if not repo.is_relative_to(root) or not repo.is_dir():
        raise CheckpointError(f"project repository is missing or outside source root: {name}")
    patch_path = (manifest_dir / Path(*project["_patch_path"].parts)).resolve()
    if not patch_path.is_relative_to(manifest_dir.resolve()) or not patch_path.is_file():
        raise CheckpointError(f"checkpoint patch is missing or escapes checkpoint root: {project['patch']}")
    patch_digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    if patch_digest != project["sha256"]:
        raise CheckpointError(f"patch SHA-256 mismatch for {name}: expected={project['sha256']} actual={patch_digest}")

    head = run_git(repo, ["rev-parse", "HEAD"])
    if head != project["base_commit"]:
        raise CheckpointError(f"base commit mismatch for {name}: expected={project['base_commit']} actual={head}")
    base_tree = run_git(repo, ["rev-parse", "HEAD^{tree}"])
    if base_tree != project["base_tree"]:
        raise CheckpointError(f"base tree mismatch for {name}: expected={project['base_tree']} actual={base_tree}")

    with tempfile.TemporaryDirectory(prefix=".cherish-checkpoint-index-", dir=manifest_dir) as temp_dir:
        temp_index = Path(temp_dir) / "index"
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(temp_index)
        run_git(repo, ["read-tree", "HEAD"], env)
        run_git(repo, ["apply", "--cached", "--check", str(patch_path)], env)
        run_git(repo, ["apply", "--cached", str(patch_path)], env)
        changed = run_git(repo, ["diff", "--cached", "--name-only", "--no-renames"], env).splitlines()
        changed = sorted(str(safe_relative(path, "patch changed path")) for path in changed)
        if changed != project["_changed_paths"]:
            raise CheckpointError(f"changed path mismatch for {name}: expected={project['_changed_paths']} actual={changed}")
        patched_tree = run_git(repo, ["write-tree"], env)
        if patched_tree != project["patched_tree"]:
            raise CheckpointError(f"patched tree mismatch for {name}: expected={project['patched_tree']} actual={patched_tree}")
        run_git(repo, ["apply", "--cached", "--reverse", str(patch_path)], env)
        reversed_tree = run_git(repo, ["write-tree"], env)
        if reversed_tree != project["base_tree"]:
            raise CheckpointError(f"reverse replay did not restore baseline tree for {name}: {reversed_tree}")
    return {
        "path": name,
        "status": "verified",
        "base_commit": head,
        "base_tree": base_tree,
        "patched_tree": patched_tree,
        "changed_paths": changed,
        "patch_sha256": patch_digest,
    }


def verify(source_root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    results = [verify_project(source_root, manifest_path.resolve().parent, item) for item in manifest["projects"]]
    return {
        "status": "PASS",
        "source_root": str(source_root.resolve()),
        "manifest": str(manifest_path.resolve()),
        "verification": "temporary-index patch replay and reverse replay",
        "live_worktree_verified": False,
        "projects": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path, help="Android source checkout root")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="checkpoint manifest")
    args = parser.parse_args(argv)
    try:
        report = verify(args.source_root, args.manifest)
    except CheckpointError as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
