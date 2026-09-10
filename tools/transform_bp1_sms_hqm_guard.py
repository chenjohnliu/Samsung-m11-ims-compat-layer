#!/usr/bin/env python3
"""Fail soft when optional Samsung SMS HQM telemetry cannot query the SMS role."""

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


TRANSFORMATION_ID = "BP1-sms-hqm-telemetry-guard"
TARGET_PATH = "com/sec/internal/ims/servicemodules/sms/SmsUtil.smali"
EXPECTED_PATHS = {TARGET_PATH}
EXPECTED_INPUT_SHA256 = "d01a780d6c27f99b1d3de7b7d8f6ba0994b95873b469c630cb8331c06ea077ca"
OWNER = "Lcom/sec/internal/ims/servicemodules/sms/SmsUtil;"
METHOD = "private static sendSMSInfoToHQM(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;ZI)V"
LOOKUP = "invoke-static/range {p0 .. p0}, Landroid/provider/Telephony$Sms;->getDefaultSmsPackage(Landroid/content/Context;)Ljava/lang/String;"
MARKER = "BP1: default SMS role unavailable; HQM CSDA omitted"
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
            "required_method", "legacy_lookup_count", "guarded_lookup_count"}
    if set(item) != keys:
        raise TransformError("malformed target contract")
    rel = PurePosixPath(item["path"])
    if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != TARGET_PATH:
        raise TransformError("unexpected or unsafe target path")
    identity = (OWNER, ["public"], "Ljava/lang/Object;", METHOD, 1, 1)
    found = (item["class"], item["class_access"], item["super"], item["required_method"],
             item["legacy_lookup_count"], item["guarded_lookup_count"])
    if found != identity:
        raise TransformError("target identity drift")
    if item["input_sha256"] != EXPECTED_INPUT_SHA256:
        raise TransformError("input hash contract drift")
    return raw


def _methods(text: str, signature: str) -> list[str]:
    return [m.group(0) for m in METHOD_RE.finditer(text) if m.group("header") == signature]


def _identity(text: str, item: dict) -> str:
    rows = [line.split() for line in text.splitlines()
            if line.startswith(".class ") and line.split()[-1] == item["class"]]
    if len(rows) != 1 or rows[0][1:-1] != item["class_access"]:
        raise TransformError("class identity drift")
    if len(re.findall(r"(?m)^\.super\s+" + re.escape(item["super"]) + r"\s*$", text)) != 1:
        raise TransformError("superclass drift")
    methods = _methods(text, item["required_method"])
    if len(methods) != 1:
        raise TransformError("required method drift")
    method = methods[0]
    if method.count(LOOKUP) != item["legacy_lookup_count"]:
        raise TransformError("legacy lookup anchor drift")
    if MARKER in method or ":bp1_sms_role_start" in method:
        raise TransformError("BP1 is already or partially applied")
    return method


def _updated(text: str, method: str) -> str:
    old = LOOKUP + "\n\n    move-result-object v7"
    new = f""":bp1_sms_role_start
    {LOOKUP}

    move-result-object v7
    :bp1_sms_role_end
    .catch Ljava/lang/RuntimeException; {{:bp1_sms_role_start .. :bp1_sms_role_end}} :bp1_sms_role_failed

    goto :bp1_sms_role_done

    :bp1_sms_role_failed
    move-exception v7
    sget-object v0, {OWNER}->LOG_TAG:Ljava/lang/String;
    const-string v8, \"{MARKER}\"
    invoke-static {{v0, v8, v7}}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Throwable;)I
    const/4 v7, 0x0

    :bp1_sms_role_done"""
    if method.count(old) != 1:
        raise TransformError("lookup/move-result anchor drift")
    updated_method = method.replace(old, new)
    return text.replace(method, updated_method)


def _post(original: str, updated: str, item: dict) -> None:
    if original == updated or updated.count(MARKER) != item["guarded_lookup_count"]:
        raise TransformError("guard post-state drift")
    method = _methods(updated, item["required_method"])
    if len(method) != 1:
        raise TransformError("required method post-state drift")
    body = method[0]
    required_once = (LOOKUP, "Ljava/lang/RuntimeException;", "const/4 v7, 0x0",
                     "Landroid/util/Log;->w")
    if any(body.count(marker) != 1 for marker in required_once):
        raise TransformError("guard semantics drift")
    if body.count(":bp1_sms_role_failed") != 2:
        raise TransformError("guard semantics drift")
    if "Ljava/lang/Throwable; {:bp1_sms_role_start" in body:
        raise TransformError("guard is broader than RuntimeException")
    for match in METHOD_RE.finditer(original):
        if match.group("header") != item["required_method"]:
            matches = _methods(updated, match.group("header"))
            if len(matches) != 1 or matches[0] != match.group(0):
                raise TransformError(f"unrelated method changed: {match.group('header')}")


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
    method = _identity(text, item)
    updated = _updated(text, method)
    _post(text, updated, item)
    output = updated.encode("utf-8")
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID,
               "changed": True, "files": [{"target": TARGET_PATH,
               "hooks": ["sms_hqm_role_fail_soft"],
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
