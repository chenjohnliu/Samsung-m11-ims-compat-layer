#!/usr/bin/env python3
"""Start Samsung MT VoWiFi audio only after the call reaches ESTABLISHED."""

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


TRANSFORMATION_ID = "BT1-mt-vowifi-post-est-media"
TARGET_PATH = "com/sec/internal/ims/servicemodules/volte2/ImsInCall.smali"
EXPECTED_PATHS = {TARGET_PATH}
EXPECTED_INPUT_SHA256 = "7d1d149c95181a1bcb22b2146b621bcd8fbd5cad5e5f64435a915c00044a1499"
OWNER = "Lcom/sec/internal/ims/servicemodules/volte2/ImsInCall;"
SUPER = "Lcom/sec/internal/ims/servicemodules/volte2/CallState;"
METHOD = "private enter_InCall()V"
ESTABLISHED_ANCHOR = (
    "    invoke-virtual {v4}, "
    "Lcom/sec/internal/ims/servicemodules/volte2/CallStateMachine;"
    "->notifyOnEstablished()V\n"
)
MARKER = "queued SAE audio interface after MT VoWiFi established"
UPDATE_CALL = (
    "    invoke-interface {v4, v5, v6}, "
    "Lcom/sec/internal/interfaces/ims/core/handler/IVolteServiceInterface;"
    "->updateAudioInterface(ILjava/lang/String;)V"
)
METHOD_RE = re.compile(r"(?ms)^\.method\s+(?P<header>[^\r\n]+)\r?\n.*?^\.end method\s*$")

INSERTION = """
    # BT1: Android 13 does not issue Samsung's private changeAudioPath callback
    # for an answered MT call.  Wait for ESTABLISHED so the native AudioSession
    # exists before selecting SAE.
    iget-object v4, p0, Lcom/sec/internal/ims/servicemodules/volte2/ImsInCall;->mCsm:Lcom/sec/internal/ims/servicemodules/volte2/CallStateMachine;

    invoke-virtual {v4}, Lcom/sec/internal/ims/servicemodules/volte2/CallStateMachine;->getPreviousState()Lcom/sec/internal/helper/State;

    move-result-object v4

    iget-object v5, p0, Lcom/sec/internal/ims/servicemodules/volte2/ImsInCall;->mCsm:Lcom/sec/internal/ims/servicemodules/volte2/CallStateMachine;

    iget-object v5, v5, Lcom/sec/internal/ims/servicemodules/volte2/CallStateMachine;->mIncomingCall:Lcom/sec/internal/ims/servicemodules/volte2/ImsIncomingCall;

    if-ne v4, v5, :cond_bt1_mt_media_done

    iget-object v4, p0, Lcom/sec/internal/ims/servicemodules/volte2/ImsInCall;->mRegistration:Lcom/sec/ims/ImsRegistration;

    if-eqz v4, :cond_bt1_mt_media_done

    invoke-virtual {v4}, Lcom/sec/ims/ImsRegistration;->getRegiRat()I

    move-result v4

    const/16 v5, 0x12

    if-ne v4, v5, :cond_bt1_mt_media_done

    iget-object v4, p0, Lcom/sec/internal/ims/servicemodules/volte2/ImsInCall;->mSession:Lcom/sec/internal/ims/servicemodules/volte2/ImsCallSession;

    invoke-virtual {v4}, Lcom/sec/internal/ims/servicemodules/volte2/ImsCallSession;->getCmcType()I

    move-result v4

    if-nez v4, :cond_bt1_mt_media_done

    iget-object v4, p0, Lcom/sec/internal/ims/servicemodules/volte2/ImsInCall;->mSession:Lcom/sec/internal/ims/servicemodules/volte2/ImsCallSession;

    invoke-virtual {v4}, Lcom/sec/internal/ims/servicemodules/volte2/ImsCallSession;->getCallProfile()Lcom/sec/ims/volte2/data/CallProfile;

    move-result-object v4

    invoke-virtual {v4}, Lcom/sec/ims/volte2/data/CallProfile;->getCallType()I

    move-result v4

    const/4 v5, 0x1

    if-ne v4, v5, :cond_bt1_mt_media_done

    iget-object v4, p0, Lcom/sec/internal/ims/servicemodules/volte2/ImsInCall;->mVolteSvcIntf:Lcom/sec/internal/interfaces/ims/core/handler/IVolteServiceInterface;

    iget-object v5, p0, Lcom/sec/internal/ims/servicemodules/volte2/ImsInCall;->mRegistration:Lcom/sec/ims/ImsRegistration;

    invoke-virtual {v5}, Lcom/sec/ims/ImsRegistration;->getHandle()I

    move-result v5

    const-string v6, "SAE"

    invoke-interface {v4, v5, v6}, Lcom/sec/internal/interfaces/ims/core/handler/IVolteServiceInterface;->updateAudioInterface(ILjava/lang/String;)V

    const-string v4, "M11qMtMedia"

    const-string v5, "queued SAE audio interface after MT VoWiFi established"

    invoke-static {v4, v5}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    :cond_bt1_mt_media_done
""".lstrip("\n")


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
            "required_method", "established_anchor_count", "inserted_hook_count"}
    if set(item) != keys:
        raise TransformError("malformed target contract")
    rel = PurePosixPath(item["path"])
    if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != TARGET_PATH:
        raise TransformError("unexpected or unsafe target path")
    identity = (OWNER, ["public"], SUPER, METHOD, 1, 1)
    found = (item["class"], item["class_access"], item["super"],
             item["required_method"], item["established_anchor_count"],
             item["inserted_hook_count"])
    if found != identity or item["input_sha256"] != EXPECTED_INPUT_SHA256:
        raise TransformError("target identity or input hash contract drift")
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
    if method.count(ESTABLISHED_ANCHOR) != item["established_anchor_count"]:
        raise TransformError("ESTABLISHED anchor drift")
    if MARKER in text or "cond_bt1_mt_media_done" in text:
        raise TransformError("BT1 is already or partially applied")
    return method


def _updated(text: str, method: str) -> str:
    replacement = ESTABLISHED_ANCHOR + "\n" + INSERTION
    updated_method = method.replace(ESTABLISHED_ANCHOR, replacement)
    if updated_method == method or updated_method.count(MARKER) != 1:
        raise TransformError("BT1 insertion failed")
    return text.replace(method, updated_method)


def _post(original: str, updated: str, item: dict) -> None:
    methods = _methods(updated, item["required_method"])
    if original == updated or len(methods) != 1:
        raise TransformError("BT1 post-state drift")
    body = methods[0]
    if body.count(MARKER) != item["inserted_hook_count"] or body.count(UPDATE_CALL) != 1:
        raise TransformError("BT1 hook count drift")
    if body.index(ESTABLISHED_ANCHOR) >= body.index(UPDATE_CALL):
        raise TransformError("SAE update is not post-ESTABLISHED")
    for anchor in ("->mIncomingCall:", "->getRegiRat()I", "const/16 v5, 0x12",
                   "->getCmcType()I", "->getCallType()I", 'const-string v6, "SAE"'):
        if INSERTION.count(anchor) != 1 or anchor not in body:
            raise TransformError(f"BT1 gate drift: {anchor}")
    expected = _methods(original, item["required_method"])[0].replace(
        ESTABLISHED_ANCHOR, ESTABLISHED_ANCHOR + "\n" + INSERTION)
    if body != expected:
        raise TransformError("enter_InCall changed beyond BT1 insertion")
    for match in METHOD_RE.finditer(original):
        if match.group("header") != item["required_method"]:
            found = _methods(updated, match.group("header"))
            if len(found) != 1 or found[0] != match.group(0):
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
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != item["input_sha256"]:
        raise TransformError("input hash drift")
    text = data.decode("utf-8")
    method = _identity(text, item)
    updated = _updated(text, method)
    _post(text, updated, item)
    output = updated.encode("utf-8")
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID,
               "changed": True, "files": [{"target": TARGET_PATH,
               "hooks": ["mt_vowifi_post_established_sae"],
               "input_sha256": hashlib.sha256(data).hexdigest(),
               "output_sha256": hashlib.sha256(output).hexdigest()}]}
    report_data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    if overlay.exists() or report.exists():
        target = overlay.joinpath(*PurePosixPath(TARGET_PATH).parts)
        if allow_identical and report.is_file() and target.is_file() \
                and report.read_bytes() == report_data and target.read_bytes() == output:
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
        os.link(temp_report, report.resolve(strict=False))
        published = True
        os.rename(temp_overlay, overlay.resolve(strict=False))
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
    parser.add_argument("--allow-identical", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = transform(args.contract, args.input_smali_root, args.output_overlay,
                           args.report, args.allow_identical)
    except (OSError, UnicodeError, TransformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
