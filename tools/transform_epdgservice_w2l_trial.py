#!/usr/bin/env python3
"""Apply the fail-closed M11 active-call AP-assist W2L trial transform."""

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


TRANSFORMATION_ID = "EC2-active-w2l-trial"
METHOD_RE = re.compile(r"(?ms)^\.method\s+(?P<header>[^\r\n]+)\r?\n.*?^\.end method\s*$")
ASSET = Path(__file__).with_name("epdg_w2l_trial") / "M11qW2LTrial.smali"

TARGETS = {
    "com/sec/epdg/IntentReceiver.smali": {
        "input": "09195d7295dd5e50b21d44f12f6ce1d2b275c71be83181a94533ea4e8eecf826",
        "output": "faca368c072cf8c2747e392c66a9c7e9ff8ed518b9242ad5195ebe2a32fd5ed7",
        "redecoded": "28137d1d9b4cf3d6bd3844bf7e27dddc10d7c3cf4224315d5f3e5ddc9f658c84",
        "methods": ["public initializeIntentReceiver()V", "public processSlowPath(Ljava/lang/Object;)V"],
        "operations": ["register_wifi_state_changed", "dispatch_disabling_and_disabled"],
    },
    "com/sec/epdg/EpdgSubScription.smali": {
        "input": "de192b5e2f1b3452b12febb2d5e704b06d7070159513a9ac32a399c62d82dfeb",
        "output": "eada33cdce9a9080354cdc29a6614239c1d6dd0793a06dfe3bb5aa31fa975446",
        "redecoded": "7d571b556755aece2e80a706d394cd6955af07659d982fbdaa010adca5b0b128",
        "methods": ["protected retryW2LHandoverIfRequired(Ljava/lang/String;)Z", "protected notifyQualifiedNetworksChange()V", "protected notifyQualifiedNetworksChange(Ljava/lang/String;I)V"],
        "operations": ["route_weak_rssi_to_ap_assist_qn", "pin_only_ims_before_qn_publication"],
    },
    "com/sec/epdg/EpdgHandler.smali": {
        "input": "ba5829cf1483f7a0afe0ff7a7016163ea909a5d1c600d3e6b25e44332772bb53",
        "output": "2791c03a8a6416f2a95d618fa8fdb7ad7ed706fe591c45ed10d1dec6ef83e68b",
        "redecoded": "13826f02083391bd8dfba325887c0f3d912b9f0b8cb7ac0dedfc3244f318b5ac",
        "methods": ["private handleCallStatusChange(Landroid/os/Message;)V"],
        "operations": ["cleanup_trial_on_call_idle"],
    },
    "com/sec/epdg/IPSecDataConnSM$W2MInProgressState.smali": {
        "input": "e9dca03fb6b0b356d81bb4db0e011b21474815c03c1f7fc6c1b95b7e86bca83c",
        "output": "4369bfcd40483782aa6d86f87035b62dc74af82f8eb3b3ce37dd0251dd0c73c0",
        "redecoded": "3411562da70ecb64468a8fd9ff35cd36f9f9b2534ec7212509740a27f8d7d2fd",
        "methods": [
            "public enter()V",
            "public exit()V",
            "public processMessage(Landroid/os/Message;)Z",
        ],
        "operations": ["attach_trial_transaction", "defer_same_cid_source_msg7_once", "cleanup_on_state_exit"],
    },
    "com/sec/epdg/apassist/IwlanService/IwlanDataService$IwlanDataServiceProvider.smali": {
        "input": "ba5fec14a3109bdbb5f22610133ffd62b545ef72be024b46b94fb7a2226cbe32",
        "output": "13ed426bc7c96e222b2bc788b92729694a1e0d47f23c4d3e18058ae018e7b986",
        "redecoded": "13ed426bc7c96e222b2bc788b92729694a1e0d47f23c4d3e18058ae018e7b986",
        "methods": ["public cancelHandover(ILandroid/telephony/data/DataServiceCallback;)V"],
        "operations": ["cleanup_on_framework_cancel_or_timeout"],
    },
}

ADDITIONS = {
    "com/sec/epdg/M11qW2LTrial.smali": {
        "output": "a2dc03ae458ca5db9aa7f40f51d8dd84122ad3353a180287fbd69daf9a9bbfeb",
        "redecoded": "8cb5a87220d630c99e3920c75302e5df4a1cb973883f5fac31749def6e9db4bb",
        "operations": ["fail_closed_guard", "transient_qn_pin", "idempotent_transaction_cleanup", "diagnostic_markers"],
    }
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _methods(text: str, signature: str) -> list[str]:
    return [m.group(0) for m in METHOD_RE.finditer(text) if m.group("header") == signature]


def _one(text: str, signature: str) -> str:
    found = _methods(text, signature)
    if len(found) != 1:
        raise TransformError(f"required method drift: {signature}")
    return found[0]


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise TransformError(f"anchor drift: {label}")
    return text.replace(old, new, 1)


def _patch_intent_receiver(text: str) -> str:
    sig = "public initializeIntentReceiver()V"
    original = _one(text, sig)
    anchor = '''    .line 92
    :cond_2
    const-string v2, "android.intent.action.ACTION_SHUTDOWN"
'''
    insertion = '''    .line 92
    :cond_2
    const-string v2, "android.net.wifi.WIFI_STATE_CHANGED"

    invoke-virtual {v0, v2}, Landroid/content/IntentFilter;->addAction(Ljava/lang/String;)V

    const-string v2, "android.intent.action.ACTION_SHUTDOWN"
'''
    text = text.replace(original, _replace_once(original, anchor, insertion, "wifi state registration"))

    sig = "public processSlowPath(Ljava/lang/Object;)V"
    original = _one(text, sig)
    anchor = '''    .local v0, "intent":Landroid/content/Intent;
    iget-object v1, p0, Lcom/sec/epdg/IntentReceiver;->TAG:Ljava/lang/String;
'''
    insertion = '''    .local v0, "intent":Landroid/content/Intent;
    invoke-virtual {v0}, Landroid/content/Intent;->getAction()Ljava/lang/String;

    move-result-object v1

    const-string v2, "android.net.wifi.WIFI_STATE_CHANGED"

    invoke-virtual {v2, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    if-eqz v1, :m11q_w2l_continue

    iget-object v1, p0, Lcom/sec/epdg/IntentReceiver;->mContext:Landroid/content/Context;

    iget-object v2, p0, Lcom/sec/epdg/IntentReceiver;->mSubScription:Lcom/sec/epdg/EpdgSubScription;

    iget v3, p0, Lcom/sec/epdg/IntentReceiver;->mPhoneId:I

    iget v4, p0, Lcom/sec/epdg/IntentReceiver;->mSubId:I

    invoke-static {v0, v1, v2, v3, v4}, Lcom/sec/epdg/M11qW2LTrial;->onWifiState(Landroid/content/Intent;Landroid/content/Context;Lcom/sec/epdg/EpdgSubScription;II)V

    return-void

    :m11q_w2l_continue
    iget-object v1, p0, Lcom/sec/epdg/IntentReceiver;->TAG:Ljava/lang/String;
'''
    return text.replace(original, _replace_once(original, anchor, insertion, "wifi state dispatch"))


def _patch_subscription(text: str) -> str:
    sig = "protected retryW2LHandoverIfRequired(Ljava/lang/String;)Z"
    original = _one(text, sig)
    anchor = '''    .line 2875
    :cond_9
    :try_start_0
    iget-object v4, p0, Lcom/sec/epdg/EpdgSubScription;->TAG:Ljava/lang/String;
'''
    insertion = '''    .line 2875
    :cond_9
    const-string v4, "ims"

    invoke-virtual {v4, p1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z

    move-result v4

    if-eqz v4, :m11q_w2l_weak_legacy

    iget v4, p0, Lcom/sec/epdg/EpdgSubScription;->mPhoneId:I

    invoke-static {p0, v4}, Lcom/sec/epdg/M11qW2LTrial;->requestWeak(Lcom/sec/epdg/EpdgSubScription;I)Z

    move-result v4

    if-eqz v4, :m11q_w2l_weak_legacy

    const/4 v0, 0x1

    goto :goto_0

    :m11q_w2l_weak_legacy
    :try_start_0
    iget-object v4, p0, Lcom/sec/epdg/EpdgSubScription;->TAG:Ljava/lang/String;
'''
    text = text.replace(original, _replace_once(original, anchor, insertion, "weak RSSI AP-assist route"))
    sig = "protected notifyQualifiedNetworksChange()V"
    original = _one(text, sig)
    anchor = '''    :cond_a
    new-instance v4, Lcom/sec/epdg/data/DataType/MapconInformation;
'''
    insertion = '''    :cond_a
    iget v4, p0, Lcom/sec/epdg/EpdgSubScription;->mPhoneId:I

    invoke-static {p0, v4, v2}, Lcom/sec/epdg/M11qW2LTrial;->pinResult(Lcom/sec/epdg/EpdgSubScription;ILjava/util/List;)V

    new-instance v4, Lcom/sec/epdg/data/DataType/MapconInformation;
'''
    text = text.replace(original, _replace_once(original, anchor, insertion, "pin IMS before publication"))
    sig = "protected notifyQualifiedNetworksChange(Ljava/lang/String;I)V"
    original = _one(text, sig)
    anchor = '''    .line 2689
    :cond_1
    const/16 v3, 0x12
'''
    insertion = '''    .line 2689
    :cond_1
    iget v3, p0, Lcom/sec/epdg/EpdgSubScription;->mPhoneId:I

    invoke-static {p0, v3, v2}, Lcom/sec/epdg/M11qW2LTrial;->pinResult(Lcom/sec/epdg/EpdgSubScription;ILjava/util/List;)V

    const-string v3, "ims"

    invoke-virtual {v3, p1}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z

    move-result v3

    if-eqz v3, :m11q_w2l_not_ims

    iget v3, p0, Lcom/sec/epdg/EpdgSubScription;->mPhoneId:I

    invoke-static {p0, v3}, Lcom/sec/epdg/M11qW2LTrial;->isPinned(Lcom/sec/epdg/EpdgSubScription;I)Z

    move-result v3

    if-eqz v3, :m11q_w2l_not_ims

    const/16 p2, 0xd

    :m11q_w2l_not_ims
    const/16 v3, 0x12
'''
    return text.replace(original, _replace_once(original, anchor, insertion, "pin direct IMS notification"))


def _patch_handler(text: str) -> str:
    sig = "private handleCallStatusChange(Landroid/os/Message;)V"
    original = _one(text, sig)
    anchor = '''    .line 1042
    :cond_0
    iget v2, p0, Lcom/sec/epdg/EpdgHandler;->mPhoneId:I
'''
    insertion = '''    .line 1042
    :cond_0
    sget-object v2, Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;->CALL_IDLE:Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;

    if-ne v0, v2, :m11q_w2l_not_idle

    iget-object v2, p0, Lcom/sec/epdg/EpdgHandler;->mSubScription:Lcom/sec/epdg/EpdgSubScription;

    iget v3, p0, Lcom/sec/epdg/EpdgHandler;->mPhoneId:I

    invoke-static {v2, v3}, Lcom/sec/epdg/M11qW2LTrial;->onCallIdle(Lcom/sec/epdg/EpdgSubScription;I)V

    :m11q_w2l_not_idle
    iget v2, p0, Lcom/sec/epdg/EpdgHandler;->mPhoneId:I
'''
    return text.replace(original, _replace_once(original, anchor, insertion, "call idle cleanup"))


def _patch_w2m(text: str) -> str:
    sig = "public enter()V"
    original = _one(text, sig)
    anchor = '''    invoke-super {p0}, Lcom/sec/epdg/IPSecDataConnSM$StateBase;->enter()V

    .line 1138
'''
    insertion = '''    invoke-super {p0}, Lcom/sec/epdg/IPSecDataConnSM$StateBase;->enter()V

    iget-object v0, p0, Lcom/sec/epdg/IPSecDataConnSM$W2MInProgressState;->this$0:Lcom/sec/epdg/IPSecDataConnSM;

    invoke-static {v0}, Lcom/sec/epdg/M11qW2LTrial;->onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V

    .line 1138
'''
    text = text.replace(original, _replace_once(original, anchor, insertion, "W2M attach"))

    sig = "public exit()V"
    original = _one(text, sig)
    anchor = '''    invoke-super {p0}, Lcom/sec/epdg/IPSecDataConnSM$StateBase;->exit()V

    .line 1149
'''
    insertion = '''    invoke-super {p0}, Lcom/sec/epdg/IPSecDataConnSM$StateBase;->exit()V

    iget-object v0, p0, Lcom/sec/epdg/IPSecDataConnSM$W2MInProgressState;->this$0:Lcom/sec/epdg/IPSecDataConnSM;

    invoke-static {v0}, Lcom/sec/epdg/M11qW2LTrial;->onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V

    .line 1149
'''
    text = text.replace(original, _replace_once(original, anchor, insertion, "W2M exit cleanup"))

    sig = "public processMessage(Landroid/os/Message;)Z"
    original = _one(text, sig)
    anchor = '''    invoke-super {p0, p1}, Lcom/sec/epdg/IPSecDataConnSM$StateBase;->processMessage(Landroid/os/Message;)Z

    .line 1155
    const/4 v0, 0x0
'''
    insertion = '''    invoke-super {p0, p1}, Lcom/sec/epdg/IPSecDataConnSM$StateBase;->processMessage(Landroid/os/Message;)Z

    iget-object v0, p0, Lcom/sec/epdg/IPSecDataConnSM$W2MInProgressState;->this$0:Lcom/sec/epdg/IPSecDataConnSM;

    invoke-static {v0, p1}, Lcom/sec/epdg/M11qW2LTrial;->deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I

    move-result v0

    if-eqz v0, :m11q_w2l_normal_message

    const/4 v1, 0x1

    if-ne v0, v1, :m11q_w2l_msg7_consumed

    iget-object v0, p0, Lcom/sec/epdg/IPSecDataConnSM$W2MInProgressState;->this$0:Lcom/sec/epdg/IPSecDataConnSM;

    invoke-virtual {v0, p1}, Lcom/sec/epdg/IPSecDataConnSM;->deferMessage(Landroid/os/Message;)V

    :m11q_w2l_msg7_consumed
    return v1

    :m11q_w2l_normal_message
    .line 1155
    const/4 v0, 0x0
'''
    return text.replace(original, _replace_once(original, anchor, insertion, "source msg7 deferral"))


def _patch_data_service(text: str) -> str:
    sig = "public cancelHandover(ILandroid/telephony/data/DataServiceCallback;)V"
    original = _one(text, sig)
    anchor = '''    .line 210
    const/4 v0, 0x0
'''
    insertion = '''    invoke-virtual {p0}, Lcom/sec/epdg/apassist/IwlanService/IwlanDataService$IwlanDataServiceProvider;->getSlotIndex()I

    move-result v0

    invoke-static {v0, p1}, Lcom/sec/epdg/M11qW2LTrial;->onFrameworkCancel(II)V

    .line 210
    const/4 v0, 0x0
'''
    return text.replace(original, _replace_once(original, anchor, insertion, "framework cancel cleanup"))


PATCHERS = {
    "com/sec/epdg/IntentReceiver.smali": _patch_intent_receiver,
    "com/sec/epdg/EpdgSubScription.smali": _patch_subscription,
    "com/sec/epdg/EpdgHandler.smali": _patch_handler,
    "com/sec/epdg/IPSecDataConnSM$W2MInProgressState.smali": _patch_w2m,
    "com/sec/epdg/apassist/IwlanService/IwlanDataService$IwlanDataServiceProvider.smali": _patch_data_service,
}


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
    if raw["source_baseline"] != {"transformation_id": "EC1-epdgservice-android13-compat", "decoded_smali_root": "exact EC1 output"}:
        raise TransformError("source baseline drift")
    target_keys = {"path", "input_sha256", "output_sha256", "redecoded_sha256", "required_methods", "operations"}
    if not isinstance(raw["targets"], list) or len(raw["targets"]) != len(TARGETS):
        raise TransformError("target set drift")
    seen = set()
    for item in raw["targets"]:
        if not isinstance(item, dict) or set(item) != target_keys or item.get("path") in seen:
            raise TransformError("malformed or duplicate target")
        path_key = item["path"]
        rel = PurePosixPath(path_key)
        if rel.is_absolute() or ".." in rel.parts or path_key not in TARGETS:
            raise TransformError("unexpected or unsafe target path")
        spec = TARGETS[path_key]
        if item["redecoded_sha256"] != spec["redecoded"]:
            raise TransformError(f"canonical output contract drift: {path_key}")
        if (item["input_sha256"], item["output_sha256"], item["required_methods"], item["operations"]) != (spec["input"], spec["output"], spec["methods"], spec["operations"]):
            raise TransformError(f"target contract drift: {path_key}")
        seen.add(path_key)
    addition_keys = {"path", "output_sha256", "redecoded_sha256", "operations"}
    if not isinstance(raw["additions"], list) or len(raw["additions"]) != len(ADDITIONS):
        raise TransformError("addition set drift")
    seen_add = set()
    for item in raw["additions"]:
        if not isinstance(item, dict) or set(item) != addition_keys or item.get("path") in seen_add:
            raise TransformError("malformed or duplicate addition")
        path_key = item["path"]
        rel = PurePosixPath(path_key)
        if rel.is_absolute() or ".." in rel.parts or path_key not in ADDITIONS:
            raise TransformError("unexpected or unsafe addition path")
        spec = ADDITIONS[path_key]
        if item["redecoded_sha256"] != spec["redecoded"]:
            raise TransformError(f"canonical addition contract drift: {path_key}")
        if (item["output_sha256"], item["operations"]) != (spec["output"], spec["operations"]):
            raise TransformError(f"addition contract drift: {path_key}")
        seen_add.add(path_key)
    return raw


def _post(original: str, updated: str, spec: dict) -> None:
    if original == updated:
        raise TransformError("transform made no change")
    if _sha(updated.encode("utf-8")) != spec["output"]:
        raise TransformError("post-transform hash drift")
    changed = set(spec["methods"])
    for match in METHOD_RE.finditer(original):
        signature = match.group("header")
        found = _methods(updated, signature)
        if len(found) != 1:
            raise TransformError(f"method set drift: {signature}")
        if signature not in changed and found[0] != match.group(0):
            raise TransformError(f"unrelated method changed: {signature}")


def transform(contract_path: Path, source_root: Path, overlay: Path, report: Path) -> dict:
    contract = load_contract(contract_path)
    if source_root.is_symlink() or not source_root.is_dir():
        raise TransformError("input root must be a non-symlink directory")
    root = source_root.resolve(strict=True)
    outputs = []
    report_files = []
    for item in contract["targets"]:
        path_key = item["path"]
        source = root.joinpath(*PurePosixPath(path_key).parts)
        if source.is_symlink() or not source.is_file():
            raise TransformError(f"target must be a regular non-symlink file: {path_key}")
        data = source.read_bytes()
        spec = TARGETS[path_key]
        digest = _sha(data)
        if digest == spec["output"]:
            raise TransformError(f"already applied: {path_key}")
        if digest != spec["input"]:
            raise TransformError(f"input hash drift: {path_key}")
        text = data.decode("utf-8")
        for signature in spec["methods"]:
            _one(text, signature)
        updated = PATCHERS[path_key](text)
        _post(text, updated, spec)
        output = updated.encode("utf-8")
        outputs.append((path_key, output))
        report_files.append({"target": path_key, "kind": "modified", "operations": spec["operations"], "input_sha256": digest, "output_sha256": _sha(output)})
    asset_data = ASSET.read_bytes()
    for item in contract["additions"]:
        path_key = item["path"]
        spec = ADDITIONS[path_key]
        if _sha(asset_data) != spec["output"]:
            raise TransformError(f"addition asset hash drift: {path_key}")
        if root.joinpath(*PurePosixPath(path_key).parts).exists():
            raise TransformError(f"addition already exists: {path_key}")
        outputs.append((path_key, asset_data))
        report_files.append({"target": path_key, "kind": "added", "operations": spec["operations"], "input_sha256": None, "output_sha256": _sha(asset_data)})
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID, "changed": True, "files": report_files}
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
        for path_key, data in outputs:
            target = temp_overlay.joinpath(*PurePosixPath(path_key).parts)
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
