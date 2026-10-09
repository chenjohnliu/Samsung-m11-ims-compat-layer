#!/usr/bin/env python3
"""Read-only local Git inventory; remote-tracking refs are explicitly not live proof."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess


def run(path, *args):
    result = subprocess.run(["git", "-C", str(path), *args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git failed: " + " ".join(args))
    return result.stdout.strip()


def inspect(root, relative):
    path = root / relative
    try:
        status = run(path, "status", "--porcelain=v1", "--untracked-files=normal")
        head = run(path, "rev-parse", "HEAD")
        refs = run(path, "for-each-ref", "--format=%(refname:short)|%(objectname)|%(upstream:short)|%(upstream:track)", "refs/heads")
        cover = run(path, "for-each-ref", "--contains", "HEAD", "--format=%(refname:short)", "refs/remotes")
        # Manifest revisions often point to annotated release tags: compare
        # their peeled commit too, not the tag-object hash against HEAD.
        manifest_refs = run(path, "for-each-ref", "--format=%(objectname) %(*objectname)", "refs/remotes/m").split()
        remotes = run(path, "remote", "-v")
        result = {"path": relative, "head": head, "status": status.splitlines(),
                  "branches": refs.splitlines(), "cached_remote_contains_head": [r for r in cover.splitlines() if not r.startswith("m/")],
                  "head_equals_manifest_pin": head in manifest_refs,
                  "remotes": remotes.splitlines()}
        return result
    except Exception as exc:
        return {"path": relative, "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    listed = subprocess.check_output(["repo", "list", "-p"], cwd=root, text=True).splitlines()
    paths = set(listed)
    # Find custom repos omitted from repo's manifest. Prune managed checkouts,
    # generated output and .repo's internal object stores rather than scanning them.
    listed_set = set(listed)
    for directory, children, files in os.walk(root, followlinks=False):
        rel = Path(directory).relative_to(root).as_posix()
        if ".git" in children or ".git" in files:
            paths.add(rel)
            children[:] = []
            continue
        if rel in listed_set:
            children[:] = []
            continue
        children[:] = [name for name in children if name not in
                       {".repo", "out", ".git", "__pycache__", "node_modules"}]
    if (root / ".repo/manifests/.git").exists():
        paths.add(".repo/manifests")
    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks = [pool.submit(inspect, root, relative) for relative in sorted(paths)]
        for task in as_completed(tasks):
            results.append(task.result())
            if len(results) % 200 == 0:
                print("audited", len(results), "/", len(paths), flush=True)
    results.sort(key=lambda item: item["path"])
    summary = {"manifest_project_count": len(listed), "git_repo_count": len(results),
               "dirty": [r["path"] for r in results if r.get("status")],
               "head_not_in_cached_remote_or_manifest": [r["path"] for r in results if not r.get("error") and not r["cached_remote_contains_head"] and not r["head_equals_manifest_pin"]],
               "local_branches_ahead_or_untracked": [r["path"] for r in results if any(
                   "ahead" in b or "gone" in b or b.endswith("||") for b in r.get("branches", []))],
               "errors": [r for r in results if r.get("error")],
               "remote_check": "local cached refs only; verify live remote for candidates"}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump({"summary": summary, "repositories": results}, stream, indent=2)
    print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in summary.items()}, indent=2), flush=True)


if __name__ == "__main__":
    main()
