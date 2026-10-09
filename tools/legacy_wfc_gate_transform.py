#!/usr/bin/env python3
"""Create a hash-pinned BV1 smali overlay for the legacy WFC startup gate."""

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


TRANSFORMATION_ID = "BV1-legacy-wfc-startup-gate"
MANAGER = "com/sec/internal/ims/core/WfcEpdgManager.smali"
OBSERVER = "com/sec/internal/ims/core/WfcEpdgManager$VoWifiSettingObserver.smali"
INPUT_SHA256 = {
    MANAGER: "924a0b2d36e9f24146ba3a983ca2799a1eaf1881d93cf5b1304631f45583802a",
    OBSERVER: "72370db24d6909715423bcc76c00025142549d02e3a49303aea02c9ccc25d7a6",
}
OUTPUT_SHA256 = {
    MANAGER: "cfe43201db8bd88e6cb30800600081249cea9b176fee8289ccb2dcac687dd635",
    OBSERVER: "6150ac244b32878f267337ce9039598a2b2b608897a7342afefabd8673eda967",
}
METHOD_RE = re.compile(r"(?ms)^\.method\s+(?P<header>[^\r\n]+)\r?\n.*?^\.end method\s*$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _method(text: str, signature: str) -> str:
    found = [m.group(0) for m in METHOD_RE.finditer(text) if m.group("header") == signature]
    if len(found) != 1:
        raise TransformError(f"required method drift: {signature}")
    return found[0]


def _replace_method(text: str, signature: str, replacement: str) -> str:
    original = _method(text, signature)
    if replacement in text or text.count(original) != 1:
        raise TransformError(f"repeated or ambiguous method patch: {signature}")
    return text.replace(original, replacement, 1)


ACTIVE_ANDROID_SETTING = r'''.method private getActiveAndroidWfcSetting(I)I
    .locals 12
    .param p1, "phoneId"    # I

    const/4 v0, -0x2

    const/4 v10, 0x0

    :try_start_0
    invoke-static {p1}, Lcom/sec/internal/ims/core/sim/SimManagerFactory;->getSimManagerFromSimSlot(I)Lcom/sec/internal/interfaces/ims/core/ISimManager;

    move-result-object v1

    if-eqz v1, :legacy_wfc_read_done

    invoke-interface {v1}, Lcom/sec/internal/interfaces/ims/core/ISimManager;->isSimAvailable()Z

    move-result v11

    if-eqz v11, :legacy_wfc_read_done

    invoke-interface {v1}, Lcom/sec/internal/interfaces/ims/core/ISimManager;->getSimSlotIndex()I

    move-result v11

    if-ne v11, p1, :legacy_wfc_read_done

    invoke-interface {v1}, Lcom/sec/internal/interfaces/ims/core/ISimManager;->getSubscriptionId()I

    move-result v3

    invoke-static {v3}, Landroid/telephony/SubscriptionManager;->isValidSubscriptionId(I)Z

    move-result v11

    if-eqz v11, :legacy_wfc_read_done

    iget-object v11, p0, Lcom/sec/internal/ims/core/WfcEpdgManager;->mContext:Landroid/content/Context;

    invoke-static {v11}, Landroid/telephony/SubscriptionManager;->from(Landroid/content/Context;)Landroid/telephony/SubscriptionManager;

    move-result-object v2

    if-eqz v2, :legacy_wfc_read_done

    invoke-virtual {v2, v3}, Landroid/telephony/SubscriptionManager;->isActiveSubscriptionId(I)Z

    move-result v11

    if-eqz v11, :legacy_wfc_read_done

    invoke-static {v3}, Landroid/telephony/SubscriptionManager;->getPhoneId(I)I

    move-result v11

    if-ne v11, p1, :legacy_wfc_read_done

    iget-object v4, p0, Lcom/sec/internal/ims/core/WfcEpdgManager;->mContext:Landroid/content/Context;

    invoke-virtual {v4}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v4

    if-eqz v4, :legacy_wfc_read_done

    const-string v5, "content://telephony/siminfo"

    invoke-static {v5}, Landroid/net/Uri;->parse(Ljava/lang/String;)Landroid/net/Uri;

    move-result-object v5

    const/4 v11, 0x2

    new-array v6, v11, [Ljava/lang/String;

    const/4 v11, 0x0

    const-string v9, "_id"

    aput-object v9, v6, v11

    const/4 v11, 0x1

    const-string/jumbo v9, "wfc_ims_enabled"

    aput-object v9, v6, v11

    const-string v7, "_id=?"

    const/4 v11, 0x1

    new-array v8, v11, [Ljava/lang/String;

    invoke-static {v3}, Ljava/lang/String;->valueOf(I)Ljava/lang/String;

    move-result-object v9

    const/4 v11, 0x0

    aput-object v9, v8, v11

    const/4 v9, 0x0

    invoke-virtual/range {v4 .. v9}, Landroid/content/ContentResolver;->query(Landroid/net/Uri;[Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;Ljava/lang/String;)Landroid/database/Cursor;

    move-result-object v10

    if-eqz v10, :legacy_wfc_read_done

    invoke-interface {v10}, Landroid/database/Cursor;->moveToFirst()Z

    move-result v11

    if-eqz v11, :legacy_wfc_close_cursor

    const-string/jumbo v11, "wfc_ims_enabled"

    invoke-interface {v10, v11}, Landroid/database/Cursor;->getColumnIndex(Ljava/lang/String;)I

    move-result v11

    if-ltz v11, :legacy_wfc_close_cursor

    invoke-interface {v10, v11}, Landroid/database/Cursor;->getType(I)I

    move-result v9

    const/4 v6, 0x1

    if-ne v9, v6, :legacy_wfc_close_cursor

    invoke-interface {v10, v11}, Landroid/database/Cursor;->getInt(I)I

    move-result v11

    const/4 v9, -0x1

    if-lt v11, v9, :legacy_wfc_close_cursor

    const/4 v9, 0x1

    if-gt v11, v9, :legacy_wfc_close_cursor

    move v0, v11
    :try_end_0
    .catch Ljava/lang/Exception; {:try_start_0 .. :try_end_0} :legacy_wfc_read_exception

    :legacy_wfc_close_cursor
    :try_start_1
    invoke-interface {v10}, Landroid/database/Cursor;->close()V
    :try_end_1
    .catch Ljava/lang/Exception; {:try_start_1 .. :try_end_1} :legacy_wfc_close_exception

    const/4 v11, -0x2

    if-eq v0, v11, :legacy_wfc_read_done

    :try_start_2
    invoke-interface {v1}, Lcom/sec/internal/interfaces/ims/core/ISimManager;->isSimAvailable()Z

    move-result v11

    if-eqz v11, :legacy_wfc_identity_changed

    invoke-interface {v1}, Lcom/sec/internal/interfaces/ims/core/ISimManager;->getSimSlotIndex()I

    move-result v11

    if-ne v11, p1, :legacy_wfc_identity_changed

    invoke-interface {v1}, Lcom/sec/internal/interfaces/ims/core/ISimManager;->getSubscriptionId()I

    move-result v11

    if-ne v11, v3, :legacy_wfc_identity_changed

    invoke-virtual {v2, v3}, Landroid/telephony/SubscriptionManager;->isActiveSubscriptionId(I)Z

    move-result v11

    if-eqz v11, :legacy_wfc_identity_changed

    invoke-static {v3}, Landroid/telephony/SubscriptionManager;->getPhoneId(I)I

    move-result v11

    if-ne v11, p1, :legacy_wfc_identity_changed
    :try_end_2
    .catch Ljava/lang/Exception; {:try_start_2 .. :try_end_2} :legacy_wfc_identity_exception

    return v0

    :legacy_wfc_identity_changed
    const/4 v0, -0x2

    return v0

    :legacy_wfc_identity_exception
    move-exception v11

    const/4 v0, -0x2

    return v0

    :legacy_wfc_read_exception
    move-exception v11

    if-eqz v10, :legacy_wfc_read_done

    :try_start_3
    invoke-interface {v10}, Landroid/database/Cursor;->close()V
    :try_end_3
    .catch Ljava/lang/Exception; {:try_start_3 .. :try_end_3} :legacy_wfc_close_exception

    goto :legacy_wfc_read_done

    :legacy_wfc_close_exception
    move-exception v11

    const/4 v0, -0x2

    :legacy_wfc_read_done
    return v0
.end method'''


EXPLICIT_LEGACY_MODE = r'''.method private isExplicitLegacyIwlanMode()Z
    .locals 2

    const-string/jumbo v0, "ro.telephony.iwlan_operation_mode"

    const-string v1, ""

    invoke-static {v0, v1}, Landroid/os/SemSystemProperties;->get(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    const-string v1, "legacy"

    invoke-virtual {v1, v0}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v0

    return v0
.end method'''


IS_WFC_ENABLED = r'''.method private isWFCEnabled(I)Z
    .locals 7
    .param p1, "phoneId"    # I

    iget-object v0, p0, Lcom/sec/internal/ims/core/WfcEpdgManager;->mContext:Landroid/content/Context;

    invoke-direct {p0, v0, p1}, Lcom/sec/internal/ims/core/WfcEpdgManager;->isEntitlementRequired(Landroid/content/Context;I)Z

    move-result v0

    const/4 v1, 0x0

    if-eqz v0, :legacy_wfc_entitlement_ok

    iget-object v0, p0, Lcom/sec/internal/ims/core/WfcEpdgManager;->mContext:Landroid/content/Context;

    invoke-direct {p0, v0, p1}, Lcom/sec/internal/ims/core/WfcEpdgManager;->isEntitlementResult(Landroid/content/Context;I)Z

    move-result v0

    if-nez v0, :legacy_wfc_entitlement_ok

    return v1

    :legacy_wfc_entitlement_ok
    invoke-direct {p0, p1}, Lcom/sec/internal/ims/core/WfcEpdgManager;->isVowifiSupported(I)Z

    move-result v0

    if-nez v0, :legacy_wfc_supported

    return v1

    :legacy_wfc_supported
    add-int/lit8 v0, p1, 0x1

    invoke-static {p1}, Lcom/sec/internal/helper/SimUtil;->getSimMno(I)Lcom/sec/internal/constants/Mno;

    move-result-object v2

    const/4 v4, 0x1

    invoke-virtual {v2}, Lcom/sec/internal/constants/Mno;->isCanada()Z

    move-result v3

    if-nez v3, :legacy_wfc_original_enabled

    invoke-virtual {v2}, Lcom/sec/internal/constants/Mno;->isUSA()Z

    move-result v3

    if-nez v3, :legacy_wfc_original_enabled

    iget-object v3, p0, Lcom/sec/internal/ims/core/WfcEpdgManager;->mContext:Landroid/content/Context;

    invoke-virtual {v3}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v3

    new-instance v5, Ljava/lang/StringBuilder;

    invoke-direct {v5}, Ljava/lang/StringBuilder;-><init>()V

    const-string/jumbo v6, "wifi_call_enable"

    invoke-virtual {v5, v6}, Ljava/lang/StringBuilder;->append(Ljava/lang/String;)Ljava/lang/StringBuilder;

    invoke-virtual {v5, v0}, Ljava/lang/StringBuilder;->append(I)Ljava/lang/StringBuilder;

    invoke-virtual {v5}, Ljava/lang/StringBuilder;->toString()Ljava/lang/String;

    move-result-object v5

    const/4 v6, -0x1

    invoke-static {v3, v5, v6}, Landroid/provider/Settings$System;->getInt(Landroid/content/ContentResolver;Ljava/lang/String;I)I

    move-result v3

    if-ne v3, v4, :legacy_wfc_original_done

    :legacy_wfc_original_enabled
    move v1, v4

    :legacy_wfc_original_done
    invoke-direct {p0}, Lcom/sec/internal/ims/core/WfcEpdgManager;->isExplicitLegacyIwlanMode()Z

    move-result v0

    if-eqz v0, :legacy_wfc_return_original

    invoke-direct {p0, p1}, Lcom/sec/internal/ims/core/WfcEpdgManager;->getActiveAndroidWfcSetting(I)I

    move-result v0

    if-ne v0, v4, :legacy_wfc_not_android_enabled

    return v4

    :legacy_wfc_not_android_enabled
    if-eqz v0, :legacy_wfc_return_disabled

    const/4 v2, -0x1

    if-ne v0, v2, :legacy_wfc_return_disabled

    :legacy_wfc_return_original
    return v1

    :legacy_wfc_return_disabled
    const/4 v0, 0x0

    return v0
.end method'''


SIMINFO_REGISTRATION = r'''    iput-object v2, p0, Lcom/sec/internal/ims/core/WfcEpdgManager;->mVoWifiSettingObserver:Lcom/sec/internal/ims/core/WfcEpdgManager$VoWifiSettingObserver;

    invoke-direct {p0}, Lcom/sec/internal/ims/core/WfcEpdgManager;->isExplicitLegacyIwlanMode()Z

    move-result v3

    if-eqz v3, :legacy_wfc_observer_registered

    const-string v3, "content://telephony/siminfo"

    invoke-static {v3}, Landroid/net/Uri;->parse(Ljava/lang/String;)Landroid/net/Uri;

    move-result-object v3

    iget-object v4, p0, Lcom/sec/internal/ims/core/WfcEpdgManager;->mContext:Landroid/content/Context;

    invoke-virtual {v4}, Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;

    move-result-object v4

    iget-object v5, p0, Lcom/sec/internal/ims/core/WfcEpdgManager;->mVoWifiSettingObserver:Lcom/sec/internal/ims/core/WfcEpdgManager$VoWifiSettingObserver;

    const/4 v6, 0x1

    invoke-virtual {v4, v3, v6, v5}, Landroid/content/ContentResolver;->registerContentObserver(Landroid/net/Uri;ZLandroid/database/ContentObserver;)V

    :legacy_wfc_observer_registered'''


OBSERVER_DISPATCH = r'''    const-string v3, "content://telephony/siminfo"

    invoke-virtual {v0, v3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-nez v3, :legacy_wfc_observed_siminfo

    const-string v3, "content://telephony/siminfo/"

    invoke-virtual {v0, v3}, Ljava/lang/String;->startsWith(Ljava/lang/String;)Z

    move-result v3

    if-eqz v3, :legacy_wfc_original_observer

    :legacy_wfc_observed_siminfo

    const-string/jumbo v3, "ro.telephony.iwlan_operation_mode"

    const-string v4, ""

    invoke-static {v3, v4}, Landroid/os/SemSystemProperties;->get(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v3

    const-string v4, "legacy"

    invoke-virtual {v4, v3}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v3

    if-eqz v3, :legacy_wfc_observer_return

    const/4 v3, 0x0

    :legacy_wfc_observer_loop
    invoke-static {}, Lcom/sec/internal/helper/SimUtil;->getPhoneCount()I

    move-result v4

    if-ge v3, v4, :legacy_wfc_observer_return

    iget-object v4, p0, Lcom/sec/internal/ims/core/WfcEpdgManager$VoWifiSettingObserver;->this$0:Lcom/sec/internal/ims/core/WfcEpdgManager;

    const/4 v5, 0x4

    invoke-virtual {v4, v5, v3}, Lcom/sec/internal/ims/core/WfcEpdgManager;->sendMessage(II)V

    add-int/lit8 v3, v3, 0x1

    goto :legacy_wfc_observer_loop

    :legacy_wfc_observer_return
    return-void

    :legacy_wfc_original_observer'''


def patch_manager(text: str) -> str:
    marker = ".method private isAnySimAvailableWithWFCEnabled()Z"
    if text.count(marker) != 1 or ACTIVE_ANDROID_SETTING in text or EXPLICIT_LEGACY_MODE in text:
        raise TransformError("manager helper anchor drift or repeated patch")
    text = text.replace(marker, ACTIVE_ANDROID_SETTING + "\n\n" + EXPLICIT_LEGACY_MODE + "\n\n" + marker, 1)
    text = _replace_method(text, "private isWFCEnabled(I)Z", IS_WFC_ENABLED)
    init = _method(text, "public initSequentially()V")
    anchor = "    iput-object v2, p0, Lcom/sec/internal/ims/core/WfcEpdgManager;->mVoWifiSettingObserver:Lcom/sec/internal/ims/core/WfcEpdgManager$VoWifiSettingObserver;"
    if init.count(anchor) != 1:
        raise TransformError("manager observer registration anchor drift")
    patched_init = init.replace(anchor, SIMINFO_REGISTRATION, 1)
    return text.replace(init, patched_init, 1)


def patch_observer(text: str) -> str:
    method = _method(text, "public onChange(ZLandroid/net/Uri;)V")
    anchor = '''    invoke-static {v1, v2}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

    .line 967
    const/4 v1, 0x1'''
    replacement = '''    invoke-static {v1, v2}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I

''' + OBSERVER_DISPATCH + '''

    .line 967
    const/4 v1, 0x1'''
    if method.count(anchor) != 1 or OBSERVER_DISPATCH in text:
        raise TransformError("observer dispatch anchor drift or repeated patch")
    return text.replace(method, method.replace(anchor, replacement, 1), 1)


PATCHERS = {MANAGER: patch_manager, OBSERVER: patch_observer}


def _safe_source(root: Path, relative: str) -> Path:
    path = root.joinpath(*PurePosixPath(relative).parts)
    if path.is_symlink() or not path.is_file():
        raise TransformError(f"target must be a regular non-symlink file: {relative}")
    return path


def transform(source_root: Path, output_overlay: Path, report: Path) -> dict:
    if source_root.is_symlink() or not source_root.is_dir():
        raise TransformError("input root must be a non-symlink directory")
    originals = {name: _safe_source(source_root, name).read_bytes() for name in PATCHERS}
    hashes = {name: sha256(data) for name, data in originals.items()}
    if all(hashes[name] == OUTPUT_SHA256[name] for name in PATCHERS):
        raise TransformError("already applied exact legacy WFC gate transform")
    if any(hashes[name] == OUTPUT_SHA256[name] for name in PATCHERS):
        raise TransformError("mixed original/patched input refused")
    for name in PATCHERS:
        if hashes[name] != INPUT_SHA256[name]:
            raise TransformError(f"input hash drift: {name}")
    updated = {}
    for name, patcher in PATCHERS.items():
        data = patcher(originals[name].decode("utf-8")).encode("utf-8")
        if sha256(data) != OUTPUT_SHA256[name]:
            raise TransformError(f"post-transform hash drift: {name}")
        updated[name] = data
    payload = {
        "schema_version": 1,
        "transformation_id": TRANSFORMATION_ID,
        "changed": True,
        "files": [
            {"target": name, "input_sha256": hashes[name], "output_sha256": sha256(updated[name])}
            for name in PATCHERS
        ],
    }
    if output_overlay.exists() or report.exists():
        raise TransformError("refusing to overwrite existing overlay or report")
    if output_overlay.is_symlink() or report.is_symlink() or not output_overlay.parent.is_dir() or not report.parent.is_dir():
        raise TransformError("unsafe output path")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_overlay.name}.", dir=output_overlay.parent))
    fd, temporary_report_name = tempfile.mkstemp(prefix=f".{report.name}.", suffix=".tmp", dir=report.parent)
    os.close(fd)
    temporary_report = Path(temporary_report_name)
    published_report = False
    try:
        for name, data in updated.items():
            destination = temporary.joinpath(*PurePosixPath(name).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        temporary_report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary_report, report.absolute())
        published_report = True
        os.rename(temporary, output_overlay.absolute())
    except BaseException:
        if published_report:
            report.unlink(missing_ok=True)
        shutil.rmtree(temporary, ignore_errors=True)
        temporary_report.unlink(missing_ok=True)
        raise
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-smali-root", required=True, type=Path)
    parser.add_argument("--output-overlay", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = transform(args.input_smali_root, args.output_overlay, args.report)
    except (OSError, UnicodeError, TransformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
