import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_legacy_wfc_gate as B


class LegacyWfcBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.pins = self.base / "pins.json"

    def tearDown(self):
        self.temporary.cleanup()

    def pins_for(self, primary):
        self.pins.write_text(json.dumps({
            "schema_version": 1, "transformation_id": B.IDENTITY,
            "classes_dex_sha256": hashlib.sha256(primary).hexdigest(),
            "unsigned_apk_sha256": "1" * 64,
        }), encoding="utf-8")

    def archive(self, primary=b"new", bridge=b"bridge", extra=False):
        apk = self.base / "ims.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("classes.dex", primary)
            archive.writestr("classes2.dex", bridge)
            if extra:
                archive.writestr("classes3.dex", b"unexpected")
        return apk

    def test_packaged_gate_preserves_bridge_and_rejects_old_primary(self):
        self.pins_for(b"new")
        apk = self.archive()
        with patch.object(B.BV1, "BRIDGE_DEX", hashlib.sha256(b"bridge").hexdigest()):
            result = B.verify_apk(apk, self.pins)
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["runtime_validated"])
            self.archive(primary=b"old")
            with self.assertRaisesRegex(B.BuildError, "primary/bridge"):
                B.verify_apk(apk, self.pins)

    def test_changed_bridge_and_extra_dex_are_rejected(self):
        self.pins_for(b"new")
        with patch.object(B.BV1, "BRIDGE_DEX", hashlib.sha256(b"bridge").hexdigest()):
            with self.assertRaisesRegex(B.BuildError, "primary/bridge"):
                B.verify_apk(self.archive(bridge=b"changed"), self.pins)
            with self.assertRaisesRegex(B.BuildError, "inventory"):
                B.verify_apk(self.archive(extra=True), self.pins)

    def test_pin_identity_and_hash_validation(self):
        self.pins_for(b"new")
        data = json.loads(self.pins.read_text(encoding="utf-8"))
        data["transformation_id"] = "BV1-w2l-ip-continuity-trial"
        self.pins.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(B.BuildError, "identity"):
            B.load_pins(self.pins)
        data["transformation_id"] = B.IDENTITY
        data["classes_dex_sha256"] = "UNPROMOTED"
        self.pins.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(B.BuildError, "promoted"):
            B.load_pins(self.pins)

    def test_roundtrip_rejects_instruction_changes_in_any_class(self):
        source, final = self.base / "source", self.base / "final"
        content = (
            ".class public Lfixture;\n.super Ljava/lang/Object;\n"
            ".method public run()V\n    .locals 1\n"
            "    const-string v0, \"same\"\n    return-void\n.end method\n"
        )
        for root in (source, final):
            for name in (*B.TRANSFORM.PATCHERS, "Unrelated.smali"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        self.assertEqual(B.verify_roundtrip(source, final)["classes_verified"], 3)
        (final / "Unrelated.smali").write_text(content.replace('"same"', '"changed"'), encoding="utf-8")
        with self.assertRaisesRegex(B.BuildError, "Unrelated"):
            B.verify_roundtrip(source, final)


if __name__ == "__main__":
    unittest.main()
