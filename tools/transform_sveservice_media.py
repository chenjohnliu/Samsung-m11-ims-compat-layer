#!/usr/bin/env python3
"""Apply the M11q SVE loader and retained media diagnostics fail-closed."""

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


TRANSFORMATION_ID = "SV1-sveservice-media-compat"
JNI_PATH = "com/samsung/sve/sveJNI.smali"
IMPL_PATH = "com/sec/sve/service/sve/SecVideoEngineImpl.smali"
EXPECTED_PATHS = {JNI_PATH, IMPL_PATH}
JNI_OWNER = "Lcom/samsung/sve/sveJNI;"
JNI_SUPER = "Ljava/lang/Object;"
IMPL_OWNER = "Lcom/sec/sve/service/sve/SecVideoEngineImpl;"
IMPL_SUPER = "Lcom/sec/sve/ISecVideoEngineService$Stub;"
CLINIT = "static constructor <clinit>()V"
CREATE = "public saeCreateChannel(IILjava/lang/String;ILjava/lang/String;IIILjava/lang/String;ZZ)I"
START = "public saeStartChannel(IIZ)I"
METHOD_RE = re.compile(r"(?ms)^\.method\s+(?P<header>[^\r\n]+)\r?\n.*?^\.end method\s*$")

EXPECTED_ARTIFACT = {
    "stock_apk_sha256": "5066ebdbd2dc8d5ff8da613f8b0f63b1d7e0408f3732b889719179d2bc1e33ab",
    "stock_apk_size": 634428,
    "stock_dex_sha256": "630ff3e440b8199fb9037bd3a56585573a724c83f548e6754cdc4dbad64fa804",
    "runtime_reference_apk_sha256": "5293755ea74848a8e8ba311ecbef53cc10c1af588857d98ef9d6dbad3b5cd1be",
    "runtime_reference_dex_sha256": "39d848a267da1c54ff73d1d7f06b2c8cc6a6a9f743a97ced4a3cf944237fff5d",
}

EXPECTED_TARGETS = {
    JNI_PATH: {
        "class": JNI_OWNER,
        "class_access": ["public"],
        "super": JNI_SUPER,
        "input_sha256": "4536e9fa48d0407dd700b2cd26725366df62044234a47f9ff27d0a94fbf1ced4",
        "output_sha256": "e4babeae0c6c25f6deb1444168f4576a2888dcad41b7bf7eb95cdb1e5c31d0dc",
        "methods": [{
            "signature": CLINIT,
            "input_sha256": "8b4256f81a4bcd3e1f7c8a10fd1f60fce8632a0e78c667602081a6f1d375000b",
            "output_sha256": "e09d15daa5abac5e59ad8fc9904bc939b713f2272a2778a478ac9694d24ca360",
            "anchor_count": 1,
            "invariant": "compat_loader_precedes_svejni",
        }],
    },
    IMPL_PATH: {
        "class": IMPL_OWNER,
        "class_access": ["public"],
        "super": IMPL_SUPER,
        "input_sha256": "237ace851c3ccfcb90b01808d33e00587b8a126e69cedc2ee0ba6e1d4e9487dc",
        "output_sha256": "4349b17d37780f8b3e38e6b062af63b8eed8b92910b3abdfb198ce21e3c8ccb1",
        "methods": [{
            "signature": CREATE,
            "input_sha256": "1e6c2725582e7aec9c56883de82a9f85a6999557a965575be7a32492e0f17b20",
            "output_sha256": "d7f823c3f81d6453536d991598d8407c2e2d2652a796de785070b5069009b0d4",
            "anchor_count": 2,
            "invariant": "single_entry_and_return_diagnostic",
        }, {
            "signature": START,
            "input_sha256": "489e7836d2fb07d310d611079c160dce40d8811c9e25fd72f8ae91410b80bbf2",
            "output_sha256": "38486ef37891ff45b1322b36f3d8a669e3cb6544379391bd785cc6cef3a83a47",
            "anchor_count": 3,
            "invariant": "expanded_locals_and_single_entry_and_return_diagnostic",
        }],
    },
}

LOAD_SVEJNI = (
    '    const-string v0, "svejni"\n\n'
    '    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V'
)
LOAD_COMPAT = (
    '    const-string v0, "m11q_sve_compat"\n\n'
    '    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\n\n'
)
DIAG_TAG = 'const-string v0, "M11qSveDiag"'
CREATE_NATIVE = (
    "    invoke-virtual/range {v0 .. v11}, Lcom/samsung/sve/sveJNI;"
    "->sveJNISAE_CreateChannel(IILjava/lang/String;ILjava/lang/String;IIILjava/lang/String;ZZ)I\n\n"
    "    move-result v0"
)
START_NATIVE = (
    "    invoke-virtual {v0, p1, p2, p3}, Lcom/samsung/sve/sveJNI;"
    "->sveJNISAE_StartChannel(IIZ)I\n\n"
    "    move-result v0"
)

CREATE_ENTER = """    const-string v0, "M11qSveDiag"

    new-instance v1, Ljava/lang/StringBuilder;

    invoke-direct {v1}, Ljava/lang/StringBuilder;-><init>()V

    const-string v2, "create enter ch="

    invoke-virtual {v1, v2}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v1

    invoke-virtual {v1, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v1

    invoke-virtual {v1}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v1

    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    move-result v0

"""

CREATE_RETURN = """

    const-string v1, "M11qSveDiag"

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, "create return ch="

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v2

    const-string v3, " rc="

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2, v0}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v1, v2}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    move-result v1"""

START_ENTER = """    const-string v1, "M11qSveDiag"

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, "start enter ch="

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v2

    const-string v3, " dir="

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2, p2}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v1, v2}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    move-result v1

"""

START_RETURN = """

    const-string v1, "M11qSveDiag"

    new-instance v2, Ljava/lang/StringBuilder;

    invoke-direct {v2}, Ljava/lang/StringBuilder;-><init>()V

    const-string v3, "start return ch="

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2, p1}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v2

    const-string v3, " rc="

    invoke-virtual {v2, v3}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2, v0}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    move-result-object v2

    invoke-virtual {v2}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v2

    invoke-static {v1, v2}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    move-result v1"""


def _digest(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _methods(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in METHOD_RE.finditer(text):
        header = match.group("header")
        if header in found:
            raise TransformError(f"duplicate method: {header}")
        found[header] = match.group(0)
    return found


def load_contract(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransformError(f"cannot read contract: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {
            "schema_version", "transformation_id", "artifact", "targets"}:
        raise TransformError("malformed contract")
    if raw["schema_version"] != 1 or raw["transformation_id"] != TRANSFORMATION_ID:
        raise TransformError("unsupported contract identity")
    if raw["artifact"] != EXPECTED_ARTIFACT:
        raise TransformError("artifact contract drift")
    targets = raw["targets"]
    if not isinstance(targets, list) or len(targets) != 2:
        raise TransformError("contract must contain exactly two targets")
    found = {}
    target_keys = {"path", "class", "class_access", "super", "input_sha256",
                   "output_sha256", "methods"}
    method_keys = {"signature", "input_sha256", "output_sha256", "anchor_count",
                   "invariant"}
    for item in targets:
        if not isinstance(item, dict) or set(item) != target_keys:
            raise TransformError("malformed target contract")
        rel = PurePosixPath(item["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() not in EXPECTED_PATHS:
            raise TransformError("unexpected or unsafe target path")
        if item["path"] in found:
            raise TransformError("duplicate target contract")
        if not isinstance(item["methods"], list) or any(
                not isinstance(method, dict) or set(method) != method_keys
                for method in item["methods"]):
            raise TransformError("malformed method contract")
        found[item["path"]] = {key: value for key, value in item.items() if key != "path"}
    if found != EXPECTED_TARGETS:
        raise TransformError("target contract drift")
    return raw


def _identity(text: str, item: dict) -> dict[str, str]:
    rows = [line.split() for line in text.splitlines()
            if line.startswith(".class ") and line.split()[-1] == item["class"]]
    if len(rows) != 1 or rows[0][1:-1] != item["class_access"]:
        raise TransformError("class identity drift")
    if len(re.findall(r"(?m)^\.super\s+" + re.escape(item["super"]) + r"\s*$", text)) != 1:
        raise TransformError("superclass drift")
    methods = _methods(text)
    for required in item["methods"]:
        body = methods.get(required["signature"])
        if body is None or _digest(body) != required["input_sha256"]:
            raise TransformError(f"required method drift: {required['signature']}")
    return methods


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise TransformError(f"{label} anchor drift")
    return text.replace(old, new, 1)


def _update_jni(text: str, methods: dict[str, str]) -> str:
    method = methods[CLINIT]
    if "m11q_sve_compat" in text:
        raise TransformError("SV1 is already or partially applied")
    updated_method = _replace_once(method, LOAD_SVEJNI, LOAD_COMPAT + LOAD_SVEJNI,
                                   "native loader")
    return _replace_once(text, method, updated_method, "clinit method")


def _update_impl(text: str, methods: dict[str, str]) -> str:
    if "M11qSveDiag" in text:
        raise TransformError("SV1 is already or partially applied")
    create = methods[CREATE]
    create = _replace_once(create, "    .line 277\n", CREATE_ENTER + "    .line 277\n",
                           "create entry")
    create = _replace_once(create, CREATE_NATIVE, CREATE_NATIVE + CREATE_RETURN,
                           "create return")
    updated = _replace_once(text, methods[CREATE], create, "create method")

    start = methods[START]
    start = _replace_once(start, "    .locals 1\n", "    .locals 4\n", "start locals")
    start = _replace_once(start, "    .line 284\n", START_ENTER + "    .line 284\n",
                          "start entry")
    start = _replace_once(start, START_NATIVE, START_NATIVE + START_RETURN,
                          "start return")
    return _replace_once(updated, methods[START], start, "start method")


def _post(original: str, updated: str, item: dict) -> None:
    if original == updated or _digest(updated) != item["output_sha256"]:
        raise TransformError("target output hash drift")
    before = _methods(original)
    after = _methods(updated)
    required = {method["signature"]: method for method in item["methods"]}
    if set(before) != set(after):
        raise TransformError("method inventory drift")
    for signature, body in before.items():
        if signature not in required and after[signature] != body:
            raise TransformError(f"unrelated method changed: {signature}")
    for signature, method in required.items():
        if _digest(after[signature]) != method["output_sha256"]:
            raise TransformError(f"method output hash drift: {signature}")
    if item["class"] == JNI_OWNER:
        body = after[CLINIT]
        if body.count("m11q_sve_compat") != 1 or body.count('const-string v0, "svejni"') != 1:
            raise TransformError("loader count drift")
        if body.index("m11q_sve_compat") >= body.index('const-string v0, "svejni"'):
            raise TransformError("compat loader is not first")
    else:
        if after[CREATE].count("M11qSveDiag") != 2 or after[START].count("M11qSveDiag") != 2:
            raise TransformError("diagnostic hook count drift")
        if "    .locals 4\n" not in after[START]:
            raise TransformError("start register count drift")


def transform(contract_path: Path, source_root: Path, overlay: Path, report: Path,
              allow_identical: bool = False) -> dict:
    contract = load_contract(contract_path)
    if source_root.is_symlink() or not source_root.is_dir():
        raise TransformError("input root must be a non-symlink directory")
    root = source_root.resolve(strict=True)
    outputs: dict[str, bytes] = {}
    report_files = []
    for item in contract["targets"]:
        rel = PurePosixPath(item["path"])
        source = root.joinpath(*rel.parts)
        if source.is_symlink() or not source.is_file():
            raise TransformError("target must be a regular non-symlink file")
        data = source.read_bytes()
        if _digest(data) != item["input_sha256"]:
            raise TransformError(f"input hash drift: {item['path']}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransformError("target is not UTF-8") from exc
        methods = _identity(text, item)
        updated = (_update_jni(text, methods) if item["path"] == JNI_PATH
                   else _update_impl(text, methods))
        _post(text, updated, item)
        output = updated.encode("utf-8")
        outputs[item["path"]] = output
        report_files.append({
            "target": item["path"],
            "hooks": (["load_media_compat_before_svejni"] if item["path"] == JNI_PATH
                      else ["trace_sae_create", "trace_sae_start"]),
            "input_sha256": _digest(data),
            "output_sha256": _digest(output),
        })
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID,
               "changed": True, "files": report_files}
    report_data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    if overlay.exists() or report.exists():
        identical = (report.is_file() and report.read_bytes() == report_data and
                     all((overlay.joinpath(*PurePosixPath(path).parts)).is_file() and
                         overlay.joinpath(*PurePosixPath(path).parts).read_bytes() == data
                         for path, data in outputs.items()))
        if allow_identical and identical:
            payload["changed"] = False
            return payload
        raise TransformError("refusing to overwrite existing overlay or report")
    if not overlay.parent.is_dir() or overlay.parent.is_symlink() or \
            not report.parent.is_dir() or report.parent.is_symlink() or report.is_symlink():
        raise TransformError("unsafe output path")
    temp_overlay = Path(tempfile.mkdtemp(prefix=f".{overlay.name}.", dir=overlay.parent))
    fd, temp_name = tempfile.mkstemp(prefix=f".{report.name}.", suffix=".tmp", dir=report.parent)
    os.close(fd)
    temp_report = Path(temp_name)
    published = False
    try:
        for path, data in outputs.items():
            target = temp_overlay.joinpath(*PurePosixPath(path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
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
