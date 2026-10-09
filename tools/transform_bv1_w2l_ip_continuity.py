#!/usr/bin/env python3
"""Apply the fail-closed BV1 IMS W2L retained-IP classification trial."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath


class TransformError(ValueError):
    pass


TRANSFORMATION_ID = "BV1-w2l-ip-continuity-trial"
SOURCE_APK_SHA256 = "4cf9360b609fcc45329d038835a5913ba9c76844fe4cf59b70c132f904ae0dd1"
TARGET = "com/sec/internal/ims/core/PdnController$NetworkCallback.smali"
ADDITION = "com/sec/internal/ims/core/M11qW2LIPContinuity.smali"
TARGET_INPUT_SHA256 = "aeece7782e8e4f43607cdac9c57e10d3ac0c6c7d253c87935c415f34d230b60a"
TARGET_OUTPUT_SHA256 = "816a7a81f5c15af024240c618f9fd712af0faec800aba55e46b9f3c17b5a471c"
ADDITION_OUTPUT_SHA256 = "ff3ce00936d60b6b5996af08aaa0262652f090245a2d1ea60ac97fba2aab53a9"
METHOD = "private isLocalIpChanged(Lcom/sec/internal/helper/os/LinkPropertiesWrapper;)I"
ASSET = Path(__file__).with_name("ims_w2l_trial") / "M11qW2LIPContinuity.smali"
METHOD_RE = re.compile(r"(?ms)^\.method\s+(?P<header>[^\r\n]+)\r?\n.*?^\.end method\s*$")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _methods(text: str, signature: str) -> list[str]:
    return [m.group(0) for m in METHOD_RE.finditer(text) if m.group("header") == signature]


def _one(text: str, signature: str) -> str:
    found = _methods(text, signature)
    if len(found) != 1:
        raise TransformError(f"required method drift: {signature}")
    return found[0]


def _patch(text: str) -> str:
    original = _one(text, METHOD)
    anchor = '''    .line 772
    iget-object v0, p0, Lcom/sec/internal/ims/core/PdnController$NetworkCallback;->this$0:Lcom/sec/internal/ims/core/PdnController;
'''
    insertion = '''    invoke-static {p0, p1}, Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->shouldClassifyAsStacked(Lcom/sec/internal/ims/core/PdnController$NetworkCallback;Lcom/sec/internal/helper/os/LinkPropertiesWrapper;)Z

    move-result v2

    if-eqz v2, :bv1_original_local_ip_check

    const/4 v2, 0x2

    return v2

    :bv1_original_local_ip_check
    .line 772
    iget-object v0, p0, Lcom/sec/internal/ims/core/PdnController$NetworkCallback;->this$0:Lcom/sec/internal/ims/core/PdnController;
'''
    if original.count(anchor) != 1:
        raise TransformError("anchor drift: isLocalIpChanged entry")
    return text.replace(original, original.replace(anchor, insertion, 1), 1)


def load_contract(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransformError(f"cannot read contract: {exc}") from exc
    required = {"schema_version", "transformation_id", "source_baseline", "targets", "additions"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise TransformError("malformed contract")
    if raw["schema_version"] != 1 or raw["transformation_id"] != TRANSFORMATION_ID:
        raise TransformError("unsupported contract identity")
    if raw["source_baseline"] != {
        "apk_sha256": SOURCE_APK_SHA256,
        "decoded_smali_root": "exact current unsigned IMS base",
    }:
        raise TransformError("malformed source baseline")
    target_keys = {"path", "input_sha256", "output_sha256", "redecoded_sha256", "required_methods", "operations"}
    if not isinstance(raw["targets"], list) or len(raw["targets"]) != 1:
        raise TransformError("target set drift")
    item = raw["targets"][0]
    if not isinstance(item, dict) or set(item) != target_keys:
        raise TransformError("malformed target")
    if item["path"] != TARGET or item["required_methods"] != [METHOD]:
        raise TransformError("target identity drift")
    if item["operations"] != ["classify_qualified_retained_w2l_as_stacked"]:
        raise TransformError("target operation drift")
    if item["input_sha256"] != TARGET_INPUT_SHA256 or item["output_sha256"] != TARGET_OUTPUT_SHA256:
        raise TransformError("target hash identity drift")
    addition_keys = {"path", "output_sha256", "redecoded_sha256", "operations"}
    if not isinstance(raw["additions"], list) or len(raw["additions"]) != 1:
        raise TransformError("addition set drift")
    addition = raw["additions"][0]
    if not isinstance(addition, dict) or set(addition) != addition_keys:
        raise TransformError("malformed addition")
    if addition["path"] != ADDITION:
        raise TransformError("addition identity drift")
    if addition["operations"] != ["fail_closed_w2l_continuity_classifier"]:
        raise TransformError("addition operation drift")
    if addition["output_sha256"] != ADDITION_OUTPUT_SHA256:
        raise TransformError("addition hash identity drift")
    for entry in (item, addition):
        rel = PurePosixPath(entry["path"])
        if rel.is_absolute() or ".." in rel.parts:
            raise TransformError("unsafe contract path")
    for entry, keys in ((item, ("input_sha256", "output_sha256", "redecoded_sha256")), (addition, ("output_sha256", "redecoded_sha256"))):
        for key in keys:
            if not isinstance(entry[key], str) or re.fullmatch(r"[0-9a-f]{64}", entry[key]) is None:
                raise TransformError(f"invalid hash: {entry['path']}:{key}")
    return raw


def transform(contract_path: Path, source_root: Path, overlay: Path, report: Path) -> dict:
    contract = load_contract(contract_path)
    if source_root.is_symlink() or not source_root.is_dir():
        raise TransformError("input root must be a non-symlink directory")
    root = source_root.absolute()
    target_spec = contract["targets"][0]
    source = root.joinpath(*PurePosixPath(TARGET).parts)
    if source.is_symlink() or not source.is_file():
        raise TransformError(f"target must be a regular non-symlink file: {TARGET}")
    original_data = source.read_bytes()
    original_hash = _sha(original_data)
    if original_hash == target_spec["output_sha256"]:
        raise TransformError(f"already applied: {TARGET}")
    if original_hash != target_spec["input_sha256"]:
        raise TransformError(f"input hash drift: {TARGET}")
    original = original_data.decode("utf-8")
    updated = _patch(original)
    if original == updated:
        raise TransformError("transform made no change")
    updated_data = updated.encode("utf-8")
    if _sha(updated_data) != target_spec["output_sha256"]:
        raise TransformError("post-transform hash drift")
    for match in METHOD_RE.finditer(original):
        signature = match.group("header")
        found = _methods(updated, signature)
        if len(found) != 1:
            raise TransformError(f"method set drift: {signature}")
        if signature != METHOD and found[0] != match.group(0):
            raise TransformError(f"unrelated method changed: {signature}")
    asset_data = ASSET.read_bytes()
    addition_spec = contract["additions"][0]
    if _sha(asset_data) != addition_spec["output_sha256"]:
        raise TransformError(f"addition asset hash drift: {ADDITION}")
    if root.joinpath(*PurePosixPath(ADDITION).parts).exists():
        raise TransformError(f"addition already exists: {ADDITION}")
    files = [
        {"target": TARGET, "kind": "modified", "operations": target_spec["operations"], "input_sha256": original_hash, "output_sha256": _sha(updated_data)},
        {"target": ADDITION, "kind": "added", "operations": addition_spec["operations"], "input_sha256": None, "output_sha256": _sha(asset_data)},
    ]
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID, "changed": True, "files": files}
    report_data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    if overlay.exists() or report.exists():
        raise TransformError("refusing to overwrite existing overlay or report")
    if overlay.is_symlink() or report.is_symlink() or not overlay.parent.is_dir() or not report.parent.is_dir():
        raise TransformError("unsafe output path")
    temp_overlay = Path(tempfile.mkdtemp(prefix=f".{overlay.name}.", dir=overlay.parent))
    fd, temp_name = tempfile.mkstemp(prefix=f".{report.name}.", suffix=".tmp", dir=report.parent)
    os.close(fd)
    temp_report = Path(temp_name)
    published = False
    try:
        for path_key, data in ((TARGET, updated_data), (ADDITION, asset_data)):
            target = temp_overlay.joinpath(*PurePosixPath(path_key).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        temp_report.write_bytes(report_data)
        os.replace(temp_report, report.absolute())
        published = True
        os.rename(temp_overlay, overlay.absolute())
    except BaseException:
        if published:
            report.unlink(missing_ok=True)
        shutil.rmtree(temp_overlay, ignore_errors=True)
        temp_report.unlink(missing_ok=True)
        raise
    temp_report.unlink(missing_ok=True)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--input-smali-root", required=True, type=Path)
    parser.add_argument("--output-overlay", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = transform(args.contract, args.input_smali_root, args.output_overlay, args.report)
    except (OSError, UnicodeError, TransformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
