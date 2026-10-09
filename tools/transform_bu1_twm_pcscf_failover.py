#!/usr/bin/env python3
"""Shorten TWM's normal IMS Timer F for bounded P-CSCF failover testing."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path, PurePosixPath


class TransformError(ValueError):
    pass


TRANSFORMATION_ID = "BU1-twm-pcscf-failover-trial"
TARGET_PATH = "res/raw/imsprofile.json"
EXPECTED_INPUT_SHA256 = "eac62efba558d45826fd2951bf5087c65d005cbd2587a0d817891e525e11f937"
PROFILE_IDENTITY = {
    "name": "TWM Mobile VoLTE",
    "mnoname": "TWM_TW",
    "representative_plmn": "46697",
    "pdn": "ims",
    "reg_enabled": True,
}
STOCK_TIMER = (
    "1:2000,2:16000,4:17000,A:2000,B:128000,C:180000,D:32000,"
    "E:2000,F:128000,G:2000,H:128000,I:17000,J:128000,K:17000"
)
TRIAL_TIMER = STOCK_TIMER.replace("F:128000", "F:16000")
ANCHOR = '      "reg_enabled": true,\n      "priority": 0,\n'
REPLACEMENT = (
    '      "reg_enabled": true,\n'
    f'      "timer": "{TRIAL_TIMER}",\n'
    '      "priority": 0,\n'
)


def load_contract(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransformError(f"cannot read contract: {exc}") from exc
    keys = {"schema_version", "transformation_id", "target"}
    if not isinstance(raw, dict) or set(raw) != keys:
        raise TransformError("malformed contract")
    if raw["schema_version"] != 1 or raw["transformation_id"] != TRANSFORMATION_ID:
        raise TransformError("unsupported contract identity")
    item = raw["target"]
    expected_keys = {
        "path", "input_sha256", "profile_identity", "required_network_service",
        "timer_f_before_ms", "timer_f_after_ms", "reg_retry_base_time_policy",
    }
    if not isinstance(item, dict) or set(item) != expected_keys:
        raise TransformError("malformed target contract")
    rel = PurePosixPath(item["path"])
    if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != TARGET_PATH:
        raise TransformError("unexpected or unsafe target path")
    expected = (
        item["input_sha256"], item["profile_identity"],
        item["required_network_service"], item["timer_f_before_ms"],
        item["timer_f_after_ms"], item["reg_retry_base_time_policy"],
    )
    wanted = (
        EXPECTED_INPUT_SHA256, PROFILE_IDENTITY, "mmtel", 128000, 16000,
        "preserve-inherited-30-seconds",
    )
    if expected != wanted:
        raise TransformError("target identity or policy contract drift")
    return raw


def _profiles(text: str) -> list[dict]:
    try:
        root = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TransformError(f"invalid IMS profile JSON: {exc}") from exc
    profiles = root.get("profile") if isinstance(root, dict) else None
    if not isinstance(profiles, list):
        raise TransformError("IMS profile inventory is missing")
    return profiles


def _target(profiles: list[dict]) -> dict:
    matches = [profile for profile in profiles if all(
        profile.get(key) == value for key, value in PROFILE_IDENTITY.items())]
    if len(matches) != 1:
        raise TransformError("TWM normal IMS profile identity drift")
    profile = matches[0]
    if profile.get("emergency_support") is True or profile.get("cmc_type", 0) != 0:
        raise TransformError("target unexpectedly includes emergency or CMC behavior")
    networks = profile.get("network")
    if not isinstance(networks, list) or not any(
            "wifi" in item.get("type", "").split(",")
            and "mmtel" in item.get("services", []) for item in networks):
        raise TransformError("target lacks Wi-Fi MMTEL service")
    return profile


def _updated(text: str) -> str:
    before_profiles = _profiles(text)
    before = _target(before_profiles)
    if "timer" in before or "reg_retry_base_time" in before:
        raise TransformError("BU1 is already or partially applied")

    start = text.find('      "name": "TWM Mobile VoLTE",')
    end = text.find('\n    },\n    {', start)
    if start < 0 or end < 0:
        raise TransformError("cannot isolate TWM normal IMS profile")
    section = text[start:end]
    if section.count(ANCHOR) != 1:
        raise TransformError("TWM insertion anchor drift")
    updated = text[:start] + section.replace(ANCHOR, REPLACEMENT) + text[end:]

    after_profiles = _profiles(updated)
    after = _target(after_profiles)
    if after.get("timer") != TRIAL_TIMER:
        raise TransformError("Timer F trial value was not applied")
    if "reg_retry_base_time" in after:
        raise TransformError("registration retry base time changed in Timer F trial")

    before_by_name = {item.get("name"): item for item in before_profiles}
    after_by_name = {item.get("name"): item for item in after_profiles}
    if before_by_name.keys() != after_by_name.keys():
        raise TransformError("profile inventory changed")
    expected_after = dict(before)
    expected_after["timer"] = TRIAL_TIMER
    for name in before_by_name:
        wanted = expected_after if name == PROFILE_IDENTITY["name"] else before_by_name[name]
        if after_by_name[name] != wanted:
            raise TransformError(f"unrelated IMS profile changed: {name}")
    return updated


def validate_result(source: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise TransformError("final target must be a regular non-symlink file")
    profiles = _profiles(source.read_text(encoding="utf-8"))
    profile = _target(profiles)
    if profile.get("timer") != TRIAL_TIMER:
        raise TransformError("final TWM normal IMS Timer F is not 16000 ms")
    if "reg_retry_base_time" in profile:
        raise TransformError("final Timer F trial changes registration retry base time")


def transform(contract_path: Path, source: Path, output: Path,
              allow_identical: bool = False) -> dict:
    contract = load_contract(contract_path)
    if source.is_symlink() or not source.is_file():
        raise TransformError("target must be a regular non-symlink file")
    if output.is_symlink() or not output.parent.is_dir():
        raise TransformError("unsafe output path")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != contract["target"]["input_sha256"]:
        raise TransformError("input hash drift")
    updated = _updated(data.decode("utf-8")).encode("utf-8")
    payload = {
        "schema_version": 1,
        "transformation_id": TRANSFORMATION_ID,
        "changed": True,
        "files": [{
            "target": TARGET_PATH,
            "hooks": ["twm_normal_ims_timer_f_16000ms"],
            "input_sha256": hashlib.sha256(data).hexdigest(),
            "output_sha256": hashlib.sha256(updated).hexdigest(),
        }],
    }
    if output.exists():
        if allow_identical and output.is_file() and output.read_bytes() == updated:
            payload["changed"] = False
            return payload
        raise TransformError("refusing to overwrite output")
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output.resolve(strict=False))
    finally:
        if fd >= 0:
            os.close(fd)
        temporary.unlink(missing_ok=True)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-identical", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = transform(args.contract, args.input, args.output, args.allow_identical)
    except (OSError, UnicodeError, TransformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
