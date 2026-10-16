#!/usr/bin/env python3
"""Validate the public Cherish source index against local checkpoint records.

Without --forks-root this is an offline metadata/artifact check. It verifies
that the index matches the immutable baseline and supplement manifests, that
patch files match their recorded hashes, and that every declared tree chain is
contiguous. It does not prove that a remote fork still exists or that its
commit objects are available.

With --forks-root, the synchronized Telephony and Telecom forks are also
checked using local Git objects only. Each pinned commit chain is matched to
the ordered patch files using a temporary Git index, leaving clone refs,
worktrees, and real indexes untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


BASELINE_MANIFEST = "platform/checkpoints/cherish-20261012/manifest.json"
IMS_SUPPLEMENT_MANIFEST = "platform/checkpoints/cherish-20261012-ims-supplement/manifest.json"
VOWIFI_MANIFEST = "platform/checkpoints/cherish-20261016-vowifi/manifest.json"
INDEX_PATH = "devices/m11q/cherish-source-index.json"
EXPECTED_PROJECT_COUNT = 14
SYNCED_FORK_PROJECTS = {"frameworks/opt/telephony", "packages/services/Telecomm"}
FORK_REPOSITORIES = {
    "frameworks/opt/telephony": "https://github.com/chenjohnliu/android_frameworks_opt_telephony.git",
    "packages/services/Telecomm": "https://github.com/chenjohnliu/android_packages_services_Telecomm.git",
}
OID_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_TIMEOUT_SECONDS = 30


class ValidationError(Exception):
    """An actionable source-index validation failure."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"expected a JSON object in {path}")
    return data


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} must be a non-empty relative path")
    if "\\" in value or "\x00" in value:
        raise ValidationError(f"{label} contains an unsafe path separator")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValidationError(f"{label} is not a safe relative path: {value!r}")
    if path.parts and re.match(r"^[A-Za-z]:", path.parts[0]):
        raise ValidationError(f"{label} contains a drive-qualified path")
    return path


def _inside(root: Path, relative: Any, label: str, *, must_exist: bool = True) -> Path:
    rel = _safe_relative_path(relative, label)
    candidate = root.joinpath(*rel.parts)
    try:
        resolved_root = root.resolve(strict=False)
        resolved = candidate.resolve(strict=False)
        if must_exist and not resolved.exists():
            raise FileNotFoundError(str(resolved))
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ValidationError(f"{label} escapes the repository or is unavailable: {relative}") from exc
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ValidationError(f"cannot read patch {path}: {exc}") from exc
    return digest.hexdigest()


def _git(repo: Path, args: list[str], *, env: dict[str, str] | None = None) -> str:
    command = ["git", "-C", str(repo), *args]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError(f"Git command failed or timed out in {repo}: {args[0]}") from exc
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValidationError(f"git {' '.join(args)} failed in {repo}: {detail}")
    return completed.stdout.strip()


def _manifest_sources(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    baseline = _load_json(_inside(repo_root, BASELINE_MANIFEST, "baseline manifest"))
    ims = _load_json(_inside(repo_root, IMS_SUPPLEMENT_MANIFEST, "IMS supplement manifest"))
    vowifi = _load_json(_inside(repo_root, VOWIFI_MANIFEST, "VoWiFi supplement manifest"))
    return baseline, ims, vowifi


def _map_unique(items: Any, key: str, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        raise ValidationError(f"{label} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get(key), str):
            raise ValidationError(f"{label} contains an invalid entry")
        value = item[key]
        if value in result:
            raise ValidationError(f"duplicate {key} {value!r} in {label}")
        result[value] = item
    return result


def _expected_chains(
    baseline: dict[str, Any], ims: dict[str, Any], vowifi: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]]]:
    base_projects = _map_unique(baseline.get("projects"), "path", "baseline projects")
    if len(base_projects) != EXPECTED_PROJECT_COUNT:
        raise ValidationError(f"baseline manifest must contain {EXPECTED_PROJECT_COUNT} projects")

    ims_projects = _map_unique(ims.get("projects"), "path", "IMS supplement projects")
    vowifi_projects: dict[str, dict[str, Any]] = {}
    raw_vowifi = vowifi.get("projects")
    if not isinstance(raw_vowifi, list):
        raise ValidationError("VoWiFi supplement projects must be a list")
    for item in raw_vowifi:
        if not isinstance(item, dict) or not isinstance(item.get("project"), str):
            raise ValidationError("VoWiFi supplement contains an invalid project entry")
        name = item["project"]
        if name in vowifi_projects:
            raise ValidationError(f"duplicate project {name!r} in VoWiFi supplement")
        vowifi_projects[name] = item

    chains: dict[str, list[dict[str, str]]] = {}
    references: dict[str, list[dict[str, str]]] = {}

    for project_path, base in base_projects.items():
        baseline_patch = base.get("patch")
        if not isinstance(baseline_patch, str):
            raise ValidationError(f"baseline patch missing for {project_path}")
        steps = [{
            "path": f"platform/checkpoints/cherish-20261012/{baseline_patch}",
            "sha256": base.get("sha256"),
            "before_tree": base.get("base_tree"),
            "after_tree": base.get("patched_tree"),
        }]
        refs: list[dict[str, str]] = []

        ims_entry = ims_projects.get(project_path)
        if ims_entry:
            action = ims_entry.get("action")
            patch = ims_entry.get("patch")
            patch_record = {
                "path": f"platform/checkpoints/cherish-20261012-ims-supplement/{patch}",
                "sha256": ims_entry.get("patch_sha256"),
            }
            if action == "apply_once_after_parent_checkpoint":
                steps.append({
                    **patch_record,
                    # The two apply-once records inherit the parent checkpoint
                    # tree; the manifest's parent_patched_tree field is only
                    # populated on the MMS reference-only record.
                    "before_tree": base.get("patched_tree"),
                    "after_tree": ims_entry.get("after_tree"),
                })
            elif action == "reference_only_do_not_reapply":
                refs.append(patch_record)
            else:
                raise ValidationError(f"unsupported IMS supplement action {action!r} for {project_path}")

        vowifi_entry = vowifi_projects.get(project_path)
        if vowifi_entry:
            new_patches = [p for p in vowifi_entry.get("patches", []) if p.get("role") != "prerequisite"]
            if len(new_patches) != 1:
                raise ValidationError(f"expected exactly one new VoWiFi patch for {project_path}")
            patch = new_patches[0]
            steps.append({
                "path": f"platform/checkpoints/cherish-20261016-vowifi/{patch.get('name')}",
                "sha256": patch.get("sha256"),
                "before_tree": vowifi_entry.get("prerequisite_trees", {}).get("candidate_precondition"),
                "after_tree": vowifi_entry.get("validation", {}).get("replay_tree"),
            })

        chains[project_path] = steps
        references[project_path] = refs
    return base_projects, chains, references


def _validate_step_shape(step: dict[str, Any], project: str, position: int) -> None:
    for field in ("path", "sha256", "before_tree", "after_tree"):
        if not isinstance(step.get(field), str) or not step[field]:
            raise ValidationError(f"{project} patch step {position} has invalid {field}")
    if not SHA256_RE.fullmatch(step["sha256"]):
        raise ValidationError(f"{project} patch step {position} has malformed SHA-256")
    for field in ("before_tree", "after_tree"):
        if not OID_RE.fullmatch(step[field]):
            raise ValidationError(f"{project} patch step {position} has malformed {field}")


def validate_index_data(
    data: dict[str, Any], repo_root: Path, forks_root: Path | None = None
) -> dict[str, int]:
    """Validate parsed index data; exposed for focused tests."""
    baseline, ims, vowifi = _manifest_sources(repo_root)
    base_projects, expected_chains, expected_references = _expected_chains(baseline, ims, vowifi)

    if data.get("format_version") != 1:
        raise ValidationError("unsupported source-index format_version")
    manifests = data.get("checkpoint_manifests")
    expected_manifests = [BASELINE_MANIFEST, IMS_SUPPLEMENT_MANIFEST, VOWIFI_MANIFEST]
    if manifests != expected_manifests:
        raise ValidationError("checkpoint_manifests must list the baseline and both supplements in order")

    entries = _map_unique(data.get("projects"), "path", "source-index projects")
    if set(entries) != set(base_projects):
        missing = sorted(set(base_projects) - set(entries))
        extra = sorted(set(entries) - set(base_projects))
        raise ValidationError(f"project coverage mismatch; missing={missing}, extra={extra}")

    synchronized_projects: set[str] = set()
    for project_path, base in base_projects.items():
        entry = entries[project_path]
        if entry.get("role") != base.get("role"):
            raise ValidationError(f"role mismatch for {project_path}")
        if entry.get("source_url") != base.get("source_url"):
            raise ValidationError(f"source URL mismatch for {project_path}")
        if entry.get("base_commit") != base.get("base_commit") or entry.get("base_tree") != base.get("base_tree"):
            raise ValidationError(f"source base mismatch for {project_path}")

        steps = entry.get("patches")
        expected = expected_chains[project_path]
        if not isinstance(steps, list) or len(steps) != len(expected):
            raise ValidationError(f"ordered patch count mismatch for {project_path}")
        previous_tree = base.get("base_tree")
        for position, (step, expected_step) in enumerate(zip(steps, expected), start=1):
            if not isinstance(step, dict):
                raise ValidationError(f"{project_path} patch step {position} is not an object")
            _validate_step_shape(step, project_path, position)
            if step != expected_step:
                raise ValidationError(f"patch metadata differs from checkpoint manifests for {project_path}, step {position}")
            if step["before_tree"] != previous_tree:
                raise ValidationError(f"broken patch tree chain for {project_path}, step {position}")
            patch_file = _inside(repo_root, step["path"], f"{project_path} patch")
            actual_hash = _sha256(patch_file)
            if actual_hash != step["sha256"]:
                raise ValidationError(f"patch hash mismatch for {project_path}: {step['path']}")
            previous_tree = step["after_tree"]

        if entry.get("final_tree") != previous_tree:
            raise ValidationError(f"final_tree does not match ordered patch chain for {project_path}")

        refs = entry.get("reference_only_patches")
        expected_refs = expected_references[project_path]
        if not isinstance(refs, list) or refs != expected_refs:
            raise ValidationError(f"reference-only patch list mismatch for {project_path}")
        patch_paths = {step["path"] for step in steps}
        for reference in refs:
            if reference["path"] in patch_paths:
                raise ValidationError(f"reference-only patch is also applied for {project_path}: {reference['path']}")
            ref_file = _inside(repo_root, reference["path"], f"{project_path} reference patch")
            if _sha256(ref_file) != reference["sha256"]:
                raise ValidationError(f"reference-only patch hash mismatch for {project_path}")

        fork = entry.get("synchronized_fork")
        route = entry.get("source_route")
        if route == "synchronized_fork_or_patch_recipe":
            synchronized_projects.add(project_path)
            if not isinstance(fork, dict):
                raise ValidationError(f"synchronized fork metadata missing for {project_path}")
            _validate_fork_metadata(
                project_path, fork, expected, entry.get("base_commit"), entry.get("base_tree"),
                entry.get("final_tree"), forks_root, repo_root,
            )
        elif fork is not None:
            raise ValidationError(f"unexpected synchronized fork metadata for patch-only project {project_path}")
        elif route != "patch_recipe":
            raise ValidationError(f"unsupported source_route for {project_path}: {route!r}")

    if synchronized_projects != SYNCED_FORK_PROJECTS:
        raise ValidationError(
            f"synchronized fork project set mismatch; expected={sorted(SYNCED_FORK_PROJECTS)}, "
            f"actual={sorted(synchronized_projects)}"
        )

    return {"projects": len(entries), "patches": sum(len(x["patches"]) for x in entries.values()),
            "reference_only": sum(len(x["reference_only_patches"]) for x in entries.values()),
            "forks_checked": 2 if forks_root is not None else 0}


def _validate_fork_metadata(
    project_path: str,
    fork: dict[str, Any],
    expected_steps: list[dict[str, str]],
    base_commit: str,
    base_tree: str,
    final_tree: str,
    forks_root: Path | None,
    publication_root: Path,
) -> None:
    if fork.get("repository") != FORK_REPOSITORIES.get(project_path):
        raise ValidationError(f"synchronized fork repository mismatch for {project_path}")
    if fork.get("branch") != "cherish-13-m11q-ims":
        raise ValidationError(f"synchronized fork branch mismatch for {project_path}")
    commits = fork.get("commits")
    if not isinstance(commits, list) or len(commits) != len(expected_steps):
        raise ValidationError(f"fork commit count does not match patch chain for {project_path}")
    previous = None
    for index, (commit, step) in enumerate(zip(commits, expected_steps)):
        if not isinstance(commit, dict):
            raise ValidationError(f"invalid fork commit mapping for {project_path}")
        if commit.get("patch_path") != step["path"] or commit.get("patch_sha256") != step["sha256"]:
            raise ValidationError(f"fork commit patch mapping drift for {project_path}, step {index + 1}")
        if commit.get("tree") != step["after_tree"]:
            raise ValidationError(f"fork commit tree mapping drift for {project_path}, step {index + 1}")
        expected_parent = previous if previous is not None else base_commit
        if commit.get("parent") != expected_parent:
            raise ValidationError(f"fork commit parent mapping drift for {project_path}, step {index + 1}")
        if not OID_RE.fullmatch(str(commit.get("sha", ""))):
            raise ValidationError(f"malformed fork commit SHA for {project_path}, step {index + 1}")
        previous = commit["sha"]
    if fork.get("commit") != previous or fork.get("tree") != final_tree:
        raise ValidationError(f"fork tip does not match final patch tree for {project_path}")

    if forks_root is None:
        return
    clone_name = {
        "frameworks/opt/telephony": "telephony",
        "packages/services/Telecomm": "telecomm",
    }.get(project_path)
    if clone_name is None:
        raise ValidationError(f"no local fork clone mapping defined for {project_path}")
    clone = _inside(forks_root, clone_name, f"{project_path} fork clone")
    top = Path(_git(clone, ["rev-parse", "--show-toplevel"])).resolve()
    if top != clone:
        raise ValidationError(f"fork clone path must be the Git repository root: {clone}")
    if _git(clone, ["config", "--get", "remote.origin.url"]) != fork["repository"]:
        raise ValidationError(f"local fork origin differs from the source index for {project_path}")
    base = base_commit
    resolved_base = _git(clone, ["rev-parse", f"{base}^{{commit}}"])
    if resolved_base != base:
        raise ValidationError(f"fork base commit is not available as a full commit for {project_path}")
    base_tree_actual = _git(clone, ["rev-parse", f"{base}^{{tree}}"])
    if base_tree_actual != base_tree or base_tree_actual != expected_steps[0]["before_tree"]:
        raise ValidationError(f"fork base tree mismatch for {project_path}")
    pinned_tip = fork["commit"]
    _git(clone, ["cat-file", "-e", f"{pinned_tip}^{{commit}}"])
    resolved_tip = _git(clone, ["rev-parse", f"{pinned_tip}^{{commit}}"])
    if resolved_tip != pinned_tip:
        raise ValidationError(f"pinned fork commit is unavailable or resolves differently for {project_path}")
    _git(clone, ["merge-base", "--is-ancestor", base, pinned_tip])

    clone_tree = _git(clone, ["rev-parse", f"{pinned_tip}^{{tree}}"])
    if clone_tree != fork["tree"]:
        raise ValidationError(f"pinned fork tree mismatch for {project_path}")

    for index, (commit_record, step) in enumerate(zip(commits, expected_steps), start=1):
        sha = commit_record["sha"]
        _git(clone, ["cat-file", "-e", f"{sha}^{{commit}}"])
        resolved = _git(clone, ["rev-parse", f"{sha}^{{commit}}"])
        if resolved != sha:
            raise ValidationError(f"fork commit unavailable or abbreviated for {project_path}, step {index}")
        actual_parent = _git(clone, ["rev-parse", f"{sha}^"])
        _git(clone, ["cat-file", "-e", f"{actual_parent}^{{commit}}"])
        actual_tree = _git(clone, ["rev-parse", f"{sha}^{{tree}}"])
        if actual_parent != commit_record["parent"] or actual_tree != commit_record["tree"]:
            raise ValidationError(f"fork commit object mapping mismatch for {project_path}, step {index}")

    with tempfile.TemporaryDirectory(prefix="cherish-index-verify-") as temp_dir:
        index_path = Path(temp_dir) / "index"
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(index_path)
        _git(clone, ["read-tree", base], env=env)
        for index, (commit_record, step) in enumerate(zip(commits, expected_steps), start=1):
            patch_path = _inside(publication_root, step["path"], f"{project_path} fork patch")
            _git(clone, ["apply", "--cached", "--binary", str(patch_path)], env=env)
            resulting_tree = _git(clone, ["write-tree"], env=env)
            commit_tree = _git(clone, ["rev-parse", f"{commit_record['sha']}^{{tree}}"])
            if resulting_tree != step["after_tree"] or resulting_tree != commit_tree:
                raise ValidationError(f"patch-to-fork tree mismatch for {project_path}, step {index}")


def validate(repo_root: Path, forks_root: Path | None = None) -> dict[str, int]:
    repo_root = repo_root.resolve(strict=False)
    if not repo_root.is_dir():
        raise ValidationError(f"repository root is unavailable: {repo_root}")
    index_path = _inside(repo_root, INDEX_PATH, "source index")
    if forks_root is not None:
        forks_root = forks_root.resolve(strict=False)
        if not forks_root.is_dir():
            raise ValidationError(f"forks root is unavailable: {forks_root}")
    return validate_index_data(_load_json(index_path), repo_root, forks_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="compatibility repository root (default: this script's parent repository)",
    )
    parser.add_argument(
        "--forks-root",
        type=Path,
        help="optional directory containing local telephony/ and telecomm/ clones",
    )
    args = parser.parse_args(argv)
    try:
        result = validate(args.repo_root, args.forks_root)
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.forks_root:
        mode = "local fork Git objects verified"
    else:
        mode = "offline metadata/artifact checks passed (remote object existence not checked)"
    print(
        f"PASS: {result['projects']} projects, {result['patches']} ordered patches, "
        f"{result['reference_only']} reference-only patches; {mode}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
