#!/usr/bin/env python3
"""Derive a fail-closed Samsung VoWiFi PLMN allowlist from stock payload data."""

import argparse
import json
import re
import xml.etree.ElementTree as ET
import zipfile


def read_apk_json(apk: zipfile.ZipFile, name: str):
    with apk.open(f"res/raw/{name}.json") as stream:
        raw = stream.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # CWK3 uses end-of-line // comments but is otherwise strict JSON. A
        # slash inside a quoted value is not followed by a second slash in the
        # audited resources, so keep this deliberately narrow and dependency
        # free instead of accepting arbitrary JavaScript syntax.
        without_comments = re.sub(r"\s+//.*$", "", raw, flags=re.MULTILINE)
        return json.loads(without_comments)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ims_apk")
    parser.add_argument("epdg_config")
    args = parser.parse_args()

    with zipfile.ZipFile(args.ims_apk) as apk:
        mno_map = read_apk_json(apk, "mnomap")["mnomap"]
        switches = read_apk_json(apk, "imsswitch")["imsswitch"]
        profiles = read_apk_json(apk, "imsprofile")["profile"]

    switch_mnos = {
        item["mnoname"]
        for item in switches
        if item.get("enableIms") is True
        and item.get("enableServiceVowifi") is True
    }
    profile_mnos = {
        profile["mnoname"]
        for profile in profiles
        if profile.get("reg_enabled") is True
        and any(
            "wifi" in network.get("type", "").split(",")
            and "mmtel" in network.get("services", [])
            and network.get("enabled") is True
            for network in profile.get("network", [])
        )
    }

    root = ET.parse(args.epdg_config).getroot()
    apn_mnos = {
        item.get("mnoname")
        for item in root.iter("apn")
        if item.get("connname") == "imsApn"
    }
    settings = {
        item.get("mnoname"): item
        for item in root.iter("settings")
        if item.get("epdgenable") == "on"
    }
    supported_mnos = switch_mnos & profile_mnos & apn_mnos & settings.keys()

    print("mccmnc\tmnoname\tfilters\tcertificate\tentitlement_hint")
    seen = set()
    for item in sorted(mno_map, key=lambda entry: (entry.get("mccmnc", ""), entry.get("mnoname", ""))):
        mno = item.get("mnoname", "").split("@", 1)[0]
        plmn = item.get("mccmnc", "")
        if mno not in supported_mnos or not plmn.isdigit() or len(plmn) not in (5, 6):
            continue
        filters = ",".join(
            key for key in ("subset", "gid1", "gid2", "spname") if item.get(key)
        ) or "none"
        key = (plmn, mno, filters)
        if key in seen:
            continue
        seen.add(key)
        setting = settings[mno]
        certificate = (
            setting.get("certi_path", "none")
            if setting.get("is_using_certi") == "1"
            else "none"
        )
        entitlement = "unknown"
        print(f"{plmn}\t{mno}\t{filters}\t{certificate}\t{entitlement}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
