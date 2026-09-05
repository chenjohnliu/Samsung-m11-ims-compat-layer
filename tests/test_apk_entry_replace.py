import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.apk_entry_replace import SafetyError, build_archive


def write_zip(path: Path, entries, *, duplicate=False):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
        if duplicate:
            archive.writestr(entries[0][0], b"duplicate")


class ApkEntryReplaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def base(self):
        path = self.root / "base.apk"
        write_zip(
            path,
            [
                ("AndroidManifest.xml", b"old manifest"),
                ("classes.dex", b"old dex"),
                ("META-INF/CERT.RSA", b"rsa"),
                ("META-INF/CERT.SF", b"sf"),
                ("META-INF/MANIFEST.MF", b"signature manifest"),
                ("META-INF/maven/example/pom.xml", b"keep maven"),
                ("META-INF/services/example.Service", b"keep service"),
                ("res/raw/data.bin", b"keep resource"),
            ],
        )
        return path

    def source(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_preserves_metadata_and_strips_only_exact_signatures(self):
        output = self.root / "out.apk"
        report = build_archive(
            self.base(),
            output,
            {"classes.dex": self.source("classes.new", b"new dex")},
            {"classes2.dex": self.source("classes2.new", b"bridge dex")},
        )
        with zipfile.ZipFile(output) as archive:
            names = set(archive.namelist())
            self.assertNotIn("META-INF/CERT.RSA", names)
            self.assertNotIn("META-INF/CERT.SF", names)
            self.assertNotIn("META-INF/MANIFEST.MF", names)
            self.assertEqual(archive.read("META-INF/maven/example/pom.xml"), b"keep maven")
            self.assertEqual(archive.read("META-INF/services/example.Service"), b"keep service")
            self.assertEqual(archive.read("res/raw/data.bin"), b"keep resource")
            self.assertEqual(archive.read("classes.dex"), b"new dex")
            self.assertEqual(archive.read("classes2.dex"), b"bridge dex")
        changed = {(item["entry"], item["status"]) for item in report["changed_entries"]}
        self.assertIn(("classes.dex", "replaced"), changed)
        self.assertIn(("classes2.dex", "added"), changed)
        self.assertEqual(
            report["removed_signatures"],
            ["META-INF/CERT.RSA", "META-INF/CERT.SF", "META-INF/MANIFEST.MF"],
        )
        json.dumps(report)

    def test_rejects_traversal(self):
        base = self.root / "bad.apk"
        write_zip(base, [("../escape", b"bad")])
        with self.assertRaisesRegex(SafetyError, "non-canonical"):
            build_archive(base, self.root / "out.apk", {}, {})

    def test_rejects_duplicate_entries(self):
        base = self.root / "duplicate.apk"
        write_zip(base, [("classes.dex", b"one")], duplicate=True)
        with self.assertRaisesRegex(SafetyError, "duplicate"):
            build_archive(base, self.root / "out.apk", {}, {})

    def test_rejects_symlink_like_entry(self):
        base = self.root / "symlink.apk"
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(base, "w") as archive:
            archive.writestr(info, "target")
        with self.assertRaisesRegex(SafetyError, "symlink-like"):
            build_archive(base, self.root / "out.apk", {}, {})

    def test_rejects_unallowed_addition(self):
        with self.assertRaisesRegex(SafetyError, "missing from base"):
            build_archive(
                self.base(),
                self.root / "out.apk",
                {"classes2.dex": self.source("new.dex", b"new")},
                {},
            )

    def test_rejects_add_over_existing_entry(self):
        with self.assertRaisesRegex(SafetyError, "cannot replace existing"):
            build_archive(
                self.base(),
                self.root / "out.apk",
                {},
                {"classes.dex": self.source("new.dex", b"new")},
            )

    def test_rejects_conflicting_existing_output_and_keeps_it(self):
        output = self.root / "out.apk"
        output.write_bytes(b"do not overwrite")
        with self.assertRaisesRegex(SafetyError, "refusing to overwrite"):
            build_archive(
                self.base(),
                output,
                {"classes.dex": self.source("new.dex", b"new")},
                {},
            )
        self.assertEqual(output.read_bytes(), b"do not overwrite")

    def test_identical_existing_output_is_idempotent(self):
        base = self.base()
        output = self.root / "out.apk"
        source = self.source("new.dex", b"new")
        first = build_archive(base, output, {"classes.dex": source}, {})
        before = output.read_bytes()
        second = build_archive(base, output, {"classes.dex": source}, {})
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(first["output_sha256"], second["output_sha256"])


if __name__ == "__main__":
    unittest.main()
