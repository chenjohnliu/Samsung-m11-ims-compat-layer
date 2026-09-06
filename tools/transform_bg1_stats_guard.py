#!/usr/bin/env python3
"""Emit the two-file BG1 optional-video-statistics smali overlay."""

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


TRANSFORMATION_ID = "BG1-network-statistics-guard"
HANDLER_PATH = "com/sec/internal/ims/servicemodules/volte2/NetworkStatsOnPortHandler.smali"
CALL_PATH = "com/sec/internal/ims/servicemodules/volte2/CallStateMachine.smali"
EXPECTED_PATHS = {HANDLER_PATH, CALL_PATH}
EXPECTED_INPUT_SHA256 = {
    HANDLER_PATH: "e5b14d9633ec92d115e0402b62718a875192432a850ff195a1decdbd2c61c4f2",
    CALL_PATH: "9b89a56452a37aa81cc53c7624e9f7527ff487d2148a67c5cb58b566b7a977aa",
}
H = "Lcom/sec/internal/ims/servicemodules/volte2/NetworkStatsOnPortHandler;"
I = "Landroid/os/INetworkManagementService;"
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
    if not isinstance(targets, list) or len(targets) != 2:
        raise TransformError("contract must contain exactly two targets")
    by_path = {x.get("path"): x for x in targets if isinstance(x, dict)}
    if set(by_path) != EXPECTED_PATHS or len(by_path) != 2:
        raise TransformError("unexpected or duplicate target paths")
    keys = {"path", "class", "class_access", "super", "input_sha256",
            "required_methods", "expected_pre", "expected_post"}
    identities = {
        HANDLER_PATH: (H, ["public"], "Landroid/os/Handler;", [
            "private start()V", "private stop()V",
            "private startNetworkStatsOnPorts(Ljava/lang/String;II)V",
            "private stopNetworkStatsOnPorts(Ljava/lang/String;II)V",
            "public declared-synchronized getNetworkStatsVideoCall()J"]),
        CALL_PATH: ("Lcom/sec/internal/ims/servicemodules/volte2/CallStateMachine;",
                    ["public"], "Lcom/sec/internal/helper/StateMachine;", [
            "protected getNetworkStatsVideoCall()J",
            "protected requestCallDataUsage()V",
            "protected stopNetworkStatsOnPorts()V"]),
    }
    for name, item in by_path.items():
        if set(item) != keys:
            raise TransformError(f"malformed target contract: {name}")
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != name:
            raise TransformError("unsafe target path")
        if (item["class"], item["class_access"], item["super"], item["required_methods"]) != identities[name]:
            raise TransformError(f"target identity drift: {name}")
        if item["input_sha256"] != EXPECTED_INPUT_SHA256[name]:
            raise TransformError(f"input hash contract drift: {name}")
        if (item["expected_pre"], item["expected_post"]) != (0, 1):
            raise TransformError("state contract drift")
    return raw


def _method_spans(text: str, signature: str) -> list[tuple[int, int, str]]:
    out = []
    for match in METHOD_RE.finditer(text):
        header = match.group("header")
        if header == signature:
            out.append((match.start(), match.end(), match.group(0)))
    return out


def _replace_method(text: str, signature: str, replacement: str) -> str:
    spans = _method_spans(text, signature)
    if len(spans) != 1:
        raise TransformError(f"method occurrence drift: {signature}")
    start, end, _ = spans[0]
    return text[:start] + replacement.rstrip() + text[end:]


def _method(signature: str, body: str, locals_count: int) -> str:
    body = body.replace("@H@", H).replace("@I@", I).strip("\n")
    return f".method {signature}\n    .locals {locals_count}\n{body}\n.end method"


def _identity(text: str, spec: dict) -> None:
    rows = [line.split() for line in text.splitlines()
            if line.startswith(".class ") and line.split()[-1] == spec["class"]]
    if len(rows) != 1 or rows[0][1:-1] != spec["class_access"]:
        raise TransformError(f"class identity drift: {spec['path']}")
    if len(re.findall(r"(?m)^\.super\s+" + re.escape(spec["super"]) + r"\s*$", text)) != 1:
        raise TransformError(f"superclass drift: {spec['path']}")
    for method in spec["required_methods"]:
        if len(_method_spans(text, method)) != 1:
            raise TransformError(f"required method drift: {method}")


def _assert_pre_state(text: str, path: str) -> None:
    if path == HANDLER_PATH:
        markers = ("mStatsCapability:I", "statsUnavailable()V",
                   "BG1: video usage unavailable")
        if any(marker in text for marker in markers):
            raise TransformError("BG1 handler is already or partially applied")
    elif ":stats_unavailable" in text:
        raise TransformError("BG1 call-state hook is already or partially applied")


def _handler(text: str) -> str:
    if text.count("# instance fields") != 1:
        raise TransformError("instance-field anchor drift")
    text = text.replace("# instance fields", """# instance fields
# 0 = unchecked; 1 = exact family present; -1 = unavailable.
.field private mStatsCapability:I
.field private mStatsUnavailableLogged:Z
.field private mStatsStartFailed:Z
""", 1)

    old_start = _method_spans(text, "private start()V")[0][2]
    prefix_marker = "    .line 52\n"
    if old_start.count(prefix_marker) != 1 or old_start.count("    :cond_1\n") != 1:
        raise TransformError("start prefix anchor drift")
    prefix = old_start[:old_start.index(prefix_marker)]
    start_body = """    :cond_1
    invoke-direct {p0}, @H@->hasStatsCapability()Z
    move-result v0
    if-eqz v0, :start_done
    const/4 v0, 0x0
    iput-boolean v0, p0, @H@->mStatsStartFailed:Z
    iget v1, p0, @H@->mLocalVideoRtp:I
    iget v2, p0, @H@->mRemoteVideoRtp:I
    if-eqz v1, :afterRtp
    if-eqz v2, :afterRtp
    iget-object v0, p0, @H@->mIface:Ljava/lang/String;
    invoke-direct {p0, v0, v1, v2}, @H@->startNetworkStatsOnPorts(Ljava/lang/String;II)Z
    move-result v0
    if-eqz v0, :failedRtp
    const/4 v0, 0x1
    iput-boolean v0, p0, @H@->mReportingNetworkStatsOnPort:Z
    goto :afterRtp
    :failedRtp
    const/4 v0, 0x1
    iput-boolean v0, p0, @H@->mStatsStartFailed:Z
    :afterRtp
    iget v1, p0, @H@->mLocalVideoRtcp:I
    iget v2, p0, @H@->mRemoteVideoRtcp:I
    if-eqz v1, :afterRtcp
    if-eqz v2, :afterRtcp
    iget-object v0, p0, @H@->mIface:Ljava/lang/String;
    invoke-direct {p0, v0, v1, v2}, @H@->startNetworkStatsOnPorts(Ljava/lang/String;II)Z
    move-result v0
    if-eqz v0, :failedRtcp
    const/4 v0, 0x1
    iput-boolean v0, p0, @H@->mReportingNetworkStatsOnPort:Z
    goto :afterRtcp
    :failedRtcp
    const/4 v0, 0x1
    iput-boolean v0, p0, @H@->mStatsStartFailed:Z
    :afterRtcp
    :start_done
    return-void
    :cond_4
    :goto_1
    const-string v1, "skip startNetworkStatsOnPorts. (vendor req)"
    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    return-void
""".replace("@H@", H)
    text = _replace_method(text, "private start()V", prefix + start_body + ".end method")

    for operation, ret in (("start", "Z"), ("stop", "V")):
        success = "    const/4 v0, 0x1\n    return v0" if ret == "Z" else "    return-void"
        failure = "    const/4 v0, 0x0\n    return v0" if ret == "Z" else "    return-void"
        body = f"""    invoke-direct {{p0}}, @H@->hasStatsCapability()Z
    move-result v0
    if-eqz v0, :failed
    :service_start
    const-string v0, "network_management"
    invoke-static {{v0}}, Landroid/os/ServiceManager;->getService(Ljava/lang/String;)Landroid/os/IBinder;
    move-result-object v0
    invoke-static {{v0}}, Landroid/os/INetworkManagementService$Stub;->asInterface(Landroid/os/IBinder;)Landroid/os/INetworkManagementService;
    move-result-object v0
    if-eqz v0, :failed
    invoke-interface {{v0, p1, p2, p3}}, @I@->{operation}NetworkStatsOnPorts(Ljava/lang/String;II)V
    :service_end
    .catch Landroid/os/RemoteException; {{:service_start .. :service_end}} :backend_failed
    .catch Ljava/lang/IllegalStateException; {{:service_start .. :service_end}} :backend_failed
    .catch Ljava/lang/IllegalArgumentException; {{:service_start .. :service_end}} :backend_failed
    .catch Ljava/lang/SecurityException; {{:service_start .. :service_end}} :backend_failed
    .catch Ljava/lang/IncompatibleClassChangeError; {{:service_start .. :service_end}} :linkage_failed
{success}
    :linkage_failed
    move-exception v0
    const/4 v0, -0x1
    iput v0, p0, @H@->mStatsCapability:I
    goto :failed
    :backend_failed
    move-exception v0
    :failed
    invoke-direct {{p0}}, @H@->statsUnavailable()V
{failure}"""
        text = _replace_method(text, f"private {operation}NetworkStatsOnPorts(Ljava/lang/String;II)V",
                               _method(f"private {operation}NetworkStatsOnPorts(Ljava/lang/String;II){ret}", body, 1))

    stop = """    invoke-direct {p0}, @H@->hasStatsCapability()Z
    move-result v0
    if-eqz v0, :cleanup
    iget-boolean v0, p0, @H@->mReportingNetworkStatsOnPort:Z
    if-eqz v0, :cleanup
    iget v1, p0, @H@->mLocalVideoRtp:I
    iget v2, p0, @H@->mRemoteVideoRtp:I
    if-eqz v1, :afterRtp
    if-eqz v2, :afterRtp
    iget-object v0, p0, @H@->mIface:Ljava/lang/String;
    invoke-direct {p0, v0, v1, v2}, @H@->stopNetworkStatsOnPorts(Ljava/lang/String;II)V
    :afterRtp
    iget v1, p0, @H@->mLocalVideoRtcp:I
    iget v2, p0, @H@->mRemoteVideoRtcp:I
    if-eqz v1, :afterRtcp
    if-eqz v2, :afterRtcp
    iget-object v0, p0, @H@->mIface:Ljava/lang/String;
    invoke-direct {p0, v0, v1, v2}, @H@->stopNetworkStatsOnPorts(Ljava/lang/String;II)V
    :afterRtcp
    :cleanup
    const/4 v0, 0x0
    iput-boolean v0, p0, @H@->mReportingNetworkStatsOnPort:Z
    iput-boolean v0, p0, @H@->mStatsStartFailed:Z
    invoke-virtual {p0, v0, v0, v0, v0}, @H@->setVideoPort(IIII)V
    return-void"""
    text = _replace_method(text, "private stop()V", _method("private stop()V", stop, 3))

    query = """    monitor-enter p0
    :query_start
    invoke-direct {p0}, @H@->hasStatsCapability()Z
    move-result v0
    if-eqz v0, :unavailable
    iget-boolean v0, p0, @H@->mReportingNetworkStatsOnPort:Z
    if-eqz v0, :unavailable
    iget-boolean v0, p0, @H@->mStatsStartFailed:Z
    if-nez v0, :unavailable
    const-string v0, "network_management"
    invoke-static {v0}, Landroid/os/ServiceManager;->getService(Ljava/lang/String;)Landroid/os/IBinder;
    move-result-object v0
    invoke-static {v0}, Landroid/os/INetworkManagementService$Stub;->asInterface(Landroid/os/IBinder;)Landroid/os/INetworkManagementService;
    move-result-object v0
    if-eqz v0, :unavailable
    const-wide/16 v1, 0x0
    const/4 v8, 0x0
    iget v4, p0, @H@->mLocalVideoRtp:I
    iget v5, p0, @H@->mRemoteVideoRtp:I
    if-eqz v4, :afterRtp
    if-eqz v5, :afterRtp
    iget-object v3, p0, @H@->mIface:Ljava/lang/String;
    invoke-interface {v0, v3, v4, v5}, @I@->getNetworkStatsVideoCall(Ljava/lang/String;II)Landroid/net/NetworkStats;
    move-result-object v3
    if-eqz v3, :unavailable
    invoke-virtual {v3}, Landroid/net/NetworkStats;->getTotalBytes()J
    move-result-wide v6
    const-wide/16 v3, 0x0
    cmp-long v5, v6, v3
    if-ltz v5, :unavailable
    add-long/2addr v1, v6
    cmp-long v5, v1, v3
    if-ltz v5, :unavailable
    const/4 v8, 0x1
    :afterRtp
    iget v4, p0, @H@->mLocalVideoRtcp:I
    iget v5, p0, @H@->mRemoteVideoRtcp:I
    if-eqz v4, :afterRtcp
    if-eqz v5, :afterRtcp
    iget-object v3, p0, @H@->mIface:Ljava/lang/String;
    invoke-interface {v0, v3, v4, v5}, @I@->getNetworkStatsVideoCall(Ljava/lang/String;II)Landroid/net/NetworkStats;
    move-result-object v3
    if-eqz v3, :unavailable
    invoke-virtual {v3}, Landroid/net/NetworkStats;->getTotalBytes()J
    move-result-wide v6
    const-wide/16 v3, 0x0
    cmp-long v5, v6, v3
    if-ltz v5, :unavailable
    add-long/2addr v1, v6
    cmp-long v5, v1, v3
    if-ltz v5, :unavailable
    const/4 v8, 0x1
    :afterRtcp
    if-eqz v8, :unavailable
    :query_end
    .catch Landroid/os/RemoteException; {:query_start .. :query_end} :backend_failed
    .catch Ljava/lang/IllegalStateException; {:query_start .. :query_end} :backend_failed
    .catch Ljava/lang/IllegalArgumentException; {:query_start .. :query_end} :backend_failed
    .catch Ljava/lang/SecurityException; {:query_start .. :query_end} :backend_failed
    .catch Ljava/lang/IncompatibleClassChangeError; {:query_start .. :query_end} :linkage_failed
    .catchall {:query_start .. :query_end} :monitor_failed
    monitor-exit p0
    return-wide v1
    :linkage_failed
    move-exception v0
    const/4 v0, -0x1
    iput v0, p0, @H@->mStatsCapability:I
    goto :unavailable
    :backend_failed
    move-exception v0
    :unavailable
    :unavailable_start
    invoke-direct {p0}, @H@->statsUnavailable()V
    :unavailable_end
    .catchall {:unavailable_start .. :unavailable_end} :monitor_failed
    const-wide/16 v1, -0x1
    monitor-exit p0
    return-wide v1
    :monitor_failed
    move-exception v0
    monitor-exit p0
    throw v0"""
    text = _replace_method(text, "public declared-synchronized getNetworkStatsVideoCall()J",
                           _method("public declared-synchronized getNetworkStatsVideoCall()J", query, 9))

    helpers = _method("private statsUnavailable()V", """    iget-boolean v0, p0, @H@->mStatsUnavailableLogged:Z
    if-nez v0, :done
    const/4 v0, 0x1
    iput-boolean v0, p0, @H@->mStatsUnavailableLogged:Z
    const-string v0, "NetworkStatsOnPortHandler"
    const-string v1, "BG1: video usage unavailable (optional stats ABI/backend); callback suppressed"
    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I
    :done
    return-void""", 2)
    helpers += "\n\n" + _method("private hasStatsCapability()Z", """    iget v0, p0, @H@->mStatsCapability:I
    if-nez v0, :cached
    :probe_start
    const-class v0, @I@
    const/4 v1, 0x3
    new-array v1, v1, [Ljava/lang/Class;
    const/4 v2, 0x0
    const-class v3, Ljava/lang/String;
    aput-object v3, v1, v2
    const/4 v2, 0x1
    sget-object v3, Ljava/lang/Integer;->TYPE:Ljava/lang/Class;
    aput-object v3, v1, v2
    const/4 v2, 0x2
    aput-object v3, v1, v2
    const-string v2, "startNetworkStatsOnPorts"
    invoke-virtual {v0, v2, v1}, Ljava/lang/Class;->getMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;
    move-result-object v2
    invoke-virtual {v2}, Ljava/lang/reflect/Method;->getReturnType()Ljava/lang/Class;
    move-result-object v2
    sget-object v3, Ljava/lang/Void;->TYPE:Ljava/lang/Class;
    if-ne v2, v3, :unsupported
    const-string v2, "stopNetworkStatsOnPorts"
    invoke-virtual {v0, v2, v1}, Ljava/lang/Class;->getMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;
    move-result-object v2
    invoke-virtual {v2}, Ljava/lang/reflect/Method;->getReturnType()Ljava/lang/Class;
    move-result-object v2
    if-ne v2, v3, :unsupported
    const-string v2, "getNetworkStatsVideoCall"
    invoke-virtual {v0, v2, v1}, Ljava/lang/Class;->getMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;
    move-result-object v2
    invoke-virtual {v2}, Ljava/lang/reflect/Method;->getReturnType()Ljava/lang/Class;
    move-result-object v2
    const-class v3, Landroid/net/NetworkStats;
    if-ne v2, v3, :unsupported
    :probe_end
    .catch Ljava/lang/NoSuchMethodException; {:probe_start .. :probe_end} :probe_failed
    .catch Ljava/lang/SecurityException; {:probe_start .. :probe_end} :probe_failed
    .catch Ljava/lang/NoClassDefFoundError; {:probe_start .. :probe_end} :probe_failed
    .catch Ljava/lang/IncompatibleClassChangeError; {:probe_start .. :probe_end} :probe_failed
    const/4 v0, 0x1
    iput v0, p0, @H@->mStatsCapability:I
    return v0
    :probe_failed
    move-exception v0
    :unsupported
    const/4 v0, -0x1
    iput v0, p0, @H@->mStatsCapability:I
    invoke-direct {p0}, @H@->statsUnavailable()V
    :cached
    const/4 v1, 0x1
    if-eq v0, v1, :supported
    const/4 v0, 0x0
    return v0
    :supported
    const/4 v0, 0x1
    return v0""", 4)
    text = text.rstrip() + "\n\n" + helpers + "\n"

    for name in ("start", "stop"):
        sig = f"private {name}()V"
        old = _method_spans(text, sig)[0][2]
        locked = old.replace(f".method private {name}()V", f".method private {name}StatsLocked()V", 1)
        wrapper = _method(f"private declared-synchronized {name}()V", f"""    monitor-enter p0
    :locked_start
    invoke-direct {{p0}}, @H@->{name}StatsLocked()V
    :locked_end
    .catchall {{:locked_start .. :locked_end}} :locked_failed
    monitor-exit p0
    return-void
    :locked_failed
    move-exception v0
    monitor-exit p0
    throw v0""", 1)
        text = text.replace(old, locked + "\n\n" + wrapper, 1)
    return text


def _call_state(text: str) -> str:
    sig = "protected getNetworkStatsVideoCall()J"
    old = _method_spans(text, sig)[0][2]
    if old.count("const-wide/16 v0, 0x0") != 1:
        raise TransformError("query sentinel anchor drift")
    text = _replace_method(text, sig, old.replace("const-wide/16 v0, 0x0", "const-wide/16 v0, -0x1", 1))
    sig = "protected requestCallDataUsage()V"
    old = _method_spans(text, sig)[0][2]
    if old.count("    .locals 4") != 1 or old.count("    move-result-wide v0") != 1 or old.count("    return-void") != 1:
        raise TransformError("callback-suppression anchor drift")
    new = old.replace("    .locals 4", "    .locals 5", 1)
    new = new.replace("    move-result-wide v0", """    move-result-wide v0

    const-wide/16 v2, 0x0
    cmp-long v4, v0, v2
    if-ltz v4, :stats_unavailable""", 1)
    new = new.replace("    return-void", "    :stats_unavailable\n    return-void", 1)
    return _replace_method(text, sig, new)


def _post_validate(original: str, updated: str, spec: dict) -> None:
    if original == updated:
        raise TransformError("transformation produced no change")
    # Every method outside the narrow replacement set must remain byte-for-byte
    # identical. Added wrappers/helpers are validated separately below.
    replaced = ({
        "private start()V", "private stop()V",
        "private startNetworkStatsOnPorts(Ljava/lang/String;II)V",
        "private stopNetworkStatsOnPorts(Ljava/lang/String;II)V",
        "public declared-synchronized getNetworkStatsVideoCall()J",
    } if spec["path"] == HANDLER_PATH else {
        "protected getNetworkStatsVideoCall()J",
        "protected requestCallDataUsage()V",
    })
    for match in METHOD_RE.finditer(original):
        header = match.group("header")
        if header not in replaced:
            spans = _method_spans(updated, header)
            if len(spans) != 1 or spans[0][2] != match.group(0):
                raise TransformError(f"unrelated method changed: {header}")

    if spec["path"] == HANDLER_PATH:
        for field in ("mStatsCapability:I", "mStatsUnavailableLogged:Z",
                      "mStatsStartFailed:Z"):
            if len(re.findall(r"(?m)^\.field private " + re.escape(field) + r"\s*$", updated)) != 1:
                raise TransformError(f"BG1 field post-state drift: {field}")
        expected_methods = (
            "private startStatsLocked()V", "private declared-synchronized start()V",
            "private stopStatsLocked()V", "private declared-synchronized stop()V",
            "private startNetworkStatsOnPorts(Ljava/lang/String;II)Z",
            "private stopNetworkStatsOnPorts(Ljava/lang/String;II)V",
            "public declared-synchronized getNetworkStatsVideoCall()J",
            "private statsUnavailable()V", "private hasStatsCapability()Z",
        )
        if any(len(_method_spans(updated, signature)) != 1
               for signature in expected_methods):
            raise TransformError("BG1 handler method post-state drift")
        probe = _method_spans(updated, "private hasStatsCapability()Z")[0][2]
        if (probe.count("->getMethod(") != 3 or
                probe.count("->getReturnType()Ljava/lang/Class;") != 3 or
                "const-class v3, Landroid/net/NetworkStats;" not in probe):
            raise TransformError("BG1 capability probe post-state drift")
        for signature in (
                "private startNetworkStatsOnPorts(Ljava/lang/String;II)Z",
                "private stopNetworkStatsOnPorts(Ljava/lang/String;II)V",
                "public declared-synchronized getNetworkStatsVideoCall()J"):
            body = _method_spans(updated, signature)[0][2]
            if body.index("->hasStatsCapability()Z") > body.index("invoke-interface"):
                raise TransformError("BG1 capability guard ordering drift")
        if "Ljava/lang/Throwable;" in updated:
            raise TransformError("BG1 broad exception catch is forbidden")
    else:
        query = _method_spans(updated, "protected getNetworkStatsVideoCall()J")[0][2]
        request = _method_spans(updated, "protected requestCallDataUsage()V")[0][2]
        if (query.count("const-wide/16 v0, -0x1") != 1 or
                request.count(":stats_unavailable") != 2 or
                request.count("if-ltz v4, :stats_unavailable") != 1):
            raise TransformError("BG1 call-state post-state drift")


def _safe_inputs(root: Path, specs: list[dict]) -> tuple[Path, dict[str, Path]]:
    if root.is_symlink() or not root.is_dir():
        raise TransformError("input root must be a non-symlink directory")
    resolved = root.resolve(strict=True)
    result = {}
    for spec in specs:
        candidate = resolved.joinpath(*PurePosixPath(spec["path"]).parts)
        if candidate.is_symlink() or not candidate.is_file():
            raise TransformError(f"target must be a regular non-symlink file: {spec['path']}")
        actual = candidate.resolve(strict=True)
        try:
            actual.relative_to(resolved)
        except ValueError as exc:
            raise TransformError("target escapes input root") from exc
        cursor = resolved
        for part in PurePosixPath(spec["path"]).parts[:-1]:
            cursor /= part
            if cursor.is_symlink():
                raise TransformError("symlinked target parent is forbidden")
        result[spec["path"]] = actual
    return resolved, result


def _tree_bytes(root: Path) -> dict[str, bytes] | None:
    if root.is_symlink() or not root.is_dir():
        return None
    found = {}
    found_dirs = set()
    for item in root.rglob("*"):
        if item.is_symlink() or (item.is_file() and item.relative_to(root).as_posix() not in EXPECTED_PATHS):
            return None
        if item.is_dir():
            found_dirs.add(item.relative_to(root).as_posix())
        if item.is_file():
            found[item.relative_to(root).as_posix()] = item.read_bytes()
    expected_dirs = set()
    for name in EXPECTED_PATHS:
        parent = PurePosixPath(name).parent
        while parent != PurePosixPath("."):
            expected_dirs.add(parent.as_posix())
            parent = parent.parent
    return found if set(found) == EXPECTED_PATHS and found_dirs == expected_dirs else None


def transform(contract_path: Path, source_root: Path, overlay: Path, report: Path,
              allow_identical: bool = False) -> dict:
    contract = load_contract(contract_path)
    source_abs, inputs = _safe_inputs(source_root, contract["targets"])
    if overlay.is_symlink() or report.is_symlink() or overlay.parent.is_symlink() or report.parent.is_symlink():
        raise TransformError("output paths must not be symlinks")
    if not overlay.parent.is_dir() or not report.parent.is_dir():
        raise TransformError("output parents must be existing directories")
    overlay_abs = overlay.parent.resolve(strict=True) / overlay.name
    report_abs = report.parent.resolve(strict=True) / report.name
    if overlay_abs == report_abs or source_abs == overlay_abs or source_abs in overlay_abs.parents or source_abs == report_abs or source_abs in report_abs.parents:
        raise TransformError("overlay and report must be distinct and outside input tree")
    rendered, files = {}, []
    for spec in contract["targets"]:
        data = inputs[spec["path"]].read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransformError(f"target is not UTF-8: {spec['path']}") from exc
        _assert_pre_state(text, spec["path"])
        _identity(text, spec)
        if hashlib.sha256(data).hexdigest() != spec["input_sha256"]:
            raise TransformError(f"input hash drift: {spec['path']}")
        updated = _handler(text) if spec["path"] == HANDLER_PATH else _call_state(text)
        _post_validate(text, updated, spec)
        marker_count = (updated.count("BG1: video usage unavailable") if spec["path"] == HANDLER_PATH
                        else len(re.findall(r"(?m)^\s*:stats_unavailable\s*$", updated)))
        if marker_count != spec["expected_post"]:
            raise TransformError("post-state validation failed")
        output = updated.encode("utf-8")
        rendered[spec["path"]] = output
        files.append({"target": spec["path"], "hooks": ["optional_stats_guard"],
                      "input_sha256": hashlib.sha256(data).hexdigest(),
                      "output_sha256": hashlib.sha256(output).hexdigest()})
    payload = {"schema_version": 1, "transformation_id": TRANSFORMATION_ID,
               "changed": True, "files": files}
    report_data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    if overlay.exists() or report.exists():
        if allow_identical and report.is_file() and report.read_bytes() == report_data and _tree_bytes(overlay) == rendered:
            result = dict(payload); result["changed"] = False
            return result
        raise TransformError("refusing to overwrite existing overlay or report")
    temp_overlay = Path(tempfile.mkdtemp(prefix=f".{overlay.name}.", dir=overlay.parent))
    fd, temp_name = tempfile.mkstemp(prefix=f".{report.name}.", suffix=".tmp", dir=report.parent)
    os.close(fd); temp_report = Path(temp_name); report_published = False
    try:
        for name, data in rendered.items():
            target = temp_overlay.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        with temp_report.open("wb") as handle:
            handle.write(report_data); handle.flush(); os.fsync(handle.fileno())
        os.link(temp_report, report_abs); report_published = True
        os.rename(temp_overlay, overlay_abs)
    except BaseException:
        if report_published:
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
        result = transform(args.contract, args.input_smali_root, args.output_overlay, args.report, args.allow_identical)
    except (OSError, TransformError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 1
    print(json.dumps(result, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
