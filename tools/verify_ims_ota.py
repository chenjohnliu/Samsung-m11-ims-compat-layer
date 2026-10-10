#!/usr/bin/env python3
"""Verify full M11 BLOCK OTA payloads offline; never build or flash a ROM.

Only a new caller-owned output directory receives reconstructed diagnostic images.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

BLOCK = 4096
MAX_IMAGE_BLOCKS = 8 * 1024 * 1024 * 1024 // BLOCK
REQUIRED = {
    "imsservice.apk": ("system/system_ext/priv-app/imsservice/imsservice.apk", ("/system_ext/priv-app/imsservice/imsservice.apk", "/system/system_ext/priv-app/imsservice/imsservice.apk")),
    "EpdgService.apk": ("system/system_ext/priv-app/EpdgService/EpdgService.apk", ("/system_ext/priv-app/EpdgService/EpdgService.apk", "/system/system_ext/priv-app/EpdgService/EpdgService.apk")),
    "Telecom.apk": ("system/priv-app/Telecom/Telecom.apk", ("/priv-app/Telecom/Telecom.apk", "/system/priv-app/Telecom/Telecom.apk")),
    "telephony-common.jar": ("system/framework/telephony-common.jar", ("/framework/telephony-common.jar", "/system/framework/telephony-common.jar")),
    "framework.jar": ("system/framework/framework.jar", ("/framework/framework.jar", "/system/framework/framework.jar")),
}
OPTIONAL = {
    "system/build.prop": ("system/build.prop", ("/build.prop", "/system/build.prop")),
    "system_ext/etc/build.prop": ("system/system_ext/etc/build.prop", ("/system_ext/etc/build.prop", "/system/system_ext/etc/build.prop")),
    "vendor/build.prop": ("vendor/build.prop", ("/build.prop", "/vendor/build.prop")),
    "vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk": (
        "vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk",
        ("/overlay/CarrierConfig__auto_generated_rro_vendor.apk", "/vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk")),
}


def parse_ranges(spec):
    vals = [int(x) for x in spec.split(",")]
    if not vals or vals[0] != len(vals) - 1 or (len(vals) - 1) % 2:
        raise ValueError("malformed transfer-list range count")
    out = []
    for start, end in zip(vals[1::2], vals[2::2]):
        if start < 0 or end <= start:
            raise ValueError("invalid transfer-list range")
        out.append((start, end))
    return out


def validate_output_location(output_dir):
    parent = output_dir.parent
    if output_dir.exists() or output_dir.is_symlink() or not parent.is_dir() or parent.is_symlink():
        raise ValueError("output-dir must be absent and its existing parent must be a real directory")


def parse_transfer(data):
    lines = data.decode("ascii").splitlines()
    if len(lines) < 4 or lines[0] != "4":
        raise ValueError("only transfer-list version 4 is supported")
    total = int(lines[1])
    # The second header is the number of blocks written, NOT partition size.
    # Sparse erase ranges can extend well beyond it in a valid full OTA.
    if total <= 0 or total > MAX_IMAGE_BLOCKS or int(lines[2]) != 0 or int(lines[3]) != 0:
        raise ValueError("invalid transfer-list header or stash metadata")
    ops, max_block, new_blocks = [], 0, 0
    for line in lines[4:]:
        if not line:
            continue
        fields = line.split(" ")
        if len(fields) != 2 or fields[0] not in ("new", "zero", "erase"):
            raise ValueError("unsupported transfer-list command")
        ranges = parse_ranges(fields[1])
        for start, end in ranges:
            if end > MAX_IMAGE_BLOCKS:
                raise ValueError("transfer-list range exceeds the 8 GiB diagnostic limit")
            max_block = max(max_block, end)
            if fields[0] == "new":
                new_blocks += end - start
        ops.append((fields[0], ranges))
    if not ops:
        raise ValueError("transfer list has no operations")
    # Skipping zero/erase is correct for a fresh sparse image only when ranges
    # do not overlap previously written data. Refuse ambiguous incremental input.
    ordered = sorted((start, end) for _, ranges in ops for start, end in ranges)
    if any(right[0] < left[1] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("overlapping transfer ranges are not supported")
    return ops, max_block, new_blocks


def reconstruct(zipf, partition, out, brotli):
    base = partition + ".transfer.list"
    datname = partition + ".new.dat.br"
    names = zipf.namelist()
    if names.count(base) != 1 or names.count(datname) != 1:
        raise ValueError(f"missing or duplicate {base} or {datname}")
    ops, max_block, new_blocks = parse_transfer(zipf.read(base))
    datbr, dat, image = out / (partition + ".new.dat.br"), out / (partition + ".new.dat"), out / (partition + ".img")
    with zipf.open(datname) as src, datbr.open("xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
    if dat.exists() or dat.is_symlink():
        raise ValueError("refusing existing decompression output")
    subprocess.run([brotli, "-d", "-o", str(dat), str(datbr)], check=True)
    expected = new_blocks * BLOCK
    if dat.stat().st_size != expected:
        raise ValueError(f"{partition} data size {dat.stat().st_size} != expected {expected}")
    with dat.open("rb") as stream, image.open("xb") as raw:
        raw.truncate(max_block * BLOCK)
        for kind, ranges in ops:
            if kind != "new":
                continue
            for start, end in ranges:
                raw.seek(start * BLOCK)
                remaining = (end - start) * BLOCK
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("truncated decompressed new.dat")
                    raw.write(chunk)
                    remaining -= len(chunk)
        if stream.read(1):
            raise ValueError("unconsumed decompressed new.dat bytes")
    return image


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def debugfs_dump(debugfs, image, candidates, dest):
    for internal in candidates:
        p = subprocess.run([debugfs, "-R", f"dump {internal} {json.dumps(str(dest))}", str(image)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if p.returncode == 0 and dest.is_file():
            return internal
        dest.unlink(missing_ok=True)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ota", type=Path, required=True)
    ap.add_argument("--product-root", type=Path, required=True)
    ap.add_argument("--brotli", required=True)
    ap.add_argument("--debugfs", required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    a = ap.parse_args()
    try:
        validate_output_location(a.output_dir)
    except ValueError as exc:
        ap.error(str(exc))
    if not a.ota.is_file() or not a.product_root.is_dir():
        ap.error("OTA or product-root is unavailable")
    a.output_dir.mkdir()
    report = {"result": "FAIL", "rom_build_run": False, "runtime_validated": False,
              "zip_signature_validation": False, "compared": [], "errors": [], "vendor_payload": "absent"}
    try:
        report["ota_sha256"] = sha256(a.ota)
        with zipfile.ZipFile(a.ota) as z:
            system_image = reconstruct(z, "system", a.output_dir, a.brotli)
            vendor_name = "vendor.new.dat.br" in z.namelist() and "vendor.transfer.list" in z.namelist()
            vendor_image = reconstruct(z, "vendor", a.output_dir, a.brotli) if vendor_name else None
            report["vendor_payload"] = "present" if vendor_image else "absent"
        pending = []
        for name, (product_rel, candidates) in REQUIRED.items():
            product = a.product_root / product_rel
            if not product.is_file():
                raise ValueError(f"product file missing: {product_rel}")
            dest = a.output_dir / ("dump-" + name)
            internal = debugfs_dump(a.debugfs, system_image, candidates, dest)
            if internal is None:
                raise ValueError(f"could not extract OTA file: {name}")
            actual, expected = sha256(dest), sha256(product)
            item = {"file": product_rel, "ota_path": internal, "ota_sha256": actual, "product_sha256": expected, "match": actual == expected}
            report["compared"].append(item)
            if actual != expected:
                pending.append(product_rel)
        for name, (product_rel, candidates) in OPTIONAL.items():
            is_vendor = product_rel.startswith("vendor/")
            image = vendor_image if is_vendor else system_image
            product = a.product_root / product_rel
            if not product.is_file():
                continue
            if image is None:
                report["errors"].append(f"payload missing for existing product file: {product_rel}")
                continue
            dest = a.output_dir / ("dump-optional-" + name.replace("/", "_"))
            internal = debugfs_dump(a.debugfs, image, candidates, dest)
            if internal is None:
                report["errors"].append(f"could not extract existing optional file: {product_rel}")
                continue
            actual, expected = sha256(dest), sha256(product)
            report["compared"].append({"file": product_rel, "ota_path": internal, "ota_sha256": actual,
                                        "product_sha256": expected, "match": actual == expected, "optional": True})
            if actual != expected:
                pending.append(product_rel)
        if pending:
            report["errors"].append("hash mismatches: " + ", ".join(pending))
        if report["errors"]:
            report["result"] = "FAIL"
        elif vendor_image is None:
            report["result"] = "INCOMPLETE: vendor payload absent; not a full release PASS"
        else:
            report["result"] = "PASS"
    except Exception as exc:
        report["errors"].append(str(exc))
    report["output_dir"] = str(a.output_dir)
    report["note"] = "Offline payload hashes only; no ZIP signature or device runtime validation."
    encoded = json.dumps(report, indent=2, sort_keys=True)
    with (a.output_dir / "verification.json").open("x", encoding="utf-8") as saved:
        saved.write(encoded + "\n")
    print(encoded)
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
