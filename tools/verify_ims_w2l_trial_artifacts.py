#!/usr/bin/env python3
"""Read-only gate for the combined EC2-r2 ePDG + BV1 IMS packaged trial."""

import argparse
import hashlib
import json
from pathlib import Path

import build_imsservice_w2l_trial as BV1
import verify_epdgservice_w2l_artifact as EC2


def verify(epdg, ims, pins_path, *, epdg_prefix_pins=None):
    if epdg_prefix_pins is None:
        epdg_result = EC2.verify(epdg, EC2.ROOT / "devices/m11q/epdgservice-w2l-trial-build.json")
    else:
        import legacy_epdg_prefix_compat as LG2
        epdg_result = LG2.verify_apk(epdg, epdg_prefix_pins)
    pins = BV1.load_pins(pins_path)
    entries = BV1.BASE._zip_entries(BV1.BASE._regular(ims, "packaged IMS APK"))
    dex_inventory = {k for k in entries if k.startswith("classes") and k.endswith(".dex")}
    if dex_inventory != {"classes.dex", "classes2.dex"}:
        raise ValueError("unexpected IMS DEX inventory")
    primary = hashlib.sha256(entries["classes.dex"]).hexdigest()
    bridge = hashlib.sha256(entries["classes2.dex"]).hexdigest()
    if primary != pins["classes_dex_sha256"] or bridge != BV1.BRIDGE_DEX:
        raise ValueError(f"IMS BV1/bridge revision mismatch: primary={primary}, expected={pins['classes_dex_sha256']}; do not flash")
    return {"status": "PASS", "ec2_r2_verified": epdg_prefix_pins is None,
            "legacy_epdg_prefix_verified": epdg_prefix_pins is not None,
            "bv1_verified": True, "ims_classes_dex_sha256": primary,
            "ims_classes2_dex_sha256": bridge, "epdg_classes_dex_sha256": epdg_result["classes_dex_sha256"],
            "signature_verified": False, "runtime_validated": False, "rom_build_run": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epdg-apk", type=Path, required=True)
    parser.add_argument("--ims-apk", type=Path, required=True)
    parser.add_argument("--pins", type=Path, default=BV1.DEFAULT_PINS)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.epdg_apk, args.ims_apk, args.pins), sort_keys=True))
    except (OSError, ValueError, BV1.BuildError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
