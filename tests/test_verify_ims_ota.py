import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "verify_ims_ota.py"
SPEC = importlib.util.spec_from_file_location("verify_ims_ota", SCRIPT)
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class TransferListTests(unittest.TestCase):
    def test_m11_install_locations_distinguish_ims_system_ext_from_telecom(self):
        self.assertEqual(verify.REQUIRED["Telecom.apk"][0],
                         "system/priv-app/Telecom/Telecom.apk")
        self.assertEqual(verify.REQUIRED["imsservice.apk"][0],
                         "system/system_ext/priv-app/imsservice/imsservice.apk")

    def test_header_and_ranges(self):
        ops, maximum, blocks = verify.parse_transfer(b"4\n10\n0\n0\nnew 4,1,3,7,8\nzero 2,8,10\n")
        self.assertEqual(maximum, 10)
        self.assertEqual(blocks, 3)
        self.assertEqual(ops[0], ("new", [(1, 3), (7, 8)]))

    def test_rejects_bad_header_ranges_and_unknown_commands(self):
        for payload in (
            b"3\n10\n0\n0\nnew 2,0,1\n",
            b"4\n10\n0\n0\nnew 3,0,1\n",
            b"4\n10\n0\n0\nmove 2,0,1\n",
            b"4\n10\n0\n0\nnew 2,0,2097153\n",
            b"4\n10\n0\n0\nnew 2,0,3\nzero 2,2,4\n",
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                verify.parse_transfer(payload)

    def test_written_block_header_is_not_the_partition_size(self):
        ops, maximum, blocks = verify.parse_transfer(
            b"4\n2\n0\n0\nerase 2,4,8\nnew 4,0,1,3,4\n")
        self.assertEqual(maximum, 8)
        self.assertEqual(blocks, 2)

    def test_reconstruct_sparse_block_mapping(self):
        payload = b"4\n4\n0\n0\nnew 4,1,2,3,4\n"
        chunk = b"A" * verify.BLOCK + b"B" * verify.BLOCK
        with tempfile.TemporaryDirectory(dir=SCRIPT.parents[1]) as td:
            root = Path(td)
            archive = root / "ota.zip"
            out = root / "out"
            out.mkdir()
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("system.transfer.list", payload)
                z.writestr("system.new.dat.br", b"synthetic")
            def fake_brotli(argv, check):
                Path(argv[argv.index("-o") + 1]).write_bytes(chunk)
                return subprocess.CompletedProcess(argv, 0)
            with zipfile.ZipFile(archive) as z, patch.object(verify.subprocess, "run", side_effect=fake_brotli):
                image = verify.reconstruct(z, "system", out, "brotli")
            with image.open("rb") as f:
                self.assertEqual(len(f.read()), 4 * verify.BLOCK)
            with image.open("rb") as f:
                f.seek(verify.BLOCK)
                self.assertEqual(f.read(verify.BLOCK), b"A" * verify.BLOCK)
                f.seek(2 * verify.BLOCK)
                self.assertEqual(f.read(verify.BLOCK), b"\0" * verify.BLOCK)
                self.assertEqual(f.read(verify.BLOCK), b"B" * verify.BLOCK)

    def test_rejects_truncated_or_trailing_new_data(self):
        payload = b"4\n2\n0\n0\nnew 2,0,2\n"
        for data in (b"short", b"X" * (2 * verify.BLOCK + 1)):
            with tempfile.TemporaryDirectory(dir=SCRIPT.parents[1]) as td:
                root = Path(td)
                archive, out = root / "a.zip", root / "out"
                out.mkdir()
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr("system.transfer.list", payload)
                    z.writestr("system.new.dat.br", b"x")
                def fake_brotli(argv, check, data=data):
                    Path(argv[argv.index("-o") + 1]).write_bytes(data)
                with zipfile.ZipFile(archive) as z, patch.object(verify.subprocess, "run", side_effect=fake_brotli):
                    with self.assertRaises(ValueError):
                        verify.reconstruct(z, "system", out, "brotli")

    def test_output_directory_must_be_new(self):
        with tempfile.TemporaryDirectory(dir=SCRIPT.parents[1]) as td:
            parent = Path(td)
            verify.validate_output_location(parent / "fresh")
            with self.assertRaises(ValueError):
                verify.validate_output_location(parent)


if __name__ == "__main__":
    unittest.main()
