#!/usr/bin/env python3
"""Apply the fail-closed M11 ePDG Android-13 compatibility transform."""

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


TRANSFORMATION_ID = "EC1-epdgservice-android13-compat"
METHOD_RE = re.compile(r"(?ms)^\.method\s+(?P<header>[^\r\n]+)\r?\n.*?^\.end method\s*$")

TARGETS = {
    "com/sec/epdg/apassist/interfaceController/EpdgInterface.smali": {
        "class": "Lcom/sec/epdg/apassist/interfaceController/EpdgInterface;",
        "access": ["public"], "super": "Ljava/lang/Object;",
        "input": "a0aa1f4f78bd7baab3da7059e00653d5df5b7df21c5545af346e3b787b17b40a",
        "output": "35368da1f9b5f2f9c0536248eac0e173e5732559c1107f01c4e8067467a8e8dc",
        "methods": ["private makeInterfaceUp(Ljava/lang/String;Ljava/util/List;)V"],
        "hooks": ["configure_existing_interface", "configure_ipv6_before_enable"],
    },
    "com/sec/epdg/apassist/IwlanService/EpdgQualifiedNetworksService$EpdgNetworkAvailabilityProvider.smali": {
        "class": "Lcom/sec/epdg/apassist/IwlanService/EpdgQualifiedNetworksService$EpdgNetworkAvailabilityProvider;",
        "access": [], "super": "Landroid/telephony/data/QualifiedNetworksService$NetworkAvailabilityProvider;",
        "input": "f01f8ee3657bb5f1268d95e63ac9892c45a5730faf58c6f350c7ccbe82ca0577",
        "output": "441788ff2737dcb1538e415f125c74f7ed3c5d5f5f90c7a88c21e664ffb26f24",
        "methods": ["private updateHandOverEnabled(I)V"],
        "hooks": ["suppress_unsupported_qns_super_call"],
    },
    "com/sec/epdg/apassist/IwlanService/TelephonyAdapter.smali": {
        "class": "Lcom/sec/epdg/apassist/IwlanService/TelephonyAdapter;",
        "access": ["public"], "super": "Ljava/lang/Object;",
        "input": "c756dda5b36c0911e5f98650d64b149c4ce068b14c47eea4b6d13a81344c3991",
        "output": "4e42dd21529449c91ea3a5bf39e3d9d7e4e865855772aa44a15e2e8fd819d0de",
        "methods": ["private constructor <init>(I)V", "public setupDataCall(ILandroid/telephony/data/DataProfile;ZZILandroid/net/LinkProperties;Landroid/os/Message;)V"],
        "hooks": ["epdg_interface_namespace", "bounded_cid_fallback"],
    },
    "com/sec/epdg/EpdgSubScriptionBase.smali": {
        "class": "Lcom/sec/epdg/EpdgSubScriptionBase;", "access": ["public"],
        "super": "Ljava/lang/Object;", "input": "07934a41834cb131719b9bdefb406c0d5ce5fdb924edee7be51328af33cfdd45",
        "output": "07dbe19aed88ded2708d8ddf3532d43438d4acd564e5559e590f13b1f4cfdc07",
        "methods": ["protected getVowifiSetting()I"], "hooks": ["subscription_wfc_setting"],
    },
    "com/sec/epdg/EpdgUtils.smali": {
        "class": "Lcom/sec/epdg/EpdgUtils;", "access": ["public"], "super": "Ljava/lang/Object;",
        "input": "fb7da509678f5c95076d59a4aeff9cf72272ac4d367124490f8d4a459b98123d",
        "output": "0346f97e367857a329cea2d43dc4936f42d0e2e16d19e81f046d5380593a43d9",
        "methods": ["public static final getMobileInterfacePrefix()Ljava/lang/String;"],
        "hooks": ["epdg_interface_namespace"],
    },
    "com/sec/epdg/utils/WifiInterface/EpdgWifiInfo.smali": {
        "class": "Lcom/sec/epdg/utils/WifiInterface/EpdgWifiInfo;", "access": ["public"],
        "super": "Ljava/lang/Object;", "input": "840ce633ef3e5796a9d719093c9a4a97bdc2e60532fa7ad836b7bde158a9734c",
        "output": "291f478171ace673f8f6f86c054d2d9ea6735714cb6fb2d64245ef245f79001c",
        "methods": ["public static getCurrentSSID(Landroid/content/Context;)Ljava/lang/String;", "public static getCurrentWifiRssi(Landroid/content/Context;)I", "public static getUeWiFiMac(Landroid/content/Context;)Ljava/lang/String;"],
        "hooks": ["wifi_service_null_guards"],
    },
    "com/sec/epdg/VoWifiSettingObserver.smali": {
        "class": "Lcom/sec/epdg/VoWifiSettingObserver;", "access": ["public"],
        "super": "Lcom/sec/epdg/EpdgContentObserverBase;", "input": "7f20101c37dd30d57c8f15de2de4182af21e952a6884917f6e34955b2f150463",
        "output": "48e03824b77d61524312afc7ebcfa340815afdc1b61be65659c1e6eb064f55b7",
        "methods": ["public onChangeSlowPath(ZLandroid/net/Uri;)V", "public registerObserver(I)V"],
        "hooks": ["siminfo_setting_observer"],
    },
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


def load_contract(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransformError(f"cannot read contract: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "transformation_id", "source_artifact", "roundtrip_normalizations", "targets"}:
        raise TransformError("malformed contract")
    if raw["schema_version"] != 1 or raw["transformation_id"] != TRANSFORMATION_ID:
        raise TransformError("unsupported contract identity")
    artifact = raw["source_artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {"apk_sha256", "apk_size", "classes_dex_sha256", "validated_reference_dex_sha256"}:
        raise TransformError("malformed source artifact contract")
    if artifact != {"apk_sha256": "c798cd875f17bcad5ac5181587b09152ed96c453914b6a314d701746b08b8ad7", "apk_size": 562108, "classes_dex_sha256": "0a70f09b57e532c67f5cdda27eddd0dd85427317e153bc0009e926ee5ad5d739", "validated_reference_dex_sha256": "636e86b3f17080d0b16ddc8f8421ee9bee437b719ddc92e1c1ef84f06afd6ddf"}:
        raise TransformError("source artifact contract drift")
    if raw["roundtrip_normalizations"] != [{"path": "com/sec/epdg/utils/retry/RetryManager.smali", "input_sha256": "6ca67c6f058a9100827477f79ab2a2927c6a4c71e72c2acf9204a131b809cea8", "output_sha256": "350d5c571513260eaa96424fc8108bb4d27e09f6cc8fb8f751bf14948317f23b", "rule": "explicit_false_static_default_elided"}]:
        raise TransformError("round-trip normalization contract drift")
    items = raw["targets"]
    if not isinstance(items, list) or len(items) != len(TARGETS):
        raise TransformError("target set drift")
    by_path = {}
    keys = {"path", "class", "class_access", "super", "input_sha256", "output_sha256", "required_methods", "operations"}
    for item in items:
        if not isinstance(item, dict) or set(item) != keys or item.get("path") in by_path:
            raise TransformError("malformed or duplicate target")
        rel = PurePosixPath(item["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() not in TARGETS:
            raise TransformError("unexpected or unsafe target path")
        expected = TARGETS[rel.as_posix()]
        found = (item["class"], item["class_access"], item["super"], item["input_sha256"], item["output_sha256"], item["required_methods"], item["operations"])
        wanted = (expected["class"], expected["access"], expected["super"], expected["input"], expected["output"], expected["methods"], expected["hooks"])
        if found != wanted:
            raise TransformError(f"target contract drift: {rel.as_posix()}")
        by_path[rel.as_posix()] = item
    if set(by_path) != set(TARGETS):
        raise TransformError("target set drift")
    return raw


def _identity(text: str, spec: dict) -> None:
    rows = [line.split() for line in text.splitlines() if line.startswith(".class ") and line.split()[-1] == spec["class"]]
    if len(rows) != 1 or rows[0][1:-1] != spec["access"]:
        raise TransformError("class identity drift")
    if len(re.findall(r"(?m)^\.super\s+" + re.escape(spec["super"]) + r"\s*$", text)) != 1:
        raise TransformError("superclass drift")
    for signature in spec["methods"]:
        _one(text, signature)


def _patch_interface(text: str) -> str:
    sig = TARGETS[next(p for p in TARGETS if p.endswith("EpdgInterface.smali"))]["methods"][0]
    method = _one(text, sig)
    method = _replace_once(method, "    if-nez v3, :cond_3\n\n", "", "already-up early exit")
    old = """    .line 123
    if-eqz v1, :cond_2

    .line 124
"""
    new = """    if-eqz v0, :cond_2

    if-eqz v1, :cond_2

    invoke-virtual {p0}, Lcom/sec/epdg/apassist/interfaceController/EpdgInterface;->getIpv6Address()Landroid/net/LinkAddress;

    move-result-object v3

    invoke-virtual {v2, v3}, Landroid/net/InterfaceConfiguration;->setLinkAddress(Landroid/net/LinkAddress;)V

    iget-object v3, p0, Lcom/sec/epdg/apassist/interfaceController/EpdgInterface;->mNmService:Landroid/os/INetworkManagementService;

    invoke-interface {v3, p1, v2}, Landroid/os/INetworkManagementService;->setInterfaceConfig(Ljava/lang/String;Landroid/net/InterfaceConfiguration;)V

    .line 123
    :cond_2
    if-eqz v1, :cond_3

    .line 124
"""
    method = _replace_once(method, old, new, "IPv6 configuration")
    method = _replace_once(method, "    :cond_2\n    iget-object v3", "    :cond_3\n    iget-object v3", "IPv6 disable label")
    method = _replace_once(method, "    .line 129\n    :cond_3\n    iget-object v3", "    .line 129\n    iget-object v3", "removed early-exit label")
    return text.replace(_one(text, sig), method)


def _patch_qns(text: str) -> str:
    sig = "private updateHandOverEnabled(I)V"
    method = _one(text, sig)
    old = "    .line 107\n    invoke-super {p0, p1}, Landroid/telephony/data/QualifiedNetworksService$NetworkAvailabilityProvider;->updateHandoverEnabled(I)V\n\n"
    return text.replace(method, _replace_once(method, old, "", "QNS super call"))


def _patch_telephony(text: str) -> str:
    ctor = _one(text, "private constructor <init>(I)V")
    old = """    const-string v2, "ril.data.intfprefix"

    const-string v3, "rmnet"

    invoke-static {v2, v3}, Landroid/os/SystemProperties;->get(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2
"""
    ctor2 = _replace_once(ctor, old, '    const-string v2, "epdg_data"\n', "interface prefix")
    text = text.replace(ctor, ctor2)
    sig = "public setupDataCall(ILandroid/telephony/data/DataProfile;ZZILandroid/net/LinkProperties;Landroid/os/Message;)V"
    method = _one(text, sig)
    anchor = """    and-int/lit8 v14, v4, 0xf

    .line 163
    .local v14, "cid":I
"""
    replacement = """    and-int/lit8 v14, v4, 0xf

    if-lez v14, :cond_6

    const/16 v4, 0x8

    if-le v14, v4, :cond_7

    :cond_6
    const/4 v14, 0x1

    .line 163
    .local v14, "cid":I
    :cond_7
"""
    return text.replace(method, _replace_once(method, anchor, replacement, "CID fallback"))


def _patch_subscription(text: str) -> str:
    sig = "protected getVowifiSetting()I"
    method = _one(text, sig)
    head = """    .locals 5

    .line 296
    iget v0, p0, Lcom/sec/epdg/EpdgSubScriptionBase;->mPhoneId:I
"""
    inserted = """    .locals 5

    iget v0, p0, Lcom/sec/epdg/EpdgSubScriptionBase;->mPhoneId:I

    invoke-static {v0}, Lcom/sec/epdg/EpdgUtils;->getInstance(I)Lcom/sec/epdg/EpdgUtils;

    move-result-object v1

    invoke-virtual {v1, v0}, Lcom/sec/epdg/EpdgUtils;->getSubId(I)I

    move-result v1

    const/4 v0, -0x1

    if-eq v1, v0, :cond_0

    const-string v2, "wfc_ims_enabled"

    iget-object v3, p0, Lcom/sec/epdg/EpdgSubScriptionBase;->mContext:Landroid/content/Context;

    invoke-static {v1, v2, v0, v3}, Landroid/telephony/SubscriptionManager;->getIntegerSubscriptionProperty(ILjava/lang/String;ILandroid/content/Context;)I

    move-result v1

    if-eq v1, v0, :cond_0

    return v1

    .line 296
    :cond_0
    iget v0, p0, Lcom/sec/epdg/EpdgSubScriptionBase;->mPhoneId:I
"""
    method = _replace_once(method, head, inserted, "subscription setting read")
    method = _replace_once(method, "    if-eqz v1, :cond_1", "    if-eqz v1, :cond_2", "DSDS branch")
    method = _replace_once(method, "    if-eqz v1, :cond_0", "    if-eqz v1, :cond_1", "SIM setting branch")
    method = _replace_once(method, "    :cond_0\n    const/4 v1, 0x0", "    :cond_1\n    const/4 v1, 0x0", "disabled label")
    method = _replace_once(method, "    :cond_1\n    iget-object v1", "    :cond_2\n    iget-object v1", "legacy label")
    return text.replace(_one(text, sig), method)


def _patch_utils(text: str) -> str:
    sig = "public static final getMobileInterfacePrefix()Ljava/lang/String;"
    method = _one(text, sig)
    old = """    const-string v0, "ril.data.intfprefix"

    const-string v1, "rmnet"

    invoke-static {v0, v1}, Landroid/os/SystemProperties;->get(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0
"""
    return text.replace(method, _replace_once(method, old, '    const-string v0, "epdg_data"\n', "interface prefix"))


def _patch_wifi(text: str) -> str:
    specs = [
        ("public static getCurrentSSID(Landroid/content/Context;)Ljava/lang/String;", "    const/4 v2, 0x0\n\n    return-object v2", [("cond_0", "cond_1")]),
        ("public static getCurrentWifiRssi(Landroid/content/Context;)I", "    const/16 v2, -0x64\n\n    return v2", [("cond_0", "cond_1")]),
        ("public static getUeWiFiMac(Landroid/content/Context;)Ljava/lang/String;", "    const/4 v2, 0x0\n\n    return-object v2", [("cond_0", "cond_1")]),
    ]
    for sig, fallback, renames in specs:
        original = _one(text, sig)
        method = original
        anchor = "    check-cast v0, Landroid/net/wifi/WifiManager;\n\n"
        guard = anchor + "    if-nez v0, :cond_0\n\n" + fallback + "\n\n"
        method = _replace_once(method, anchor, guard, f"{sig} null guard")
        for old, new in renames:
            method = method.replace(f":{old}", f":{new}")
        # Restore the new guard target after renaming legacy labels.
        method = method.replace("if-nez v0, :cond_1", "if-nez v0, :cond_0", 1)
        local_anchor = '    .local v0, "wifiManager":Landroid/net/wifi/WifiManager;\n'
        method = _replace_once(method, local_anchor, local_anchor + "    :cond_0\n", f"{sig} guard label")
        text = text.replace(original, method)
    return text


def _patch_observer(text: str) -> str:
    sig = "public onChangeSlowPath(ZLandroid/net/Uri;)V"
    method = _one(text, sig)
    old = """    invoke-virtual {v12, v4}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v3

    if-eqz v3, :cond_0
"""
    new = """    invoke-virtual {v12, v4}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v3

    if-nez v3, :cond_2

    const-string v3, "telephony/siminfo"

    invoke-virtual {v12, v3}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v3

    if-eqz v3, :cond_0
"""
    text = text.replace(method, _replace_once(method, old, new, "siminfo change path"))
    sig = "public registerObserver(I)V"
    method = _one(text, sig)
    anchor = """    :goto_0
    invoke-static {}, Lcom/sec/epdg/EpdgService;->isCrossSimSupportedbyDevice()Z
"""
    insertion = """    :goto_0
    const-string v0, "content://telephony/siminfo"

    invoke-static {v0}, Landroid/net/Uri;->parse(Ljava/lang/String;)Landroid/net/Uri;

    move-result-object v0

    iget-object v1, p0, Lcom/sec/epdg/VoWifiSettingObserver;->mContext:Landroid/content/Context;

    invoke-virtual {v1}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v1

    const/4 v3, 0x1

    invoke-virtual {v1, v0, v3, p0}, Landroid/content/ContentResolver;->registerContentObserver(Landroid/net/Uri;ZLandroid/database/ContentObserver;)V

    invoke-static {}, Lcom/sec/epdg/EpdgService;->isCrossSimSupportedbyDevice()Z
"""
    return text.replace(method, _replace_once(method, anchor, insertion, "siminfo observer registration"))


PATCHERS = {
    "com/sec/epdg/apassist/interfaceController/EpdgInterface.smali": _patch_interface,
    "com/sec/epdg/apassist/IwlanService/EpdgQualifiedNetworksService$EpdgNetworkAvailabilityProvider.smali": _patch_qns,
    "com/sec/epdg/apassist/IwlanService/TelephonyAdapter.smali": _patch_telephony,
    "com/sec/epdg/EpdgSubScriptionBase.smali": _patch_subscription,
    "com/sec/epdg/EpdgUtils.smali": _patch_utils,
    "com/sec/epdg/utils/WifiInterface/EpdgWifiInfo.smali": _patch_wifi,
    "com/sec/epdg/VoWifiSettingObserver.smali": _patch_observer,
}


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


def transform(contract_path: Path, source_root: Path, overlay: Path, report: Path, allow_identical: bool = False) -> dict:
    contract = load_contract(contract_path)
    if source_root.is_symlink() or not source_root.is_dir():
        raise TransformError("input root must be a non-symlink directory")
    root = source_root.resolve(strict=True)
    outputs = []
    report_files = []
    for item in contract["targets"]:
        path = item["path"]
        source = root.joinpath(*PurePosixPath(path).parts)
        if source.is_symlink() or not source.is_file():
            raise TransformError(f"target must be a regular non-symlink file: {path}")
        data = source.read_bytes()
        digest = _sha(data)
        spec = TARGETS[path]
        if digest == spec["output"]:
            raise TransformError(f"already applied: {path}")
        if digest != spec["input"]:
            raise TransformError(f"input hash drift: {path}")
        text = data.decode("utf-8")
        _identity(text, spec)
        updated = PATCHERS[path](text)
        _post(text, updated, spec)
        output = updated.encode("utf-8")
        outputs.append((path, output))
        report_files.append({"target": path, "operations": spec["hooks"], "input_sha256": digest, "output_sha256": _sha(output)})
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID, "changed": True, "files": report_files}
    report_data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    if overlay.exists() or report.exists():
        if allow_identical and report.is_file() and report.read_bytes() == report_data and all((overlay.joinpath(*PurePosixPath(p).parts)).is_file() and (overlay.joinpath(*PurePosixPath(p).parts)).read_bytes() == data for p, data in outputs):
            payload["changed"] = False
            return payload
        raise TransformError("refusing to overwrite existing overlay or report")
    if overlay.is_symlink() or report.is_symlink() or not overlay.parent.is_dir() or not report.parent.is_dir():
        raise TransformError("unsafe output path")
    temp_overlay = Path(tempfile.mkdtemp(prefix=f".{overlay.name}.", dir=overlay.parent))
    fd, temp_name = tempfile.mkstemp(prefix=f".{report.name}.", suffix=".tmp", dir=report.parent)
    os.close(fd)
    temp_report = Path(temp_name)
    published = False
    try:
        for path, data in outputs:
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
        result = transform(args.contract, args.input_smali_root, args.output_overlay, args.report, args.allow_identical)
    except (OSError, UnicodeError, TransformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
