#!/usr/bin/env python3
"""Remove the BU1 profile override, restoring exact CWK3 stock resources. No ROM build."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

import apk_entry_replace as ZIPPER
import transform_bu1_twm_pcscf_failover as BU1

RESOURCE = BU1.TARGET_PATH
STOCK_SHA = BU1.EXPECTED_INPUT_SHA256
TRIAL_SHA = "856f0a2659769a1868365f3ead337ff099221fca8832d5f32266abce440b2a07"
PREVIOUS_LG3_APK = "4aeb261ac3f43ac85a5f8825c2bfe3b7741b442f251d9bee8be1631e0538fb97"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def restored_profile(data):
    if sha(data) == STOCK_SHA:
        return data
    if sha(data) != TRIAL_SHA:
        raise ValueError("IMS profile input drift; stock timer restoration refused")
    text = data.decode("utf-8")
    # Invert only the exact BU1 insertion; the stock hash proves every other
    # profile byte, including emergency/CMC/retry policies, is unchanged.
    if text.count(BU1.REPLACEMENT) != 1:
        raise ValueError("BU1 timer insertion drift")
    result = text.replace(BU1.REPLACEMENT, BU1.ANCHOR, 1).encode("utf-8")
    verify_profile(result)
    return result


def verify_profile(data):
    if sha(data) != STOCK_SHA:
        raise ValueError("stock IMS profile hash mismatch; Timer F experiment remains or profile drifted")
    profiles = BU1._profiles(data.decode("utf-8"))
    profile = BU1._target(profiles)
    if "timer" in profile or "reg_retry_base_time" in profile:
        raise ValueError("TWM profile must inherit stock timers and retry settings")
    # CWK3's default profile supplies F:128000 to this profile.
    default = [row for row in profiles if row.get("name") == "default"]
    if len(default) != 1 or "F:128000" not in default[0].get("timer", "").split(","):
        raise ValueError("stock inherited Timer F is not 128000 ms")


def restore_apk(apk, output):
    if apk.is_symlink() or sha(apk.read_bytes()) != PREVIOUS_LG3_APK:
        raise ValueError("expected exact prior unsigned LG3 artifact")
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("fresh output in an existing directory required")
    with zipfile.ZipFile(apk) as archive:
        if archive.namelist().count(RESOURCE) != 1:
            raise ValueError("IMS profile ZIP inventory drift")
        original = archive.read(RESOURCE)
    restored = restored_profile(original)
    with tempfile.TemporaryDirectory(prefix="stock-timer-", dir=output.parent) as directory:
        resource = Path(directory) / "imsprofile.json"
        resource.write_bytes(restored)
        report = ZIPPER.build_archive(apk, output, {RESOURCE: resource}, {})
    if report["removed_signatures"] or {r["entry"] for r in report["changed_entries"]} != {RESOURCE}:
        raise ValueError("unexpected archive changes")
    return dict(status="PASS", timer_f_ms=128000, rom_build_run=False,
                dex_changed=False, archive=report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(restore_apk(args.apk, args.output), indent=2))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
