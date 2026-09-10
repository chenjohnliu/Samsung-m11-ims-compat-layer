#!/usr/bin/env python3
"""Replace Samsung's removed IccUtils.getIccType ABI with an APK-local equivalent."""

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


TRANSFORMATION_ID = "BH1-sms-icc-type-compat"
TARGET_PATH = "com/sec/internal/google/ImsSmsImpl.smali"
EXPECTED_PATHS = {TARGET_PATH}
EXPECTED_INPUT_SHA256 = "6c786f60693305b4ad5617a60c32de7b7ba5c1e3cd42ac0ee4e613f93b013523"
OWNER = "Lcom/sec/internal/google/ImsSmsImpl;"
LEGACY = "invoke-static {v4}, Lcom/android/internal/telephony/uicc/IccUtils;->getIccType(I)I"
COMPAT = f"invoke-static {{v4}}, {OWNER}->getIccTypeCompat(I)I"
METHOD_RE = re.compile(r"(?ms)^\.method\s+(?P<header>[^\r\n]+)\r?\n.*?^\.end method\s*$")


def load_contract(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransformError(f"cannot read contract: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "transformation_id", "targets"}:
        raise TransformError("malformed contract")
    if raw["schema_version"] != 1 or raw["transformation_id"] != TRANSFORMATION_ID:
        raise TransformError("unsupported contract identity")
    targets = raw["targets"]
    if not isinstance(targets, list) or len(targets) != 1 or not isinstance(targets[0], dict):
        raise TransformError("contract must contain exactly one target")
    item = targets[0]
    keys = {"path", "class", "class_access", "super", "input_sha256",
            "required_methods", "legacy_call_count", "compat_call_count"}
    if set(item) != keys:
        raise TransformError("malformed target contract")
    rel = PurePosixPath(item["path"])
    if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != TARGET_PATH:
        raise TransformError("unexpected or unsafe target path")
    identity = (OWNER, ["public", "final"], "Ljava/lang/Object;",
                ["private canFallback(I)Z", "private canFallbackForTimeout()Z"], 2, 2)
    found = (item["class"], item["class_access"], item["super"],
             item["required_methods"], item["legacy_call_count"], item["compat_call_count"])
    if found != identity:
        raise TransformError("target identity drift")
    if item["input_sha256"] != EXPECTED_INPUT_SHA256:
        raise TransformError("input hash contract drift")
    return raw


def _methods(text: str, signature: str) -> list[str]:
    return [m.group(0) for m in METHOD_RE.finditer(text) if m.group("header") == signature]


def _identity(text: str, item: dict) -> None:
    rows = [line.split() for line in text.splitlines()
            if line.startswith(".class ") and line.split()[-1] == item["class"]]
    if len(rows) != 1 or rows[0][1:-1] != item["class_access"]:
        raise TransformError("class identity drift")
    if len(re.findall(r"(?m)^\.super\s+" + re.escape(item["super"]) + r"\s*$", text)) != 1:
        raise TransformError("superclass drift")
    for signature in item["required_methods"]:
        matches = _methods(text, signature)
        if len(matches) != 1 or matches[0].count(LEGACY) != 1:
            raise TransformError(f"required method or legacy call drift: {signature}")


def _helper() -> str:
    return f""".method private static getIccTypeCompat(I)I
    .locals 5
    .param p0, "phoneId"    # I

    const/4 v0, 0x0
    const-string v1, "ril.ICC_TYPE0"
    const/4 v2, 0x1
    if-ne p0, v2, :read
    const-string v1, "ril.ICC_TYPE1"

    :read
    :try_start
    const-string v2, "0"
    invoke-static {{v1, v2}}, Landroid/os/SystemProperties;->get(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
    move-result-object v2
    invoke-static {{v2}}, Ljava/lang/Integer;->parseInt(Ljava/lang/String;)I
    move-result v0
    :try_end
    .catch Ljava/lang/NumberFormatException; {{:try_start .. :try_end}} :invalid
    return v0

    :invalid
    move-exception v2
    const-string v3, "ImsSmsImpl"
    const-string v4, "BH1: invalid ICC type property; using unknown"
    invoke-static {{v3, v4, v2}}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    return v0
.end method"""


def _updated(text: str, item: dict) -> str:
    if "getIccTypeCompat(I)I" in text or COMPAT in text:
        raise TransformError("BH1 is already or partially applied")
    if text.count(LEGACY) != item["legacy_call_count"]:
        raise TransformError("legacy call count drift")
    result = text.replace(LEGACY, COMPAT)
    return result.rstrip() + "\n\n" + _helper() + "\n"


def _post(original: str, updated: str, item: dict) -> None:
    if original == updated or LEGACY in updated or updated.count(COMPAT) != item["compat_call_count"]:
        raise TransformError("call replacement post-state drift")
    helpers = _methods(updated, "private static getIccTypeCompat(I)I")
    if len(helpers) != 1:
        raise TransformError("compat helper post-state drift")
    helper = helpers[0]
    required = ("ril.ICC_TYPE0", "ril.ICC_TYPE1", "Landroid/os/SystemProperties;->get",
                "Ljava/lang/Integer;->parseInt", "Ljava/lang/NumberFormatException;")
    if any(marker not in helper for marker in required):
        raise TransformError("compat helper semantic drift")
    changed = set(item["required_methods"])
    for match in METHOD_RE.finditer(original):
        header = match.group("header")
        if header not in changed:
            matches = _methods(updated, header)
            if len(matches) != 1 or matches[0] != match.group(0):
                raise TransformError(f"unrelated method changed: {header}")


def transform(contract_path: Path, source_root: Path, overlay: Path, report: Path,
              allow_identical: bool = False) -> dict:
    contract = load_contract(contract_path)
    item = contract["targets"][0]
    if source_root.is_symlink() or not source_root.is_dir():
        raise TransformError("input root must be a non-symlink directory")
    root = source_root.resolve(strict=True)
    source = root.joinpath(*PurePosixPath(TARGET_PATH).parts)
    if source.is_symlink() or not source.is_file():
        raise TransformError("target must be a regular non-symlink file")
    if overlay.is_symlink() or report.is_symlink() or not overlay.parent.is_dir() or not report.parent.is_dir():
        raise TransformError("unsafe output path")
    overlay_abs = overlay.parent.resolve(strict=True) / overlay.name
    report_abs = report.parent.resolve(strict=True) / report.name
    if overlay_abs == report_abs or root == overlay_abs or root in overlay_abs.parents:
        raise TransformError("overlay and report must be distinct and outside input tree")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != item["input_sha256"]:
        raise TransformError("input hash drift")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TransformError("target is not UTF-8") from exc
    _identity(text, item)
    updated = _updated(text, item)
    _post(text, updated, item)
    output = updated.encode("utf-8")
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID,
               "changed": True, "files": [{"target": TARGET_PATH,
               "hooks": ["sms_icc_type_compat"],
               "input_sha256": hashlib.sha256(data).hexdigest(),
               "output_sha256": hashlib.sha256(output).hexdigest()}]}
    report_data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    if overlay.exists() or report.exists():
        same = False
        target = overlay.joinpath(*PurePosixPath(TARGET_PATH).parts)
        if allow_identical and report.is_file() and target.is_file():
            same = report.read_bytes() == report_data and target.read_bytes() == output
        if same:
            payload["changed"] = False
            return payload
        raise TransformError("refusing to overwrite existing overlay or report")
    temp_overlay = Path(tempfile.mkdtemp(prefix=f".{overlay.name}.", dir=overlay.parent))
    fd, temp_name = tempfile.mkstemp(prefix=f".{report.name}.", suffix=".tmp", dir=report.parent)
    os.close(fd)
    temp_report = Path(temp_name)
    published = False
    try:
        target = temp_overlay.joinpath(*PurePosixPath(TARGET_PATH).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(output)
        temp_report.write_bytes(report_data)
        os.link(temp_report, report_abs)
        published = True
        os.rename(temp_overlay, overlay_abs)
    except BaseException:
        if published:
            try: report_abs.unlink()
            except FileNotFoundError: pass
        shutil.rmtree(temp_overlay, ignore_errors=True)
        try: temp_report.unlink()
        except FileNotFoundError: pass
        raise
    try: temp_report.unlink()
    except OSError: pass
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--input-smali-root", required=True, type=Path)
    parser.add_argument("--output-overlay", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--allow-identical", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = transform(args.contract, args.input_smali_root, args.output_overlay,
                           args.report, args.allow_identical)
    except (OSError, TransformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
