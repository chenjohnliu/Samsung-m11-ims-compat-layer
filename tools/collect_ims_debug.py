#!/usr/bin/env python3
"""Collect a private, read-only ADB snapshot useful for IMS debugging."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


PROPERTIES = (
    "ro.build.display.id",
    "ro.build.version.incremental",
    "ro.build.date.utc",
    "ro.build.version.sdk",
    "ro.build.version.release",
    "ro.build.fingerprint",
    "ro.vendor.build.fingerprint",
    "ro.product.model",
    "ro.product.device",
    "gsm.version.baseband",
    "gsm.sim.state",
    "gsm.sim.operator.numeric",
    "gsm.operator.numeric",
    "ril.epdg.currenMno",
    "sys.smf.mnoname0",
    "sys.smf.mnoname1",
    "persist.radio.multisim.config",
)
PACKAGES = ("com.sec.imsservice", "com.sec.epdg", "com.sec.unifiedwfc")
NORMAL_TIMEOUT = 30
LOGCAT_TIMEOUT = 60
BUGREPORT_TIMEOUT = 300


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.-") or "command"


def parse_devices(output: str) -> list[tuple[str, str]]:
    devices = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[1:3] == ["no", "permissions"]:
            devices.append((fields[0], "no permissions"))
        elif len(fields) >= 2 and fields[1] in {"device", "unauthorized", "offline"}:
            devices.append((fields[0], fields[1]))
    return devices


class Collector:
    def __init__(self, adb: str, output: Path, serial: str | None, bugreport: bool):
        self.adb = adb
        self.output = output
        self.serial = serial
        self.want_bugreport = bugreport
        self.records: list[dict[str, Any]] = []
        self.counter = 0

    def run(self, label: str, args: Sequence[str], timeout: int = NORMAL_TIMEOUT) -> dict[str, Any]:
        self.counter += 1
        argv = [self.adb, *args]
        stem = f"{self.counter:03d}_{safe_name(label)}"
        stdout_name, stderr_name = f"{stem}.stdout.txt", f"{stem}.stderr.txt"
        started = utc_now()
        start_tick = time.monotonic()
        code: int | None = None
        error: str | None = None
        out: bytes = b""
        err: bytes = b""
        timed_out = False
        try:
            result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=timeout, check=False, shell=False)
            code, out, err = result.returncode, result.stdout or b"", result.stderr or b""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            error = f"command timed out after {timeout} seconds"
            out = exc.stdout or b""
            err = exc.stderr or b""
        except OSError as exc:
            error = f"could not start command: {exc}"
        elapsed = round(time.monotonic() - start_tick, 3)
        (self.output / stdout_name).write_bytes(out if isinstance(out, bytes) else out.encode())
        (self.output / stderr_name).write_bytes(err if isinstance(err, bytes) else err.encode())
        record = {
            "label": label,
            "argv": argv,
            "returncode": code,
            "started_utc": started,
            "elapsed_seconds": elapsed,
            "timeout_seconds": timeout,
            "timed_out": timed_out,
            "error": error,
            "stdout_file": stdout_name,
            "stderr_file": stderr_name,
        }
        self.records.append(record)
        status = "timeout" if timed_out else ("error" if error else f"exit {code}")
        print(f"{label}: {status}")
        return record

    def adb_args(self, *args: str) -> list[str]:
        return (["-s", self.serial] if self.serial else []) + list(args)

    def execute(self) -> int:
        (self.output / "README_PRIVATE.txt").write_text(PRIVATE_README, encoding="utf-8")
        try:
            version = self.run("adb_version", ["version"])
            devices = self.run("adb_devices", ["devices", "-l"])
            device_list = parse_devices(read_capture(self.output, devices["stdout_file"]))
            if self.serial:
                states = [state for serial, state in device_list if serial == self.serial]
                if not states or states[0] != "device":
                    raise CollectionError(f"specified serial is not in device state (state: {states[0] if states else 'not listed'})")
            else:
                ready = [serial for serial, state in device_list if state == "device"]
                if len(ready) != 1:
                    raise CollectionError(f"expected exactly one usable device, found {len(ready)}; pass --serial explicitly")
                self.serial = ready[0]
            print("Selected ADB device (identifier saved in private manifest).")

            def device(label: str, *args: str, timeout: int = NORMAL_TIMEOUT) -> dict[str, Any]:
                return self.run(label, self.adb_args(*args), timeout)

            device("device_date", "shell", "date")
            device("device_uptime", "shell", "uptime")
            for prop in PROPERTIES:
                device(f"property_{prop}", "shell", "getprop", prop)
            device("logcat_all_threadtime", "logcat", "-b", "all", "-d", "-v", "threadtime", timeout=LOGCAT_TIMEOUT)
            device("dumpsys_telephony_registry", "shell", "dumpsys", "telephony.registry")
            device("dumpsys_telecom", "shell", "dumpsys", "telecom")
            device("dumpsys_carrier_config", "shell", "dumpsys", "carrier_config")
            device("dumpsys_services", "shell", "dumpsys", "-l")
            for package in PACKAGES:
                device(f"pm_path_{package}", "shell", "pm", "path", package)
                device(f"dumpsys_package_{package}", "shell", "dumpsys", "package", package)
            if self.want_bugreport:
                bugreport_path = self.output / "bugreport.zip"
                device("bugreport_opt_in_slow", "bugreport", str(bugreport_path), timeout=BUGREPORT_TIMEOUT)
        except CollectionError as exc:
            print(f"Collection stopped: {exc}")
            self.write_manifest(exc)
            return 2
        except KeyboardInterrupt:
            interrupted = "collection interrupted by user (KeyboardInterrupt)"
            print("Collection interrupted; saving completed command records.")
            self.write_manifest(interrupted)
            return 130
        self.write_manifest()
        failures = sum(1 for item in self.records if item["error"] or item["returncode"] not in (0, None))
        print(f"Collection finished with {failures} command failure(s). Files are in {self.output}")
        return 1 if failures else 0

    def write_manifest(self, fatal_error: str | None = None) -> None:
        data = {
            "schema_version": 1,
            "host_started_utc": self.records[0]["started_utc"] if self.records else utc_now(),
            "host_completed_utc": utc_now(),
            "device_serial": self.serial,
            "privacy": "Contains raw device diagnostics and may include identifiers and sensitive personal data.",
            "fatal_error": str(fatal_error) if fatal_error else None,
            "commands": self.records,
        }
        (self.output / "manifest.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        restrict_private_files(self.output)


class CollectionError(Exception):
    pass


PRIVATE_README = """PRIVATE DEVICE DIAGNOSTICS — HANDLE WITH CARE

This directory contains raw Android logs and telephony dumps. They may contain
IMSI/IMEI, phone numbers, location, call history, account details, or other
personal data. Keep the directory private, review and redact before sharing,
and delete it when it is no longer needed. The collector does not upload data
or redact captures. Build and publish nothing with this collector.

The collector only invokes bounded ADB read commands, plus an optional slow
`adb bugreport` when explicitly requested. Individual command failures are
recorded in manifest.json and do not stop later captures. The package names
checked are common Samsung IMS/ePDG/WFC names and may differ on a device.
Build fingerprints are device-reported values and may be spoofed. These
captures are evidence for human analysis, not an automated root-cause verdict.
"""


def read_capture(output: Path, filename: str) -> str:
    return (output / filename).read_text(encoding="utf-8", errors="replace")


def restrict_private_files(directory: Path) -> None:
    if os.name == "posix":
        try:
            directory.chmod(0o700)
            for child in directory.iterdir():
                if child.is_file():
                    child.chmod(0o600)
        except OSError:
            pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect private, read-only ADB evidence for human IMS debugging.")
    parser.add_argument("--serial", help="ADB device serial; omit only when exactly one usable device is connected")
    parser.add_argument("--output", required=True, type=Path, help="new private output directory (must not already exist)")
    parser.add_argument("--bugreport", action="store_true", help="also capture a potentially slow ADB bugreport (up to 300 seconds)")
    parser.add_argument("--adb", default="adb", help="ADB executable path or command name (default: adb)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.output.exists():
        print(f"Refusing existing output path: {args.output}", file=sys.stderr)
        return 2
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        print(f"Could not create output directory: {exc}", file=sys.stderr)
        return 2
    restrict_private_files(args.output)
    collector = Collector(args.adb, args.output, args.serial, args.bugreport)
    return collector.execute()


if __name__ == "__main__":
    raise SystemExit(main())
