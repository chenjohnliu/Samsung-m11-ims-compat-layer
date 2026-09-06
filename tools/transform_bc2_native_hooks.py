#!/usr/bin/env python3
"""Emit a three-file BC2 smali overlay from a private decoded input tree."""

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


TRANSFORMATION_ID = "BC2-modern-bridge-native-hooks"
EXPECTED_PATHS = {
    "com/sec/internal/google/GoogleImsService.smali",
    "com/sec/internal/google/ImsCallSessionImpl.smali",
    "com/sec/internal/google/ImsNotifier.smali",
}


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
    if not isinstance(targets, list) or len(targets) != 3:
        raise TransformError("contract must contain exactly three targets")
    by_path = {item.get("path"): item for item in targets if isinstance(item, dict)}
    if set(by_path) != EXPECTED_PATHS or len(by_path) != len(targets):
        raise TransformError("unexpected or duplicate target paths")
    # Pin the complete public contract shape. This prevents a locally edited
    # contract from turning the transformer into a general stock-code copier.
    expected_keys = {
        "com/sec/internal/google/GoogleImsService.smali":
            {"path", "class", "class_access", "super", "required_fields", "method_anchor", "hooks"},
        "com/sec/internal/google/ImsCallSessionImpl.smali":
            {"path", "class", "class_access", "super", "target_method", "target_access", "anchor", "hook",
             "expected_anchor", "expected_pre", "expected_post"},
        "com/sec/internal/google/ImsNotifier.smali":
            {"path", "class", "class_access", "super", "target_method", "target_access", "anchor", "hook",
             "minimum_locals", "expected_anchor", "expected_pre", "expected_post"},
    }
    for name, item in by_path.items():
        if set(item) != expected_keys[name]:
            raise TransformError(f"malformed target contract: {name}")
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != name:
            raise TransformError("unsafe target path")
    # Validate immutable semantic values against the implementation below.
    service = by_path["com/sec/internal/google/GoogleImsService.smali"]
    if (service["class"], service["class_access"], service["super"], service["method_anchor"]) != (
            "Lcom/sec/internal/google/GoogleImsService;",
            ["public"], "Lcom/android/ims/internal/IImsService$Stub;", "# direct methods"):
        raise TransformError("service identity drift")
    expected_fields = [
        {"identity": "mInstance:Lcom/sec/internal/google/GoogleImsService;", "access": ["static"]},
        {"identity": "mVolteServiceModule:Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;", "access": []},
    ]
    if service["required_fields"] != expected_fields:
        raise TransformError("service field contract drift")
    expected_hooks = [
        {"id": "service_ready_accessor", "method": "getInstanceIfReady()Lcom/sec/internal/google/GoogleImsService;", "expected_pre": 0, "expected_post": 1},
        {"id": "incoming_identity_accessor", "method": "getModernIncomingIdentity(I)Landroid/os/IBinder;", "expected_pre": 0, "expected_post": 1},
    ]
    if service["hooks"] != expected_hooks:
        raise TransformError("service hook contract drift")
    session = by_path["com/sec/internal/google/ImsCallSessionImpl.smali"]
    notifier = by_path["com/sec/internal/google/ImsNotifier.smali"]
    if session != {
        "path": session["path"], "class": "Lcom/sec/internal/google/ImsCallSessionImpl;", "class_access": ["public"],
        "super": "Lcom/android/ims/internal/IImsCallSession$Stub;",
        "target_method": "<init>(Landroid/telephony/ims/ImsCallProfile;Lcom/sec/ims/volte2/IImsCallSession;Landroid/telephony/ims/aidl/IImsCallSessionListener;Lcom/sec/internal/google/GoogleImsService;)V",
        "target_access": ["public", "constructor"],
        "anchor": "iput-object p3, p0, Lcom/sec/internal/google/ImsCallSessionImpl;->mListener:Landroid/telephony/ims/aidl/IImsCallSessionListener;",
        "hook": "ModernCallRelay.constructionListener(Landroid/telephony/ims/aidl/IImsCallSessionListener;)Landroid/telephony/ims/aidl/IImsCallSessionListener;",
        "expected_anchor": 1, "expected_pre": 0, "expected_post": 1}:
        raise TransformError("session hook contract drift")
    if notifier != {
        "path": notifier["path"], "class": "Lcom/sec/internal/google/ImsNotifier;", "class_access": ["public"],
        "super": "Ljava/lang/Object;", "target_method": "onIncomingCall(II)V",
        "target_access": ["public"],
        "anchor": "invoke-interface {v4, p2, v5}, Lcom/android/ims/internal/ISecImsMmTelEventListener;->onIncomingCall(ILandroid/os/Bundle;)V",
        "hook": "ModernVoiceContext.onIncoming(IILandroid/os/Bundle;)Z",
        "minimum_locals": 7, "expected_anchor": 1, "expected_pre": 0, "expected_post": 1}:
        raise TransformError("notifier hook contract drift")
    return raw


METHOD_RE = re.compile(r"(?ms)^\.method\s+[^\r\n]*?\s(?P<sig>[^\s]+\([^\r\n]*?\)\S+)\r?\n.*?^\.end method\s*$")


def _method_spans(text: str, signature: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(0)) for m in METHOD_RE.finditer(text)
            if m.group("sig") == signature]


def _assert_identity(text: str, spec: dict) -> None:
    class_rows = [line.split() for line in text.splitlines()
                  if line.startswith(".class ") and line.split()[-1] == spec["class"]]
    if len(class_rows) != 1 or class_rows[0][1:-1] != spec["class_access"]:
        raise TransformError(f"class identity drift: {spec['path']}")
    if len(re.findall(r"(?m)^\.super\s+" + re.escape(spec["super"]) + r"\s*$", text)) != 1:
        raise TransformError(f"superclass drift: {spec['path']}")


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _service(text: str, spec: dict) -> tuple[str, list[str]]:
    _assert_identity(text, spec)
    for field in spec["required_fields"]:
        hits = [line for line in text.splitlines()
                if line.startswith(".field ") and line.split()[-1] == field["identity"]]
        if len(hits) != 1 or hits[0].split()[1:-1] != field["access"]:
            raise TransformError(f"required field drift: {field['identity']}")
    existing = [_method_spans(text, hook["method"]) for hook in spec["hooks"]]
    if any(existing):
        state = "already applied" if all(len(x) == 1 for x in existing) else "partially applied"
        raise TransformError(f"service hooks are {state}")
    partial_markers = ("getInstanceIfReady()", "getModernIncomingIdentity(I)",
                       ":bc2_absent")
    if any(marker in text for marker in partial_markers):
        raise TransformError("service hooks are partially applied")
    marker = spec["method_anchor"]
    if text.count(marker) != 1:
        raise TransformError("service method anchor occurrence drift")
    nl = _newline(text)
    block = nl.join([
        ".method public static declared-synchronized getInstanceIfReady()Lcom/sec/internal/google/GoogleImsService;",
        "    .locals 1", "", "    sget-object v0, Lcom/sec/internal/google/GoogleImsService;->mInstance:Lcom/sec/internal/google/GoogleImsService;",
        "", "    return-object v0", ".end method", "",
        ".method public getModernIncomingIdentity(I)Landroid/os/IBinder;", "    .locals 2", "",
        "    iget-object v0, p0, Lcom/sec/internal/google/GoogleImsService;->mVolteServiceModule:Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;",
        "", "    if-eqz v0, :bc2_absent", "",
        "    invoke-interface {v0, p1}, Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getSessionByCallId(I)Lcom/sec/ims/volte2/IImsCallSession;",
        "", "    move-result-object v0", "", "    if-eqz v0, :bc2_absent", "",
        "    invoke-interface {v0}, Lcom/sec/ims/volte2/IImsCallSession;->asBinder()Landroid/os/IBinder;",
        "", "    move-result-object v1", "", "    return-object v1", "", "    :bc2_absent",
        "    const/4 v0, 0x0", "", "    return-object v0", ".end method", ""
    ])
    return text.replace(marker + nl, marker + nl + block, 1), [h["id"] for h in spec["hooks"]]


def _replace_in_method(text: str, spec: dict, kind: str) -> tuple[str, list[str]]:
    _assert_identity(text, spec)
    spans = _method_spans(text, spec["target_method"])
    if len(spans) != 1:
        raise TransformError(f"target method occurrence drift: {spec['target_method']}")
    start, end, body = spans[0]
    method_header = body.splitlines()[0].split()
    if method_header[1:-1] != spec["target_access"]:
        raise TransformError(f"{kind} target method access drift")
    hook_owner = "Lcom/sec/internal/google/ModernCallRelay;->constructionListener" if kind == "session" else "Lcom/sec/internal/google/ModernVoiceContext;->onIncoming"
    hook_count = body.count(hook_owner)
    any_count = text.count(hook_owner)
    if any_count:
        state = "already applied" if hook_count == 1 and any_count == 1 else "partially applied or outside allowlisted method"
        raise TransformError(f"{kind} hook is {state}")
    anchor = spec["anchor"]
    if body.count(anchor) != spec["expected_anchor"] or text.count(anchor) != spec["expected_anchor"]:
        raise TransformError(f"{kind} anchor occurrence drift")
    nl = _newline(text)
    indent = "    "
    if kind == "session":
        insertion = nl.join([
            "invoke-static {p3}, Lcom/sec/internal/google/ModernCallRelay;->constructionListener(Landroid/telephony/ims/aidl/IImsCallSessionListener;)Landroid/telephony/ims/aidl/IImsCallSessionListener;",
            "    move-result-object p3", ""
        ])
    else:
        locals_hits = re.findall(r"(?m)^\s*\.locals\s+(\d+)\s*$", body)
        if len(locals_hits) != 1 or int(locals_hits[0]) < spec["minimum_locals"]:
            raise TransformError("notifier register/local drift")
        if ":bc2_incoming_done" in text:
            raise TransformError("notifier label collision or partial application")
        insertion = nl.join([
            "invoke-static {p1, p2, v5}, Lcom/sec/internal/google/ModernVoiceContext;->onIncoming(IILandroid/os/Bundle;)Z",
            "    move-result v6", "    if-nez v6, :bc2_incoming_done",
            "    if-eqz v4, :bc2_incoming_done", ""
        ])
    new_body = body.replace(indent + anchor, indent + insertion + indent + anchor, 1)
    if kind == "notifier":
        new_body = new_body.replace(indent + anchor, indent + anchor + nl + "    :bc2_incoming_done", 1)
    return text[:start] + new_body + text[end:], ["constructor_listener" if kind == "session" else "incoming_dispatch"]


def _post_validate(original: str, rendered: str, spec: dict, hooks: list[str]) -> None:
    _assert_identity(rendered, spec)
    if spec["path"].endswith("GoogleImsService.smali"):
        for hook in spec["hooks"]:
            if len(_method_spans(rendered, hook["method"])) != hook["expected_post"]:
                raise TransformError("service post-validation failed")
    elif spec["path"].endswith("ImsCallSessionImpl.smali"):
        spans = _method_spans(rendered, spec["target_method"])
        if len(spans) != 1 or spans[0][2].count("Lcom/sec/internal/google/ModernCallRelay;->constructionListener") != 1:
            raise TransformError("session post-validation failed")
    else:
        spans = _method_spans(rendered, spec["target_method"])
        body = spans[0][2] if len(spans) == 1 else ""
        if (body.count("Lcom/sec/internal/google/ModernVoiceContext;->onIncoming") != 1 or
                body.count(":bc2_incoming_done") != 3 or body.count(spec["anchor"]) != 1):
            raise TransformError("notifier post-validation failed")
    if original == rendered:
        raise TransformError("transformation produced no change")


def _safe_inputs(root: Path, specs: list[dict]) -> tuple[Path, dict[str, Path]]:
    if root.is_symlink() or not root.is_dir():
        raise TransformError("input root must be a non-symlink directory")
    resolved = root.resolve(strict=True)
    paths = {}
    for spec in specs:
        candidate = resolved.joinpath(*PurePosixPath(spec["path"]).parts)
        if candidate.is_symlink() or not candidate.is_file():
            raise TransformError(f"target must be a regular non-symlink file: {spec['path']}")
        actual = candidate.resolve(strict=True)
        try:
            actual.relative_to(resolved)
        except ValueError as exc:
            raise TransformError("target escapes input root") from exc
        # Reject symlinked parent components too.
        cursor = resolved
        for part in PurePosixPath(spec["path"]).parts[:-1]:
            cursor /= part
            if cursor.is_symlink():
                raise TransformError("symlinked target parent is forbidden")
        paths[spec["path"]] = actual
    return resolved, paths


def _tree_bytes(root: Path, paths: set[str]) -> dict[str, bytes] | None:
    if root.is_symlink() or not root.is_dir():
        return None
    found = {}
    found_dirs = set()
    for item in root.rglob("*"):
        if item.is_symlink() or (item.is_file() and item.relative_to(root).as_posix() not in paths):
            return None
        if item.is_dir():
            found_dirs.add(item.relative_to(root).as_posix())
        if item.is_file():
            found[item.relative_to(root).as_posix()] = item.read_bytes()
    expected_dirs = set()
    for name in paths:
        parent = PurePosixPath(name).parent
        while parent != PurePosixPath("."):
            expected_dirs.add(parent.as_posix())
            parent = parent.parent
    return found if set(found) == paths and found_dirs == expected_dirs else None


def transform(contract_path: Path, source_root: Path, overlay: Path, report: Path,
              allow_identical: bool = False) -> dict:
    contract = load_contract(contract_path)
    specs = contract["targets"]
    source_abs, inputs = _safe_inputs(source_root, specs)
    if overlay.is_symlink() or report.is_symlink():
        raise TransformError("output and report must not be symlinks")
    if overlay.parent.is_symlink() or report.parent.is_symlink() or not overlay.parent.is_dir() or not report.parent.is_dir():
        raise TransformError("output parents must be existing non-symlink directories")
    overlay_abs = overlay.parent.resolve(strict=True) / overlay.name
    report_abs = report.parent.resolve(strict=True) / report.name
    if overlay_abs == report_abs or overlay_abs in inputs.values() or report_abs in inputs.values():
        raise TransformError("input, overlay and report paths must be distinct")
    if source_abs == overlay_abs or source_abs in overlay_abs.parents or source_abs == report_abs or source_abs in report_abs.parents:
        raise TransformError("overlay and report must be outside the private input tree")
    rendered: dict[str, bytes] = {}
    report_files = []
    for spec in specs:
        data = inputs[spec["path"]].read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransformError(f"target is not UTF-8: {spec['path']}") from exc
        if spec["path"].endswith("GoogleImsService.smali"):
            updated, hooks = _service(text, spec)
        elif spec["path"].endswith("ImsCallSessionImpl.smali"):
            updated, hooks = _replace_in_method(text, spec, "session")
        else:
            updated, hooks = _replace_in_method(text, spec, "notifier")
        _post_validate(text, updated, spec, hooks)
        out = updated.encode("utf-8")
        rendered[spec["path"]] = out
        report_files.append({"target": spec["path"], "hooks": hooks,
                             "input_sha256": hashlib.sha256(data).hexdigest(),
                             "output_sha256": hashlib.sha256(out).hexdigest()})
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID,
               "changed": True, "files": report_files}
    report_data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if overlay.exists() or report.exists():
        if allow_identical and report.is_file() and report.read_bytes() == report_data and _tree_bytes(overlay, EXPECTED_PATHS) == rendered:
            result = dict(payload); result["changed"] = False
            return result
        raise TransformError("refusing to overwrite existing overlay or report")
    temp_overlay = Path(tempfile.mkdtemp(prefix=f".{overlay.name}.", dir=overlay.parent))
    fd, temp_report_name = tempfile.mkstemp(prefix=f".{report.name}.", suffix=".tmp", dir=report.parent)
    os.close(fd)
    temp_report = Path(temp_report_name)
    report_published = False
    try:
        for name, data in rendered.items():
            target = temp_overlay.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        with temp_report.open("wb") as handle:
            handle.write(report_data); handle.flush(); os.fsync(handle.fileno())
        os.link(temp_report, report_abs)
        report_published = True
        os.rename(temp_overlay, overlay_abs)
    except BaseException:
        if report_published:
            try: report_abs.unlink()
            except FileNotFoundError: pass
        shutil.rmtree(temp_overlay, ignore_errors=True)
        try: temp_report.unlink()
        except FileNotFoundError: pass
        raise
    # Both public names now exist. Failure to remove the private same-directory
    # report temp must not roll back only one half of the committed pair.
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
