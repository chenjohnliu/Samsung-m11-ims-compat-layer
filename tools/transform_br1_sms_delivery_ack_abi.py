#!/usr/bin/env python3
"""Suppress one Samsung-only SMS delivery-ACK callback absent from Android 13."""

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


TRANSFORMATION_ID = "BR1-sms-delivery-ack-abi-guard"
TARGET_PATH = "com/sec/internal/google/ImsSmsImpl$SmsEventListener.smali"
EXPECTED_PATHS = {TARGET_PATH}
EXPECTED_INPUT_SHA256 = "baf2f922d340d4af0df73e9ccc531a9c0c7ba2ee69454ddef1839234ea72b658"
OWNER = "Lcom/sec/internal/google/ImsSmsImpl$SmsEventListener;"
METHOD = "public onReceiveSMSDeliveryReportAck(III)V"
CALLBACK = ("invoke-interface {v1, p1, p2}, "
            "Landroid/telephony/ims/aidl/IImsSmsListener;"
            "->onReceiveSmsDeliveryReportAck(II)V")
MARKER = "# BR1: Android 13 has no Samsung delivery-report completion callback"
KDDI_ANCHOR = "sget-object v1, Lcom/sec/internal/constants/Mno;->KDDI:Lcom/sec/internal/constants/Mno;"
RETRY_ANCHOR = "Landroid/os/Handler;->sendMessageDelayed(Landroid/os/Message;J)Z"
READY_ANCHOR = 'const-string v2, "Sms not ready."'
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
            "required_method", "legacy_callback_count", "suppressed_callback_count",
            "kddi_retry_anchor_count"}
    if set(item) != keys:
        raise TransformError("malformed target contract")
    rel = PurePosixPath(item["path"])
    if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != TARGET_PATH:
        raise TransformError("unexpected or unsafe target path")
    identity = (OWNER, [], "Lcom/sec/ims/sms/ISmsServiceEventListener$Stub;",
                METHOD, 1, 1, 1)
    found = (item["class"], item["class_access"], item["super"], item["required_method"],
             item["legacy_callback_count"], item["suppressed_callback_count"],
             item["kddi_retry_anchor_count"])
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
    if method.count(CALLBACK) != item["legacy_callback_count"]:
        raise TransformError("legacy callback anchor drift")
    if method.count(KDDI_ANCHOR) != item["kddi_retry_anchor_count"]:
        raise TransformError("KDDI retry anchor drift")
    if MARKER in method:
        raise TransformError("BR1 is already or partially applied")
    return method


def _updated(text: str, method: str) -> str:
    old = "    " + CALLBACK
    if method.count(old) != 1:
        raise TransformError("callback instruction drift")
    updated_method = method.replace(old, "    " + MARKER)
    return text.replace(method, updated_method)


def _post(original: str, updated: str, item: dict) -> None:
    methods = _methods(updated, item["required_method"])
    if original == updated or len(methods) != 1:
        raise TransformError("callback suppression post-state drift")
    body = methods[0]
    if body.count(CALLBACK) != 0 or body.count(MARKER) != item["suppressed_callback_count"]:
        raise TransformError("callback suppression semantics drift")
    for anchor in (KDDI_ANCHOR, RETRY_ANCHOR, READY_ANCHOR):
        if body.count(anchor) != 1:
            raise TransformError("preserved state-machine anchor drift")
    original_method = _methods(original, item["required_method"])[0]
    if body != original_method.replace("    " + CALLBACK, "    " + MARKER):
        raise TransformError("delivery-ACK method changed beyond callback suppression")
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
               "hooks": ["sms_delivery_ack_android13_abi_guard"],
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
            try:
                report_abs.unlink()
            except FileNotFoundError:
                pass
        shutil.rmtree(temp_overlay, ignore_errors=True)
        try:
            temp_report.unlink()
        except FileNotFoundError:
            pass
        raise
    try:
        temp_report.unlink()
    except OSError:
        pass
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
