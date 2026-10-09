import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ec2_builder_tests", ROOT / "tools/build_epdgservice_w2l_trial.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class TrialBuilderTests(unittest.TestCase):
    def test_roundtrip_normalization_preserves_control_flow_and_catch_order(self):
        source = '''.class public LHelper;
.super Ljava/lang/Object;
.method public static sample(I)I
 .locals 1
 :start
 packed-switch p0, :table
 const/4 v0, 0x0
 goto :done
 :yes
 const/4 v0, 0x1
 :done
 return v0
 :end
 :handler
 move-exception v0
 throw v0
 :table
 .packed-switch 0x0
 :yes
 :done
 .end packed-switch
 .catch Ljava/lang/RuntimeException; {:start .. :end} :handler
.end method
'''
        canonical = source.replace(":yes", ":cond_1").replace(":done", ":cond_2").replace("goto ", "goto/16 ").replace("\n :table\n", "\n nop\n :table\n")
        self.assertEqual(M.normalized_smali(source), M.normalized_smali(canonical))
        for old, new in ((" :cond_1\n :cond_2", " :cond_2\n :cond_1"),
                         ("const/4 v0, 0x1", "const/4 v0, 0x2"),
                         ("{:start .. :end}", "{:done .. :end}"),
                         ("packed-switch p0", "packed-switch v0")):
            with self.subTest(old=old):
                self.assertNotEqual(M.normalized_smali(source), M.normalized_smali(canonical.replace(old, new)))

    def test_redecoded_pin_is_separate_and_strict(self):
        ec1 = {"targets": [], "roundtrip_normalizations": []}
        trial = {"targets": [{"path": "changed", "output_sha256": "raw", "redecoded_sha256": "canonical"}]}
        M.verify_classes({"changed": "stock"}, {"changed": "canonical"}, ec1, trial)
        with self.assertRaises(M.BuildError):
            M.verify_classes({"changed": "stock"}, {"changed": "raw"}, ec1, trial)

    def test_envelope_allows_only_ec1_ec2_additions_and_known_normalization(self):
        stock = {"plain": "a", "ec1": "b", "ec2": "c", "normal": "d"}
        ec1 = {"targets": [{"path": "ec1", "output_sha256": "B"}],
               "roundtrip_normalizations": [{"path": "normal", "input_sha256": "d", "output_sha256": "D"}]}
        trial = {"targets": [{"path": "ec2", "output_sha256": "C"}],
                 "additions": [{"path": "helper", "output_sha256": "H"}]}
        verified = {"plain": "a", "ec1": "B", "ec2": "C", "normal": "D", "helper": "H"}
        M.verify_classes(stock, verified, ec1, trial)
        for path in verified:
            with self.subTest(path=path), self.assertRaises(M.BuildError):
                M.verify_classes(stock, {**verified, path: "unapproved"}, ec1, trial)
        with self.assertRaisesRegex(M.BuildError, "inventory"):
            M.verify_classes(stock, {**verified, "unexpected": "new"}, ec1, trial)
        with self.assertRaisesRegex(M.BuildError, "inventory"):
            M.verify_classes(stock, {k: v for k, v in verified.items() if k != "helper"}, ec1, trial)

    def test_ec2_overlap_overrides_ec1_final_hash(self):
        M.verify_classes({"both": "stock"}, {"both": "ec2"},
                         {"targets": [{"path": "both", "output_sha256": "ec1"}], "roundtrip_normalizations": []},
                         {"targets": [{"path": "both", "output_sha256": "ec2"}]})

    def test_missing_or_unpromoted_pins_cannot_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pins.json"
            pins = {"schema_version": 1, "transformation_id": "EC2-active-w2l-trial",
                    "classes_dex_sha256": "a" * 64, "unsigned_apk_sha256": "b" * 64}
            path.write_text(json.dumps(pins), encoding="utf-8")
            self.assertEqual(M.load_pins(path), pins)
            for bad in (None, "pending", "Z" * 64):
                pins["classes_dex_sha256"] = bad
                path.write_text(json.dumps(pins), encoding="utf-8")
                with self.assertRaises(M.BuildError):
                    M.load_pins(path)

    def test_added_overlay_cannot_overwrite_existing_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = root / "overlay"
            decoded = root / "decoded"
            overlay.mkdir()
            decoded.mkdir()
            source = overlay / "Helper.smali"
            source.write_text(".class LHelper;\n", encoding="utf-8")
            added = [{"path": "Helper.smali", "output_sha256": M.BASE.sha256_file(source)}]
            (decoded / "Helper.smali").write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(M.BuildError, "already exists"):
                M._trial_overlay(overlay, decoded, [], added)
            self.assertEqual((decoded / "Helper.smali").read_text(), "existing")


if __name__ == "__main__":
    unittest.main()
