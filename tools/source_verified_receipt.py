"""Receipt helpers for explicit source-verified IMS producer chains."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DEX_NAMES = {"classes.dex", "classes2.dex"}


class ReceiptError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash(value, label: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ReceiptError(f"invalid source-verified receipt {label} SHA-256")
    return value


def _regular(path: Path, label: str) -> Path:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ReceiptError(f"missing {label}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ReceiptError(f"{label} must be a regular non-symlink file")
    return path.resolve(strict=True)


def _dex_inventory(apk: Path) -> dict[str, str]:
    try:
        with zipfile.ZipFile(apk) as archive:
            names = [item.filename for item in archive.infolist()]
            dex_names = {name for name in names
                         if name.startswith("classes") and name.endswith(".dex")}
            if len(names) != len(set(names)):
                raise ReceiptError("source-verified input APK has duplicate ZIP entries")
            if dex_names not in ({"classes.dex"}, DEX_NAMES):
                raise ReceiptError("source-verified input APK DEX inventory drift")
            return {name: hashlib.sha256(archive.read(name)).hexdigest()
                    for name in sorted(dex_names)}
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ReceiptError(f"cannot inspect source-verified input APK: {exc}") from exc


def make_source_verified_receipt(stage: str, apk_path: Path, dex_sha256: dict[str, str],
                                 source_classification: dict,
                                 upstream: dict | None = None) -> dict:
    """Create a nested receipt after the caller has completed its stage gates."""
    if not isinstance(stage, str) or not stage or not isinstance(source_classification, dict):
        raise ReceiptError("source-verified stage and classification are required")
    if source_classification.get("source_classification_verified") is not True:
        raise ReceiptError("source classification was not verified")
    try:
        json.dumps(source_classification, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ReceiptError("source classification must be JSON-compatible") from exc
    if not dex_sha256 or set(dex_sha256) not in ({"classes.dex"}, DEX_NAMES):
        raise ReceiptError("source-verified DEX inventory must be classes.dex, optionally classes2.dex")
    clean_dex = {name: _hash(value, name) for name, value in dex_sha256.items()}
    if upstream is None:
        stage_chain = [stage]
        provenance = {"root_stage": stage, "upstream_report_sha256": None}
    else:
        if not isinstance(upstream, dict):
            raise ReceiptError("invalid upstream source-verified receipt")
        previous_stage = upstream.get("stage")
        previous_chain = upstream.get("stage_chain")
        if (not isinstance(previous_stage, str) or not isinstance(previous_chain, list)
                or not previous_chain or previous_chain[-1] != previous_stage):
            raise ReceiptError("upstream source-verified stage chain is invalid")
        report_hash = _hash(upstream.get("report_sha256"), "upstream report")
        previous_provenance = upstream.get("source_provenance")
        if not isinstance(previous_provenance, dict):
            raise ReceiptError("upstream source provenance is missing")
        stage_chain = [*previous_chain, stage]
        provenance = {"root_stage": previous_provenance.get("root_stage"),
                      "upstream_stage": previous_stage,
                      "upstream_report_sha256": report_hash}
    if not isinstance(provenance["root_stage"], str):
        raise ReceiptError("source-verified root stage is missing")
    apk = _regular(Path(apk_path), "source-verified output APK")
    if _dex_inventory(apk) != clean_dex:
        raise ReceiptError("source-verified output DEX hashes do not match APK")
    return {"schema_version": 1, "stage": stage, "stage_chain": stage_chain,
            "source_provenance": provenance,
            "source_classification": source_classification,
            "artifact": {"apk_sha256": sha256_file(apk), "dex_sha256": clean_dex}}


def verify_source_verified_input(report_path: Path, input_apk: Path,
                                expected_stage: str,
                                expected_stage_chain: list[str]) -> dict:
    """Validate the previous producer receipt against the exact supplied APK."""
    if (not isinstance(expected_stage, str) or not expected_stage
            or not isinstance(expected_stage_chain, list) or not expected_stage_chain
            or any(not isinstance(item, str) or not item for item in expected_stage_chain)
            or expected_stage_chain[-1] != expected_stage):
        raise ReceiptError("expected source-verified stage chain is invalid")
    report = _regular(Path(report_path), "source-verified input receipt")
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"invalid source-verified input receipt: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReceiptError("source-verified input receipt must be a JSON object")
    if payload.get("status") != "SOURCE_VERIFIED":
        raise ReceiptError("upstream report is not SOURCE_VERIFIED")
    if (payload.get("strict_pins_verified") is not False
            or payload.get("source_invariants_verified") is not True
            or payload.get("runtime_validated") is not False
            or payload.get("release_eligible") is not False):
        raise ReceiptError("upstream source-verified status flags are invalid")
    receipt = payload.get("source_verified_receipt")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        raise ReceiptError("upstream source-verified receipt schema is missing or unsupported")
    if receipt.get("stage") != expected_stage or receipt.get("stage_chain") != expected_stage_chain:
        raise ReceiptError("upstream source-verified stage chain mismatch")
    provenance = receipt.get("source_provenance")
    classification = receipt.get("source_classification")
    artifact = receipt.get("artifact")
    if (not isinstance(provenance, dict) or provenance.get("root_stage") != expected_stage_chain[0]
            or not isinstance(classification, dict)
            or classification.get("source_classification_verified") is not True
            or not isinstance(artifact, dict)):
        raise ReceiptError("upstream source provenance/classification is invalid")
    if len(expected_stage_chain) == 1:
        if provenance.get("upstream_report_sha256") is not None:
            raise ReceiptError("root source-verified receipt has unexpected upstream provenance")
    else:
        _hash(provenance.get("upstream_report_sha256"), "upstream report")
    expected_apk = _hash(artifact.get("apk_sha256"), "artifact APK")
    recorded_dex = artifact.get("dex_sha256")
    if not isinstance(recorded_dex, dict) or set(recorded_dex) not in ({"classes.dex"}, DEX_NAMES):
        raise ReceiptError("upstream source-verified DEX inventory is invalid")
    recorded_dex = {name: _hash(value, f"artifact {name}")
                    for name, value in recorded_dex.items()}
    apk = _regular(Path(input_apk), "source-verified input APK")
    if sha256_file(apk) != expected_apk:
        raise ReceiptError("source-verified input APK does not match upstream receipt")
    if _dex_inventory(apk) != recorded_dex:
        raise ReceiptError("source-verified input DEX does not match upstream receipt")
    return {"stage": expected_stage, "stage_chain": list(expected_stage_chain),
            "source_provenance": provenance,
            "source_classification": classification,
            "artifact": artifact, "report_sha256": sha256_file(report)}
