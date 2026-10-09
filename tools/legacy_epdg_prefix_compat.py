#!/usr/bin/env python3
"""Build or discover pins for the LG2 legacy ePDG mobile-prefix fix.

LG2 starts from the exact EC2-r2 unsigned APK.  It changes only
EpdgUtils.getMobileInterfacePrefix(): Samsung's existing explicit ``legacy``
mode uses the radio-provided mobile prefix, while AP-assisted/default/unknown
modes retain EC1's ``epdg_data`` namespace.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = "com/sec/epdg/EpdgUtils.smali"
TRANSFORMATION_ID = "LG2-legacy-epdg-prefix"
INPUT_SHA256 = "0346f97e367857a329cea2d43dc4936f42d0e2e16d19e81f046d5380593a43d9"
BASE_APK_SHA256 = "4c7cca55f8647fd49e4d91b0c600033fcbbab71292fb039c53cbf289c0fc63bc"
BASE_DEX_SHA256 = "d8a7f8b1c22777b1e205e3dbf5b47db2b9fa2c37b2a403c8f527ee17e0753f1d"
DEFAULT_PINS = ROOT / "devices/m11q/legacy-epdg-prefix-build.json"

ORIGINAL_METHOD = """.method public static final getMobileInterfacePrefix()Ljava/lang/String;
    .locals 2

    .line 699
    const-string v0, "epdg_data"

    return-object v0
.end method"""

PATCHED_METHOD = """.method public static final getMobileInterfacePrefix()Ljava/lang/String;
    .locals 2

    invoke-static {}, Lcom/sec/epdg/EpdgUtils;->isIwlanLegacyMode()Z

    move-result v0

    if-eqz v0, :cond_lg2_ap_assist

    const-string v0, "ril.data.intfprefix"

    const-string v1, "rmnet"

    invoke-static {v0, v1}, Landroid/os/SystemProperties;->get(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    return-object v0

    :cond_lg2_ap_assist
    const-string v0, "epdg_data"

    return-object v0
.end method"""

LEGACY_HELPER = """.method public static isIwlanLegacyMode()Z
    .locals 2

    .line 1315
    const-string v0, "ro.telephony.iwlan_operation_mode"

    invoke-static {v0}, Landroid/os/SystemProperties;->get(Ljava/lang/String;)Ljava/lang/String;

    move-result-object v0

    .line 1316
    .local v0, "mode":Ljava/lang/String;
    const-string v1, "legacy"

    invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z

    move-result v1

    return v1
.end method"""


def sha(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def patch(text: str) -> str:
    """Return the exact LG2 class, refusing unknown or partial input."""
    if sha(text) != INPUT_SHA256:
        raise ValueError("unrecognized canonical EC2 EpdgUtils input")
    if text.count(ORIGINAL_METHOD) != 1 or PATCHED_METHOD in text:
        raise ValueError("mobile-prefix method anchor drift")
    if text.count(LEGACY_HELPER) != 1:
        raise ValueError("isIwlanLegacyMode helper semantics drift")
    result = text.replace(ORIGINAL_METHOD, PATCHED_METHOD, 1)
    if result.count(PATCHED_METHOD) != 1 or ORIGINAL_METHOD in result:
        raise ValueError("incomplete mobile-prefix transformation")
    return result


def modeled_prefix(mode: str | None, radio_prefix: str | None = None) -> str:
    """Executable model of the tiny smali branch, used by focused tests."""
    if mode == "legacy":
        return radio_prefix if radio_prefix is not None else "rmnet"
    return "epdg_data"


def modeled_profile_id(interface: str, mode: str | None, radio_prefix: str | None = None) -> int:
    prefix = modeled_prefix(mode, radio_prefix)
    try:
        return int(interface[len(prefix):]) + 1
    except (ValueError, IndexError):
        return -3


def _module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load project tool: {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BASE = _module("lg2_base_builder", "tools/build_epdgservice.py")
EC2 = _module("lg2_ec2_builder", "tools/build_epdgservice_w2l_trial.py")
BuildError = BASE.BuildError


def load_pins(path: Path) -> dict:
    raw = json.loads(BASE._regular(path, "LG2 build pins").read_text(encoding="utf-8"))
    required = {"schema_version", "transformation_id", "classes_dex_sha256",
                "unsigned_apk_sha256"}
    if set(raw) != required or raw["schema_version"] != 1 or raw["transformation_id"] != TRANSFORMATION_ID:
        raise BuildError("LG2 build pin schema/identity drift")
    for key in required - {"schema_version", "transformation_id"}:
        value = raw[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise BuildError("LG2 output pins must be promoted SHA-256 values")
    return raw


def verify_apk(apk: Path, pins_path: Path = DEFAULT_PINS) -> dict:
    """Verify the packaged LG2 DEX; APK byte identity is informational.

    Product signing and ZIP alignment can change the APK hash.  The promoted
    primary-DEX pin is therefore the install gate, while the unsigned APK hash
    reports whether the artifact is the byte-identical builder output.
    """
    apk = BASE._regular(Path(apk), "LG2 EpdgService APK")
    pins = load_pins(Path(pins_path))
    entries = BASE._zip_entries(apk)
    dex_names = sorted(name for name in entries if name.startswith("classes") and name.endswith(".dex"))
    if dex_names != ["classes.dex"]:
        raise BuildError("LG2 APK must contain exactly one primary DEX")
    dex_hash = hashlib.sha256(entries["classes.dex"]).hexdigest()
    if dex_hash != pins["classes_dex_sha256"]:
        raise BuildError("packaged LG2 classes.dex pin mismatch")
    apk_hash = BASE.sha256_file(apk)
    return {"status": "PASS", "transformation_id": TRANSFORMATION_ID,
            "classes_dex_sha256": dex_hash, "apk_sha256": apk_hash,
            "unsigned_apk_byte_identical": apk_hash == pins["unsigned_apk_sha256"]}


def _write_report(path: Path, payload: dict) -> None:
    if path.exists() or path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink():
        raise BuildError("unsafe or existing report path")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def build(args: argparse.Namespace) -> dict:
    zipper = _module("lg2_zipper", "tools/apk_entry_replace.py")
    base_apk = BASE._pinned(args.base_apk, "EC2-r2 unsigned APK", BASE_APK_SHA256)
    java = BASE._pinned(args.java, "Java runtime", BASE.JAVA_SHA256)
    apktool = BASE._pinned(args.apktool_jar, "apktool JAR", BASE.APKTOOL_SHA256)
    before_entries = BASE._zip_entries(base_apk)
    if hashlib.sha256(before_entries.get("classes.dex", b"")).hexdigest() != BASE_DEX_SHA256:
        raise BuildError("EC2-r2 classes.dex identity drift")
    discovery = args.discover_pins
    pins = None if discovery else load_pins(args.pins)
    if discovery and args.output:
        raise BuildError("pin discovery cannot publish an APK")
    if not discovery and not args.output:
        raise BuildError("strict mode requires --output")
    if args.report.exists() or args.report.is_symlink() or (args.output and (args.output.exists() or args.output.is_symlink())):
        raise BuildError("refusing to overwrite output or report")
    if args.work_dir and (args.work_dir.is_symlink() or not args.work_dir.is_dir()):
        raise BuildError("unsafe work directory")

    stage = Path(tempfile.mkdtemp(prefix="lg2-epdg-prefix-", dir=args.work_dir))
    try:
        decoded, verified = stage / "decoded", stage / "verified"
        command = [str(java), "-XX:ActiveProcessorCount=1", "-jar", str(apktool)]
        BASE._run(command + ["d", "-f", "-o", str(decoded), str(base_apk)], "EC2-r2 APK decode")
        before_classes = BASE._smali_inventory(decoded / "smali")
        target = decoded / "smali" / TARGET
        if before_classes.get(TARGET) != INPUT_SHA256 or target.is_symlink() or not target.is_file():
            raise BuildError("canonical EC2 EpdgUtils identity drift")
        original = target.read_text(encoding="utf-8")
        transformed = patch(original)
        target.write_text(transformed, encoding="utf-8", newline="")

        rebuilt = stage / "rebuilt.apk"
        BASE._run(command + ["b", str(decoded), "-o", str(rebuilt)], "LG2 APK assembly")
        dex = stage / "classes.dex"
        dex.write_bytes(BASE._zip_entries(rebuilt)["classes.dex"])
        candidate = stage / "candidate.apk"
        zip_report = zipper.build_archive(base_apk, candidate, {"classes.dex": dex}, {})
        after_entries = BASE._zip_entries(candidate)
        if set(after_entries) != set(before_entries) or any(
                after_entries[name] != content for name, content in before_entries.items() if name != "classes.dex"):
            raise BuildError("unrelated EC2-r2 APK entry changed")
        if {item["entry"] for item in zip_report["changed_entries"]} != {"classes.dex"}:
            raise BuildError("LG2 changed an unexpected APK entry")

        BASE._run(command + ["d", "-f", "-o", str(verified), str(candidate)], "LG2 APK re-decode")
        after_classes = BASE._smali_inventory(verified / "smali")
        if set(after_classes) != set(before_classes):
            raise BuildError("LG2 class inventory drift")
        for relative in set(before_classes) - {TARGET}:
            if after_classes[relative] != before_classes[relative]:
                raise BuildError(f"LG2 unrelated class changed: {relative}")
        final_text = (verified / "smali" / TARGET).read_text(encoding="utf-8")
        if EC2.normalized_smali(transformed) != EC2.normalized_smali(final_text):
            raise BuildError("LG2 target instruction round-trip drift")

        observed = {
            "schema_version": 1,
            "transformation_id": TRANSFORMATION_ID,
            "classes_dex_sha256": BASE.sha256_file(dex),
            "unsigned_apk_sha256": BASE.sha256_file(candidate),
        }
        if pins is not None and observed != pins:
            raise BuildError("LG2 final APK/DEX/redecoded pin drift")
        payload = {
            "schema_version": 1, "status": "PASS", "transformation_id": TRANSFORMATION_ID,
            "mode": "pin-discovery" if discovery else "strict", "observed_build_pins": observed,
            "observed_redecoded_target_sha256": after_classes[TARGET],
            "inputs": {"base_apk_sha256": BASE_APK_SHA256, "base_classes_dex_sha256": BASE_DEX_SHA256,
                       "epdg_utils_sha256": INPUT_SHA256},
            "toolchain": {"apktool_sha256": BASE.APKTOOL_SHA256, "java_sha256": BASE.JAVA_SHA256},
            "transformation": {"target": TARGET, "methods": ["getMobileInterfacePrefix()Ljava/lang/String;"],
                               "existing_mode_helper": "isIwlanLegacyMode()Z", "default_or_unknown_mode": "ap-assisted"},
            "output": {"strict_pins_verified": not discovery, "artifact_published": not discovery,
                       "all_redecoded_classes_verified": True, "unrelated_zip_entries_preserved": True,
                       "signed": False, "runtime_validated": False},
            "safety": {"rom_build_run": False, "source_tree_changed": False,
                       "saved_decoded_payload_used": False},
        }
        if discovery:
            _write_report(args.report, payload)
        else:
            BASE._publish(candidate, args.output, args.report, payload)
        return payload
    finally:
        if getattr(args, "keep_work", False):
            print(f"retained diagnostic work directory: {stage}", file=sys.stderr)
        else:
            shutil.rmtree(stage, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("base-apk", "apktool-jar", "java", "report"):
        result.add_argument("--" + name, required=True, type=Path)
    result.add_argument("--output", type=Path)
    result.add_argument("--pins", type=Path, default=DEFAULT_PINS)
    result.add_argument("--work-dir", type=Path)
    result.add_argument("--discover-pins", action="store_true")
    result.add_argument("--keep-work", action="store_true")
    return result


def main(argv=None) -> int:
    try:
        result = build(parser().parse_args(argv))
    except (OSError, ValueError, RuntimeError, BuildError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "mode": result["mode"],
                      **result["observed_build_pins"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
