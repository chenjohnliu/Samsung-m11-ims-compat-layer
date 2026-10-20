import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "collect_ims_debug.py"
TEST_ROOT = Path(__file__).resolve().parents[1] / "tests"
SPEC = importlib.util.spec_from_file_location("collect_ims_debug", SCRIPT)
collector_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector_module)


class FakeAdb:
    def __init__(self, devices="List of devices attached\nSERIAL1\tdevice product:test\n", fail_label=None, timeout_label=None):
        self.devices = devices
        self.calls = []
        self.fail_label = fail_label
        self.timeout_label = timeout_label

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        self.assert_safe(argv, kwargs)
        if argv[1:] == ["version"]:
            return subprocess.CompletedProcess(argv, 0, b"Android Debug Bridge version fake\n", b"")
        if argv[1:] == ["devices", "-l"]:
            return subprocess.CompletedProcess(argv, 0, self.devices.encode(), b"")
        command_text = " ".join(argv[1:])
        if self.timeout_label and self.timeout_label in command_text:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"partial", stderr=b"slow")
        rc, out, err = (17, b"failed output", b"expected failure") if self.fail_label and self.fail_label in command_text else (0, b"captured output", b"")
        if "bugreport" in argv:
            Path(argv[-1]).write_bytes(b"fake bugreport")
        return subprocess.CompletedProcess(argv, rc, out, err)

    @staticmethod
    def assert_safe(argv, kwargs):
        assert kwargs.get("shell") is False
        assert isinstance(argv, list) and all(isinstance(arg, str) for arg in argv)
        forbidden = {"reboot", "root", "remount", "clear", "stop", "start", "su"}
        assert not any(arg in forbidden for arg in argv)


class CollectImsDebugTests(unittest.TestCase):
    def run_collector(self, root, mock_run, *args):
        output = Path(root) / "new-capture"
        with patch.object(collector_module.subprocess, "run", side_effect=mock_run):
            code = collector_module.main(["--output", str(output), *args])
        return code, output

    def test_selects_single_ready_device_and_uses_argv_commands(self):
        fake = FakeAdb()
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as root:
            code, output = self.run_collector(root, fake)
            self.assertEqual(code, 0)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["device_serial"], "SERIAL1")
            commands = manifest["commands"]
            self.assertTrue(all(isinstance(item["argv"], list) for item in commands))
            device_commands = [item["argv"] for item in commands if "-s" in item["argv"]]
            self.assertTrue(device_commands)
            self.assertTrue(all(command[1:3] == ["-s", "SERIAL1"] for command in device_commands))
            self.assertTrue(any("logcat" in command for command in device_commands))
            self.assertFalse(any(any(arg in {"reboot", "root", "clear", "remount", "su"} for arg in command) for command, _ in fake.calls))
            self.assertFalse(any("bugreport" in command for command, _ in fake.calls))
            self.assertTrue((output / "README_PRIVATE.txt").exists())

    def test_serial_selection_rejects_none_multiple_and_nonready_explicit_device(self):
        cases = [
            ("List of devices attached\n", None),
            ("List of devices attached\nA\tdevice\nB\tdevice\n", None),
            ("List of devices attached\nA\tunauthorized\n", "A"),
            ("List of devices attached\nA\toffline\n", "A"),
            ("List of devices attached\n???????????? no permissions (verify udev rules)\n", "????????????"),
        ]
        for devices, serial in cases:
            with self.subTest(devices=devices, serial=serial), tempfile.TemporaryDirectory(dir=TEST_ROOT) as root:
                output = Path(root) / "new-capture"
                fake = FakeAdb(devices)
                argv = ["--output", str(output)] + (["--serial", serial] if serial else [])
                with patch.object(collector_module.subprocess, "run", side_effect=fake):
                    result = collector_module.main(argv)
                self.assertEqual(result, 2)
                manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
                self.assertIsNotNone(manifest["fatal_error"])

    def test_refuses_existing_nonempty_output_without_adb_calls(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as root:
            output = Path(root) / "existing"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            fake = FakeAdb()
            with patch.object(collector_module.subprocess, "run", side_effect=fake):
                result = collector_module.main(["--output", str(output)])
            self.assertEqual(result, 2)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
            self.assertEqual(fake.calls, [])

    def test_failure_and_timeout_are_recorded_and_collection_continues(self):
        fake = FakeAdb(fail_label="telephony.registry", timeout_label="dumpsys telecom")
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as root:
            code, output = self.run_collector(root, fake)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            failed = next(item for item in manifest["commands"] if "telephony.registry" in item["argv"])
            timed_out = next(item for item in manifest["commands"] if item["timed_out"])
            self.assertEqual(failed["returncode"], 17)
            self.assertEqual((output / failed["stderr_file"]).read_bytes(), b"expected failure")
            self.assertTrue(timed_out["timed_out"])
            self.assertIsNone(timed_out["returncode"])
            self.assertTrue(any("dumpsys" in item["argv"] and "package" in item["argv"] for item in manifest["commands"]))

    def test_bugreport_requires_opt_in_and_is_inside_output(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as root:
            fake = FakeAdb()
            code, output = self.run_collector(root, fake, "--bugreport")
            self.assertEqual(code, 0)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            bugreport = next(item for item in manifest["commands"] if item["label"] == "bugreport_opt_in_slow")
            self.assertEqual(bugreport["timeout_seconds"], 300)
            self.assertEqual(Path(bugreport["argv"][-1]), output / "bugreport.zip")
            self.assertEqual((output / "bugreport.zip").read_bytes(), b"fake bugreport")

    def test_interrupt_saves_manifest_with_prior_completed_commands(self):
        fake = FakeAdb()

        def interrupt_during_uptime(argv, **kwargs):
            if "uptime" in argv:
                raise KeyboardInterrupt
            return fake(argv, **kwargs)

        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as root:
            code, output = self.run_collector(root, interrupt_during_uptime)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            labels = [item["label"] for item in manifest["commands"]]
            self.assertEqual(code, 130)
            self.assertEqual(labels, ["adb_version", "adb_devices", "device_date"])
            self.assertIn("KeyboardInterrupt", manifest["fatal_error"])
            self.assertTrue((output / "003_device_date.stdout.txt").exists())

    def test_help_exits_without_running_adb(self):
        with patch.object(collector_module.subprocess, "run") as run:
            with self.assertRaises(SystemExit) as raised:
                collector_module.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
