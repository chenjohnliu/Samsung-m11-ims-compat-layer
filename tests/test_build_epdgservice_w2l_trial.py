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
        jumbo_fixture = ".class LString;\n.method static m()V\n const-string v0, \"x\"\n return-void\n.end method\n"
        self.assertEqual(M.normalized_smali(jumbo_fixture.replace("const-string ", "const-string/jumbo ")),
                         M.normalized_smali(jumbo_fixture))
        self.assertNotEqual(M.normalized_smali(jumbo_fixture.replace('"x"', '"y"').replace("const-string ", "const-string/jumbo ")),
                            M.normalized_smali(jumbo_fixture))
        for old, new in ((" :cond_1\n :cond_2", " :cond_2\n :cond_1"),
                         ("const/4 v0, 0x1", "const/4 v0, 0x2"),
                         ("{:start .. :end}", "{:done .. :end}"),
                         ("packed-switch p0", "packed-switch v0")):
            with self.subTest(old=old):
                self.assertNotEqual(M.normalized_smali(source), M.normalized_smali(canonical.replace(old, new)))

    def test_source_roundtrip_covers_untouched_classes_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before, after = root / "before", root / "after"
            before.mkdir(); after.mkdir()
            source = ".class public LOther;\n.super Ljava/lang/Object;\n.method public m()V\n return-void\n.end method\n"
            (before / "Other.smali").write_text(source, encoding="utf-8")
            (after / "Other.smali").write_text(source, encoding="utf-8")
            self.assertEqual(M.verify_roundtrip_sources(before, after, {"targets": [], "additions": []}, True), 1)
            (after / "Other.smali").write_text(source.replace("return-void", "nop\n return-void"), encoding="utf-8")
            with self.assertRaisesRegex(M.BuildError, "round-trip drift"):
                M.verify_roundtrip_sources(before, after, {"targets": [], "additions": []}, True)
            (after / "Other.smali").unlink()
            (after / "Added.smali").write_text(source.replace("LOther;", "LAdded;"), encoding="utf-8")
            with self.assertRaisesRegex(M.BuildError, "inventory drift"):
                M.verify_roundtrip_sources(before, after, {"targets": [], "additions": []}, True)

    def test_source_verified_only_bypasses_serialized_output_hashes(self):
        pins = {"schema_version": 1, "transformation_id": "EC2-active-w2l-trial",
                "classes_dex_sha256": "a" * 64, "unsigned_apk_sha256": "b" * 64}
        changed = {**pins, "classes_dex_sha256": "c" * 64, "unsigned_apk_sha256": "d" * 64}
        with self.assertRaisesRegex(M.BuildError, "pin drift"):
            M.verify_output_pins(changed, pins)
        M.verify_output_pins(changed, pins, True)
        with self.assertRaisesRegex(M.BuildError, "identity drift"):
            M.verify_output_pins({**changed, "transformation_id": "other"}, pins, True)

    def test_source_verified_parser_is_opt_in(self):
        args = M.parser().parse_args(["--stock-apk", "stock.apk", "--apktool-jar", "apktool.jar",
                                     "--java", "java", "--report", "report.json", "--output", "out.apk"])
        self.assertFalse(args.source_verified)
        args = M.parser().parse_args(["--stock-apk", "stock.apk", "--apktool-jar", "apktool.jar",
                                     "--java", "java", "--report", "report.json", "--output", "out.apk",
                                     "--source-verified"])
        self.assertTrue(args.source_verified)

    def test_static_explicit_defaults_normalize_only_when_semantically_exact(self):
        def field(declaration):
            return ".class public LFields;\n.super Ljava/lang/Object;\n" + declaration + "\n"
        self.assertEqual(M.normalized_smali(field(".field public static final FLAG:Z = false")),
                         M.normalized_smali(field(".field public static final FLAG:Z")))
        self.assertEqual(M.normalized_smali(field(".field public static COUNT:I = 0x0")),
                         M.normalized_smali(field(".field public static COUNT:I")))
        for declared, absent in (
                (".field public static final FLAG:Z = true", ".field public static final FLAG:Z"),
                (".field private static final FLAG:Z = false", ".field public static final FLAG:Z"),
                (".field public static final FLAG:I = 0", ".field public static final FLAG:Z"),
                (".field public static final VALUE:F = -0.0f", ".field public static final VALUE:F")):
            with self.subTest(declared=declared):
                self.assertNotEqual(M.normalized_smali(field(declared)), M.normalized_smali(field(absent)))

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

    def test_source_verified_uses_semantic_roundtrip_for_transformed_final_hashes_only(self):
        stock = {"changed": "stock", "plain": "plain"}
        ec1 = {"targets": [{"path": "changed", "output_sha256": "old-final-pin"}],
               "roundtrip_normalizations": []}
        trial = {"targets": []}
        verified = {"changed": "redecoded-but-different-text", "plain": "plain"}
        with self.assertRaisesRegex(M.BuildError, "hash drift"):
            M.verify_classes(stock, verified, ec1, trial)
        M.verify_classes(stock, verified, ec1, trial, source_verified=True)
        with self.assertRaisesRegex(M.BuildError, "hash drift"):
            M.verify_classes(stock, {**verified, "plain": "changed"}, ec1, trial,
                             source_verified=True)

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
