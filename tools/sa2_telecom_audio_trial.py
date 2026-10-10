#!/usr/bin/env python3
"""Manage the hash-checked integrated stock-derived Telecom audio port; never build Android.

The historical filename and backup identity remain compatible with prior source backups.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path("src/com/android/server/telecom")
INPUTS = {
    "CallAudioManager.java": "4ad1e8a81e787ed12fb00d7e63a0fe714f656abdde416ac70161ce7e3e7349fb",
    "CallAudioModeStateMachine.java": "7ea173141df3e7751bde7f2106e5020912d62bb65f6bcf6c59f1c9904cdd1c66",
}
HELPERS = ("SamsungImsAudioHandover.java", "SamsungImsAudioTransition.java")

MANAGER_FIELDS = '''    // SA2: call-scoped stock Telecom audio transition, not a Wi-Fi broadcast hook.
    private final SamsungImsAudioHandover mSamsungImsAudioHandover =
            new SamsungImsAudioHandover();
    private final Call.Listener mSamsungImsAudioListener = new Call.ListenerBase() {
        @Override public void onConnectionPropertiesChanged(Call call, boolean didRttChange) {
            onSamsungImsAudioCallChanged(call);
        }
        @Override public void onExtrasChanged(Call call, int source, android.os.Bundle extras) {
            onSamsungImsAudioCallChanged(call);
        }
    };

'''

MANAGER_METHODS = '''    private void onSamsungImsAudioCallChanged(Call call) {
        if (call != mForegroundCall || !SamsungImsAudioHandover.enabled()) return;
        mCallAudioModeStateMachine.sendMessageWithArgs(
                CallAudioModeStateMachine.FOREGROUND_VOIP_MODE_CHANGE,
                makeArgsForModeStateMachine());
    }

    private void observeSamsungImsAudioCall() {
        Call call = mForegroundCall;
        boolean allowed = call != null && mCalls.size() == 1 && mCalls.contains(call)
                && call.getState() == CallState.ACTIVE && !call.isEmergencyCall()
                && !call.isConference() && call.getParentCall() == null
                && !call.isSelfManaged() && !call.isExternalCall()
                && !VideoProfile.isVideo(call.getVideoState()) && !call.getIsVoipAudioMode();
        boolean wifi = call != null && call.hasProperty(Connection.PROPERTY_WIFI);
        int phoneId = -1;
        int subId = SubscriptionManager.INVALID_SUBSCRIPTION_ID;
        if (allowed) {
            PhoneAccountHandle account = call.getTargetPhoneAccount();
            subId = account == null ? SubscriptionManager.INVALID_SUBSCRIPTION_ID
                    : mCallsManager.getPhoneAccountRegistrar().getSubscriptionIdForPhoneAccount(account);
            phoneId = SubscriptionManager.getPhoneId(subId);
            allowed = account != null && "com.android.phone".equals(
                    account.getComponentName().getPackageName())
                    && SubscriptionManager.isValidSubscriptionId(subId)
                    && SamsungImsAudioHandover.singleSubscriptionMatches(
                            mCallsManager.getContext(), phoneId, subId);
            // Never infer an LTE source merely from "not Wi-Fi". Phone reports the call RAT.
            if (allowed && !wifi && !mSamsungImsAudioHandover.owns(call, phoneId, subId)) {
                allowed = call.getExtras() != null && call.getExtras().getInt(
                        android.telecom.TelecomManager.EXTRA_CALL_NETWORK_TYPE,
                        android.telephony.TelephonyManager.NETWORK_TYPE_UNKNOWN)
                        == android.telephony.TelephonyManager.NETWORK_TYPE_LTE;
            }
        }
        mSamsungImsAudioHandover.observe(call, allowed, wifi, phoneId, subId);
    }

    boolean setSamsungImsHandoverAudioMode(android.media.AudioManager audio, int mode) {
        return mSamsungImsAudioHandover.setMode(audio, mode, mCallsManager.getContext());
    }

    void finishSamsungImsHandoverAudioMode(android.media.AudioManager audio) {
        mSamsungImsAudioHandover.finish(audio);
    }

'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def target(source, name):
    path = source / PREFIX / name
    if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
        raise ValueError(f"unsafe source target: {path}")
    return path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"source anchor drift: {old[:100]!r}")
    return text.replace(old, new)


def render(source, baseline=None):
    results = {}
    for name, digest in INPUTS.items():
        path = target(source, name)
        data = path.read_bytes() if baseline is None else baseline[name]
        if path.is_symlink() or sha(data) != digest:
            raise ValueError(f"baseline source drift: {path}; no files changed")
        results[name] = data.decode("utf-8")
    text = results["CallAudioManager.java"]
    text = replace_once(text, "    private Call mForegroundCall;\n",
                        MANAGER_FIELDS + "    private Call mForegroundCall;\n")
    text = replace_once(text, "        mCalls.add(call);\n",
                        "        mCalls.add(call);\n        call.addListener(mSamsungImsAudioListener);\n")
    text = replace_once(text, "        mCalls.remove(call);\n        sendCallStatusToBluetoothStateReceiver();\n",
                        "        mCalls.remove(call);\n        call.removeListener(mSamsungImsAudioListener);\n"
                        "        sendCallStatusToBluetoothStateReceiver();\n")
    text = replace_once(text, "    private CallAudioModeStateMachine.MessageArgs makeArgsForModeStateMachine() {\n",
                        "    private CallAudioModeStateMachine.MessageArgs makeArgsForModeStateMachine() {\n"
                        "        observeSamsungImsAudioCall();\n")
    text = replace_once(text, "    /**\n     * Starts Samsung's ePDG audio path",
                        MANAGER_METHODS + "    /**\n     * Starts Samsung's ePDG audio path")
    text = replace_once(text, "        return call.getIsVoipAudioMode();\n",
                        "        return call.getIsVoipAudioMode() || mSamsungImsAudioHandover.isVoip(call);\n")
    results["CallAudioManager.java"] = text
    text = results["CallAudioModeStateMachine.java"]
    text = replace_once(text, "                mAudioManager.setMode(AudioManager.MODE_NORMAL);\n",
                        "                mCallAudioManager.finishSamsungImsHandoverAudioMode(mAudioManager);\n"
                        "                mAudioManager.setMode(AudioManager.MODE_NORMAL);\n")
    for mode in ("MODE_IN_CALL", "MODE_IN_COMMUNICATION"):
        old = f"            mAudioManager.setMode(AudioManager.{mode});\n"
        new = ("            // SA2: preserve Telecom ownership and stock STOP/mode/engine ordering.\n"
               f"            if (!mCallAudioManager.setSamsungImsHandoverAudioMode(mAudioManager, AudioManager.{mode})) {{\n"
               f"                mAudioManager.setMode(AudioManager.{mode});\n"
               "            }\n")
        text = replace_once(text, old, new)
    results["CallAudioModeStateMachine.java"] = text
    for name in HELPERS:
        results[name] = (ROOT / "platform/telecom/sa2" / name).read_text(encoding="utf-8")
    return results


def prepare(source, output):
    results = render(source)  # Validate everything before creating any output.
    output.mkdir(parents=False, exist_ok=False)
    manifest = {"trial": "SA2-stock-telecom-audio-port", "baseline": INPUTS,
                "output": {name: sha(text.encode()) for name, text in results.items()}}
    for name, text in results.items():
        (output / name).write_text(text, encoding="utf-8", newline="\n")
    diff = []
    for name in INPUTS:
        before = (source / PREFIX / name).read_text(encoding="utf-8").splitlines(True)
        diff.extend(difflib.unified_diff(before, results[name].splitlines(True),
                    fromfile=f"a/{PREFIX / name}", tofile=f"b/{PREFIX / name}"))
    (output / "review.patch").write_text("".join(diff), encoding="utf-8", newline="\n")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def apply(source, backup):
    results = render(source)
    for name in HELPERS:
        if target(source, name).exists():
            raise ValueError(f"helper already exists: {name}; refusing overwrite")
    backup.mkdir(parents=False, exist_ok=False)
    for name in INPUTS:
        shutil.copy2(target(source, name), backup / name)
    # This is a deterministic mechanical patch application, not a ROM build.
    for name, text in results.items():
        target(source, name).write_text(text, encoding="utf-8", newline="\n")
    manifest = {"trial": "SA2-stock-telecom-audio-port", "baseline": INPUTS,
                "applied": {name: sha(text.encode()) for name, text in results.items()}}
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify(source, backup):
    manifest = json.loads((backup / "manifest.json").read_text())
    if manifest.get("trial") != "SA2-stock-telecom-audio-port" or manifest.get("baseline") != INPUTS:
        raise ValueError("backup identity/baseline drift")
    expected = manifest["applied"]
    if set(expected) != set(INPUTS) | set(HELPERS): raise ValueError("manifest inventory drift")
    for name, digest in expected.items():
        if sha(target(source, name).read_bytes()) != digest:
            raise ValueError(f"applied source drift: {name}")
    for name, digest in INPUTS.items():
        path = backup / name
        if path.is_symlink() or sha(path.read_bytes()) != digest:
            raise ValueError(f"backup source drift: {name}")
    return {"trial": "SA2-stock-telecom-audio-port", "source_gate": "PASS"}


def restore(source, backup):
    verify(source, backup)  # Never overwrite subsequent edits or delete unknown helper contents.
    for name in INPUTS:
        shutil.copy2(backup / name, target(source, name))
    for name in HELPERS:
        target(source, name).unlink()
    return {"restored": list(INPUTS), "removed_project_helpers": list(HELPERS),
            "recoverable_helpers": "platform/telecom/sa2 in the project repository"}


def refresh_helpers(source, backup, history):
    # Refresh observer hooks as well as helpers from the verified original
    # baseline; upgrades keep the original restore transaction intact.
    verify(source, backup)  # Reject edits outside the last applied transaction.
    if history.resolve() == source.resolve() or history.resolve().is_relative_to(source.resolve()):
        raise ValueError("revision backup must be outside source checkout")
    manifest = json.loads((backup / "manifest.json").read_text())
    baseline = {name: (backup / name).read_bytes() for name in INPUTS}
    updates = {name: text.encode("utf-8") for name, text in render(source, baseline).items()}
    previous = {name: target(source, name).read_bytes() for name in updates}
    history.mkdir(parents=False, exist_ok=False)
    shutil.copy2(backup / "manifest.json", history / "manifest.json")
    for name, data in previous.items():
        (history / name).write_bytes(data)
    completed = []
    try:
        for name, data in updates.items():
            if target(source, name).read_bytes() != previous[name]:
                raise ValueError("concurrent helper edit refused: " + name)
            target(source, name).write_bytes(data)
            completed.append(name)
            manifest["applied"][name] = sha(data)
        manifest["carrier_scope"] = "all-operators-single-sim-either-slot"
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return {**verify(source, backup), "carrier_scope": manifest["carrier_scope"]}
    except Exception:
        for name in reversed(completed):
            if target(source, name).read_bytes() == updates[name]:
                target(source, name).write_bytes(previous[name])
        (backup / "manifest.json").write_bytes((history / "manifest.json").read_bytes())
        raise


def verify_product(product):
    paths = [product / p for p in ("system/priv-app/Telecom/Telecom.apk",
             "system_ext/priv-app/Telecom/Telecom.apk")]
    present = [p for p in paths if p.is_file()]
    if len(present) != 1:
        raise ValueError("expected exactly one product Telecom APK")
    with zipfile.ZipFile(present[0]) as apk:
        dex = b"".join(apk.read(name) for name in apk.namelist()
                       if name.startswith("classes") and name.endswith(".dex"))
    markers = [b"M11StockAudioPort", b"SA2 sequence returned ",
               b"g_call_sim_slot=0x01", b"g_call_sim_slot=0x02", b"SA2 unfocused g_call_state=",
               b"SA2 single-SIM either-slot scope phone=", b"SA2 integrated stock audio"]
    if not all(marker in dex for marker in markers):
        raise ValueError("integrated SA2 code markers absent from product Telecom APK")
    if b"persist.sys.m11_ims_audio_port" in dex:
        raise ValueError("obsolete SA2 opt-in property remains in product Telecom APK")
    return {"port": "SA2-stock-telecom-audio-port", "product_code_gate": "PASS",
            "runtime_switch": "none", "telecom_apk_sha256": sha(present[0].read_bytes()),
            "runtime_audio_validated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "apply", "refresh-helpers", "verify-source", "restore", "verify-product"))
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--product-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.mode == "verify-product":
        if not args.product_root or not args.product_root.is_dir(): parser.error("verify-product requires --product-root")
        try:
            print(json.dumps(verify_product(args.product_root), indent=2))
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            parser.exit(1, f"error: {e}\n")
        return
    if not args.source_root or args.source_root.is_symlink() or not args.source_root.is_dir():
        parser.error("source root must be an existing non-symlink directory")
    try:
        if args.mode == "prepare":
            if not args.output: parser.error("prepare requires --output")
            result = prepare(args.source_root, args.output)
        elif args.mode == "apply":
            if not args.backup: parser.error("apply requires --backup")
            result = apply(args.source_root, args.backup)
        elif args.mode == "refresh-helpers":
            if not args.backup or not args.output: parser.error("refresh-helpers requires --backup and --output revision backup")
            result = refresh_helpers(args.source_root, args.backup, args.output)
        else:
            if not args.backup: parser.error("verify-source requires --backup manifest")
            result = restore(args.source_root, args.backup) if args.mode == "restore" else verify(args.source_root, args.backup)
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError) as e:
        parser.exit(1, f"error: {e}\n")


if __name__ == "__main__":
    main()
