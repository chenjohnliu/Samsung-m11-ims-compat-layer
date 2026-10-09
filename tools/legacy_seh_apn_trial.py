#!/usr/bin/env python3
"""Prepare/apply/restore the opt-in SEH1+LG3 source batch. Never build a ROM."""

import argparse
import json
import os
from pathlib import Path
import tempfile
import zipfile

import build_legacy_wfc_gate as LG3
import legacy_epdg_prefix_compat as LG2
import legacy_iwlan_trial as LEG1
import legacy_service_state_compat as SS1

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / "devices/m11q/seh-apn-bridge-build.json"
JAVA_PREFIX = "frameworks/opt/telephony/src/java/com/android/internal/telephony/"
RIL = JAVA_PREFIX + "RIL.java"
DPM = JAVA_PREFIX + "data/DataProfileManager.java"
PROP = "device/samsung/m11q/system.prop"
POLICY = "device/samsung/m11q/ims/sepolicy/system_ext/private/"
IMS = "device/samsung/m11q/ims/proprietary/priv-app/imsservice/imsservice.apk"
FLAG = "ro.m11q.ims_seh_apn_bridge"
TRIAL = "SEH1-LG3-legacy-apn-callback"
EXPECTED = {
    RIL: "6c59a33b2858d18545fe1d563f17cbef3c1d15f1e54bc3acde53415a4a508b2c",
    DPM: "59c631db824716216805f8d938405cc0fdf02685d4be1b7b22ff7170a17645b8",
    PROP: "9487ecb87ab0db357e9fdfa0a63acfdcad59dd98df12bfb92d8d3d110e11ef7f",
    POLICY + "property.te": "92abe6f6d72ecf6598fd33ea5adf2aee564076b64a7143f76b50c47e2ba46c5e",
    POLICY + "property_contexts": "bf1c431dd31b40708b723fc00a139e3f0d2e2bc78cd419ad9f00ac9861a6a2b2",
    POLICY + "radio.te": "2193e5a04975f65799faa0d37f4eed707da764cfbf271b5f25b3f7a284313d17",
    IMS: LG3.BASE_APK,
}
RIL_ANCHOR = b'''        if (RILJ_LOGD) {
            riljLog("Radio HAL version: " + mRadioVersion);
        }
    }
'''
RIL_HOOK = b'''        // SEH1: one opt-in Samsung callback owner; no standard-radio requests.
        if (proxies == null) M11SehRadioBridge.maybeStart(this, mContext, mPhoneId);
'''
DPM_ANCHOR = b"        updateDataProfilesAtModem();\n        updateInitialAttachDataProfileAtModem(forceUpdateIa);"
DPM_HOOK = b'''        // SEH1: immutable snapshot on this handler, including unchanged-profile updates.
        com.android.internal.telephony.M11SehProfilePublisher.publish(mPhone, mAllDataProfiles);

'''


def java_assets():
    pins = json.loads(LEG1.regular(PINS).read_text())
    if pins.get("schema_version") != 1 or pins.get("transformation_id") != TRIAL:
        raise ValueError("SEH1 source pin identity drift")
    expected = {"M11SehApnPolicy.java", "M11SehRadioTransport.java",
                "M11SehRadioBridge.java", "M11SehProfilePublisher.java"}
    if set(pins["java_sources"]) != expected:
        raise ValueError("SEH1 Java inventory drift")
    result = {}
    for name, digest in pins["java_sources"].items():
        data = LEG1.regular(ROOT / "platform/java/com/android/internal/telephony" / name).read_bytes()
        if LEG1.sha(data) != digest:
            raise ValueError("SEH1 Java source pin drift: " + name)
        result[JAVA_PREFIX + name] = data
    return result


def prerequisites(root):
    for relative, digest in LEG1.PREREQUISITES.items():
        if relative == IMS: continue
        if LEG1.sha(LEG1.regular(root / relative).read_bytes()) != digest:
            raise ValueError("legacy prerequisite drift: " + relative)
    LEG1.validate_vendor(LEG1.binary_xml(LEG1.regular(root / LEG1.VENDOR).read_bytes()))


def candidates(original, apk, assets, legacy_comment=False):
    result = dict(original)
    for relative, anchor, hook in ((RIL, RIL_ANCHOR, RIL_HOOK), (DPM, DPM_ANCHOR, DPM_HOOK)):
        if result[relative].count(anchor) != 1 or hook in result[relative]:
            raise ValueError("source hook anchor drift: " + relative)
        if relative == RIL:
            result[relative] = result[relative].replace(anchor, anchor[:-6] + hook + b"    }\n", 1)
        else:
            result[relative] = result[relative].replace(anchor, hook + anchor, 1)
    scope = "slot0/TWM only" if legacy_comment else "slot0, all operators"
    result[PROP] += ("\n# SEH1 opt-in stock APN callback restoration, " + scope + ".\n").encode() + (FLAG + "=true\n").encode()
    result[POLICY + "property.te"] += b"\n# SEH1 exact read-only trial property.\nsystem_internal_prop(m11q_seh_trial_prop)\n"
    result[POLICY + "property_contexts"] += ("\n" + FLAG + " u:object_r:m11q_seh_trial_prop:s0 exact bool\n").encode()
    result[POLICY + "radio.te"] += b"\n# SEH1: no broader hardware-service or default-property grants.\nget_prop(radio, m11q_seh_trial_prop)\n"
    result[IMS] = apk
    result.update(assets)
    return result


def prepare(root, state, apk, report):
    root, state = LEG1.source_root(root), LEG1.safe(state)
    if state == root or root in state.parents:
        raise ValueError("private backup state must be outside the Android checkout")
    if state.exists():
        raise ValueError("state already exists; use verify-source/apply/rollback")
    prerequisites(root)
    assets = java_assets()
    original = {r: LEG1.regular(root / r).read_bytes() for r in EXPECTED}
    for relative, digest in EXPECTED.items():
        if LEG1.sha(original[relative]) != digest:
            raise ValueError("unrecognized source input: " + relative)
    for relative in assets:
        if LEG1.safe(root / relative).exists():
            raise ValueError("pre-existing bridge source refused: " + relative)
    pins = LG3.load_pins(LG3.DEFAULT_PINS)
    data = LEG1.regular(apk).read_bytes()
    evidence = json.loads(LEG1.regular(report).read_text())
    if (LEG1.sha(data) != pins["unsigned_apk_sha256"] or evidence.get("mode") != "strict"
            or evidence.get("status") != "PASS" or evidence.get("observed_build_pins") != pins
            or not all(evidence.get("output", {}).get(k) is True for k in
                ("strict_pins_verified", "artifact_published", "all_redecoded_classes_verified",
                 "unrelated_zip_entries_preserved"))):
        raise ValueError("complete strict LG3 artifact/report required")
    LG3.verify_apk(apk)
    candidate = candidates(original, data, assets)
    if not state.parent.is_dir(): raise ValueError("backup state parent must exist")
    state.mkdir(mode=0o700)
    entries = {}
    for relative, value in candidate.items():
        target = state / "candidate" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
        old = original.get(relative)
        if old is not None:
            backup = state / "original" / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(old)
        entries[relative] = {"original_sha256": None if old is None else LEG1.sha(old),
                             "candidate_sha256": LEG1.sha(value)}
    (state / "manifest.json").write_text(json.dumps({"schema_version": 1,
        "transformation_id": TRIAL, "android_root": str(root), "carrier_scope": "all", "files": entries}, indent=2) + "\n")
    return verify_source(root, state, expected="original")


def bundle(root, state):
    root, state = LEG1.source_root(root), LEG1.safe(state)
    manifest = json.loads(LEG1.regular(state / "manifest.json").read_text())
    if (manifest.get("schema_version") != 1 or manifest.get("transformation_id") != TRIAL
            or manifest.get("android_root") != str(root)
            or set(manifest["files"]) != set(EXPECTED) | set(java_assets())):
        raise ValueError("private staging manifest drift")
    original, candidate = {}, {}
    for relative, info in manifest["files"].items():
        old = info["original_sha256"]
        original[relative] = None if old is None else LEG1.regular(state / "original" / relative).read_bytes()
        candidate[relative] = LEG1.regular(state / "candidate" / relative).read_bytes()
        if (old is not None and (old != EXPECTED.get(relative) or LEG1.sha(original[relative]) != old)
                or LEG1.sha(candidate[relative]) != info["candidate_sha256"]):
            raise ValueError("backup/candidate hash drift: " + relative)
    rebuilt = candidates({r: b for r, b in original.items() if b is not None},
                         candidate[IMS], java_assets(), legacy_comment=manifest.get("carrier_scope") != "all")
    if rebuilt != candidate or LEG1.sha(candidate[IMS]) != LG3.load_pins(LG3.DEFAULT_PINS)["unsigned_apk_sha256"]:
        raise ValueError("candidate no longer matches reviewed source/artifact")
    return original, candidate


def observed(root, relatives):
    result = {}
    for relative in relatives:
        path = LEG1.safe(root / relative)
        result[relative] = LEG1.regular(path).read_bytes() if path.exists() else None
    return result


def verify_source(root, state, expected="candidate"):
    root = LEG1.source_root(root)
    prerequisites(root)
    original, candidate = bundle(root, state)
    actual = observed(root, candidate)
    target = original if expected == "original" else candidate
    if actual != target: raise ValueError("source drift/mixed state; do not build")
    return {"status": "PASS", "trial": TRIAL, "source_state": expected,
            "rom_build_run": False, "runtime_validated": False,
            "source_hashes": {r: None if b is None else LEG1.sha(b) for r, b in actual.items()}}


def replace(path, old, new):
    path = LEG1.safe(path)
    current = LEG1.regular(path).read_bytes() if path.exists() else None
    if current != old: raise ValueError("concurrent source edit refused: " + str(path))
    if new is None:
        path.unlink()  # Only an exact, known trial source file is removed on rollback.
    elif old is not None:
        LEG1.atomic_replace(path, old, new)
    else:
        if not path.parent.is_dir(): raise ValueError("source parent absent")
        descriptor, name = tempfile.mkstemp(prefix=".seh1-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream: stream.write(new)
            os.chmod(temporary, 0o644)
            os.link(temporary, path)  # Exclusive publication; never overwrite a concurrent creation.
        finally:
            temporary.unlink(missing_ok=True)


def change(root, state, rollback=False):
    root = LEG1.source_root(root)
    prerequisites(root)
    original, candidate = bundle(root, state)
    target = original if rollback else candidate
    before = observed(root, candidate)
    for relative, value in before.items():
        if value not in (original[relative], candidate[relative]):
            raise ValueError("unrelated source edit refused: " + relative)
    changed = []
    try:
        for relative, value in target.items():
            if before[relative] == value: continue
            replace(root / relative, before[relative], value)
            changed.append(relative)
        answer = verify_source(root, state, "original" if rollback else "candidate")
    except Exception:
        for relative in reversed(changed):
            current = observed(root, [relative])[relative]
            if current == target[relative]: replace(root / relative, current, before[relative])
        raise
    return {**answer, "source_changed": bool(changed), "rollback": rollback}


def refresh_assets(root, state, history):
    """Upgrade a verified prior batch without discarding its original rollback backup."""
    root, state, history = LEG1.source_root(root), LEG1.safe(state), LEG1.safe(history)
    if history == root or root in history.parents or history.exists():
        raise ValueError("fresh revision backup outside source checkout required")
    prerequisites(root)
    manifest = json.loads(LEG1.regular(state / "manifest.json").read_text())
    assets = java_assets()
    if (manifest.get("schema_version") != 1 or manifest.get("transformation_id") != TRIAL
            or manifest.get("android_root") != str(root)
            or set(manifest["files"]) != set(EXPECTED) | set(assets)):
        raise ValueError("prior batch identity drift")
    original, previous = {}, {}
    for relative, info in manifest["files"].items():
        old = info["original_sha256"]
        original[relative] = None if old is None else LEG1.regular(state / "original" / relative).read_bytes()
        previous[relative] = LEG1.regular(state / "candidate" / relative).read_bytes()
        if (old is not None and (old != EXPECTED.get(relative) or LEG1.sha(original[relative]) != old)
                or LEG1.sha(previous[relative]) != info["candidate_sha256"]):
            raise ValueError("prior backup/candidate drift: " + relative)
    prior_assets = {r: previous[r] for r in assets}
    source_original = {r: b for r, b in original.items() if b is not None}
    if candidates(source_original, previous[IMS], prior_assets,
                  legacy_comment=manifest.get("carrier_scope") != "all") != previous:
        raise ValueError("prior deterministic batch drift")
    if observed(root, previous) != previous:
        raise ValueError("live source drift; upgrade refused")
    updated = candidates(source_original, previous[IMS], assets)
    changed = [r for r in previous if previous[r] != updated[r]]
    history.mkdir(mode=0o700)
    (history / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for relative in changed:
        old_target = history / "candidate" / relative
        old_target.parent.mkdir(parents=True, exist_ok=True)
        old_target.write_bytes(previous[relative])
    # Known exact contents only; rollback applied files on any write failure.
    completed = []
    try:
        for relative in changed:
            replace(root / relative, previous[relative], updated[relative])
            completed.append(relative)
        for relative in changed:
            replace(state / "candidate" / relative, previous[relative], updated[relative])
            manifest["files"][relative]["candidate_sha256"] = LEG1.sha(updated[relative])
        manifest["carrier_scope"] = "all"
        (state / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return {**verify_source(root, state), "carrier_scope": "all", "changed": changed}
    except Exception:
        for relative in reversed(completed):
            if observed(root, [relative])[relative] == updated[relative]:
                replace(root / relative, updated[relative], previous[relative])
        for relative in changed:
            candidate_path = state / "candidate" / relative
            if candidate_path.read_bytes() == updated[relative]:
                replace(candidate_path, updated[relative], previous[relative])
        (state / "manifest.json").write_bytes((history / "manifest.json").read_bytes())
        raise


def verify_product(product):
    root = LEG1.source_root(product)
    properties = {LEG1.MODE: [], LEG1.LABEL: [], FLAG: []}
    for relative in ("system/build.prop", "vendor/build.prop", "product/etc/build.prop",
                     "system/system_ext/etc/build.prop", "odm/etc/build.prop"):
        path = root / relative
        if not path.exists(): continue
        for line in LEG1.regular(path).read_text().splitlines():
            if line.strip().startswith("#") or "=" not in line: continue
            key, value = line.strip().split("=", 1)
            if key in properties: properties[key].append(value)
    if properties != {LEG1.MODE: ["legacy"], LEG1.LABEL: ["legacy-r1"], FLAG: ["true"]}:
        raise ValueError("packaged trial properties mismatch; do not flash")
    overlay = root / "vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk"
    with zipfile.ZipFile(LEG1.regular(overlay)) as archive:
        if archive.namelist().count("res/xml/vendor.xml") != 1: raise ValueError("overlay XML inventory drift")
        data = archive.read("res/xml/vendor.xml")
        if data.lstrip().startswith(b"<"): raise ValueError("compiled CarrierConfig XML required")
        LEG1.validate_vendor(LEG1.binary_xml(data))
    apks = root / "system/system_ext/priv-app"
    LG3.verify_apk(apks / "imsservice/imsservice.apk")
    LG2.verify_apk(apks / "EpdgService/EpdgService.apk", ROOT / "devices/m11q/legacy-epdg-prefix-build.json")
    SS1.verify_framework(root / "system/framework/framework.jar")
    # Defined method checks, not descriptor/string hits. Preserved public entry points are
    # already covered by telephony-common's existing public/protected ProGuard rules.
    jar = LEG1.regular(root / "system/framework/telephony-common.jar")
    required = {
        "M11SehRadioBridge": "maybeStart(Lcom/android/internal/telephony/RIL;Landroid/content/Context;I)V",
        "M11SehProfilePublisher": "publish(Lcom/android/internal/telephony/Phone;Ljava/util/List;)V",
        "M11SehRadioTransport": "register(Landroid/os/IHwBinder;)V",
        "M11SehApnPolicy": "fallback(Lcom/android/internal/telephony/M11SehApnPolicy$Snapshot;IILjava/lang/String;Ljava/lang/String;Z)Lcom/android/internal/telephony/M11SehApnPolicy$Profile;",
    }
    with zipfile.ZipFile(jar) as archive:
        names = [n for n in archive.namelist() if n.startswith("classes") and n.endswith(".dex")]
        if not names or len(names) != len(set(names)): raise ValueError("telephony DEX inventory drift")
        for owner, method in required.items():
            methods = [method]
            if owner == "M11SehApnPolicy": methods.append("validOperator(Ljava/lang/String;)Z")
            definitions = []
            for name in names:
                definitions.extend(SS1.dex_definitions(archive.read(name),
                    "Lcom/android/internal/telephony/" + owner + ";"))
            if len(definitions) != 1 or any(m not in definitions[0] for m in methods):
                raise ValueError("packaged SEH1 defined method missing: " + owner)
            for signature in methods:
                flags, _, code = definitions[0][signature]
                if (not flags & 1 or flags & 0x506 or not code
                        or bool(flags & 8) != (owner != "M11SehRadioTransport")):
                    raise ValueError("packaged SEH1 entry point invalid: " + owner)
    return {"status": "PASS", "trial": TRIAL, "rom_build_run": False,
            "runtime_validated": False, "signature_verified": False,
            "telephony_jar_sha256": LEG1.sha(jar.read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "apply", "refresh-assets", "verify-source", "rollback", "verify-product"))
    for name in ("android-root", "state-dir", "apk", "build-report", "product-root", "revision-backup"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    try:
        if args.action == "verify-product":
            if args.product_root is None: raise ValueError("--product-root required")
            result = verify_product(args.product_root)
        else:
            if args.android_root is None or args.state_dir is None:
                raise ValueError("--android-root and --state-dir required")
            if args.action == "prepare":
                if args.apk is None or args.build_report is None: raise ValueError("--apk and --build-report required")
                result = prepare(args.android_root, args.state_dir, args.apk, args.build_report)
            elif args.action == "refresh-assets":
                if args.revision_backup is None: raise ValueError("--revision-backup required")
                result = refresh_assets(args.android_root, args.state_dir, args.revision_backup)
            elif args.action == "verify-source": result = verify_source(args.android_root, args.state_dir)
            else: result = change(args.android_root, args.state_dir, args.action == "rollback")
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(2, "error: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
