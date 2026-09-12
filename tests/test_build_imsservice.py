import argparse
import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "build_imsservice.py"
CONFIG = ROOT / "devices" / "m11q" / "imsservice-build.json"
PAYLOAD = ROOT / "devices" / "m11q" / "payload-manifest.tsv"


def load():
    spec = importlib.util.spec_from_file_location("build_imsservice", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load()


class BuildImsserviceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_repository_config_pins_complete_pipeline(self):
        config = MODULE.load_config(CONFIG)
        self.assertEqual(config["ordered_patches"], [
            "BC1-modern-mmtel-discovery", "BC2-modern-bridge-native-hooks",
            "BG1-network-statistics-guard", "BH1-sms-icc-type-compat",
            "BP1-sms-hqm-telemetry-guard"])
        self.assertEqual(len(config["bridge_source"]["files"]), 7)
        self.assertEqual(config["bridge_source"]["publication_status"],
                         "project-authored-apache-2.0")
        self.assertEqual(MODULE.DEFAULT_BRIDGE, ROOT / "bridge" / "java")
        self.assertEqual(config["stock_framework_res"]["size"], 69575977)
        self.assertEqual(config["toolchain"]["apktool"]["jvm_args"],
                         ["-XX:ActiveProcessorCount=1"])
        self.assertEqual(config["final_dex_invariants"]["entries"]["classes.dex"],
                         "a16a42ed01d284dc20efa57c67c6f18b6ffb20132367228b7e8a8c90f5eb90c6")
        self.assertEqual(config["final_dex_invariants"]["entries"]["classes2.dex"],
                         "8c51137524e0adf37305f852ea28306ac44ee86b5a92963e9ff19b32c314756b")
        self.assertEqual(config["final_dex_invariants"]["unsigned_apk_sha256"],
                         "607491254442757133bcf2034f43763d5629f31961b3d787b01fbde8437633d9")
        self.assertEqual(config["final_dex_invariants"]["pin_state"], "pinned")
        self.assertEqual(config["final_dex_invariants"]["pin_basis"],
                         "current-source-build")
        self.assertIn("javap_sha256", config["toolchain"]["jdk11"])
        self.assertEqual(MODULE.payload_identity(
            PAYLOAD, "/system/framework/imsmanager.jar"),
            ("ba88f7111ea5c678d597dcb0498ee9fc42611fd4f6af12b6312fad05495de78b",
             671422))

    def test_repository_bridge_sources_match_manifest(self):
        config = MODULE.load_config(CONFIG)
        sources = MODULE._bridge_sources(MODULE.DEFAULT_BRIDGE, config)
        self.assertEqual(len(sources), 7)
        self.assertTrue(all(MODULE.DEFAULT_BRIDGE.resolve() in source.parents
                            for source in sources))

    def test_config_and_payload_drift_fail_closed(self):
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
        raw["ordered_patches"].reverse()
        changed = self.base / "changed.json"
        changed.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.BuildError, "ordered transformation"):
            MODULE.load_config(changed)
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
        raw["toolchain"]["apktool"]["jvm_args"] = []
        changed.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.BuildError, "JVM determinism"):
            MODULE.load_config(changed)
        for field in ("pin_state", "pin_basis"):
            raw = json.loads(CONFIG.read_text(encoding="utf-8"))
            del raw["final_dex_invariants"][field]
            changed.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.BuildError, "malformed build config"):
                MODULE.load_config(changed)
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
        raw["final_dex_invariants"]["pin_state"] = "needs-promotion"
        changed.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.BuildError, "basis/state mismatch"):
            MODULE.load_config(changed)
        manifest = self.base / "payload.tsv"
        manifest.write_text("stock_path\tstock_sha256\tstock_size\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.BuildError, "occurrence drift"):
            MODULE.payload_identity(manifest, "/system/framework/imsmanager.jar")

    def test_expected_file_rejects_hash_size_and_symlink(self):
        source = self.base / "source"
        source.write_bytes(b"exact")
        digest = hashlib.sha256(b"exact").hexdigest()
        self.assertEqual(MODULE._expected_file(source, "fixture", digest, 5), source.resolve())
        with self.assertRaisesRegex(MODULE.BuildError, "size mismatch"):
            MODULE._expected_file(source, "fixture", digest, 4)
        with self.assertRaisesRegex(MODULE.BuildError, "SHA-256 mismatch"):
            MODULE._expected_file(source, "fixture", "0" * 64)
        link = self.base / "link"
        try:
            link.symlink_to(source)
        except OSError:
            return
        with self.assertRaisesRegex(MODULE.BuildError, "non-symlink"):
            MODULE._expected_file(link, "fixture", digest)

    def test_bridge_source_inventory_and_hashes_are_exact(self):
        root = self.base / "bridge"
        relative = "com/sec/internal/google/Only.java"
        source = root / relative
        source.parent.mkdir(parents=True)
        source.write_bytes(b"class Only {}\n")
        config = {"bridge_source": {"files": {
            relative: hashlib.sha256(source.read_bytes()).hexdigest()}}}
        self.assertEqual(MODULE._bridge_sources(root, config), [source.resolve()])
        (root / "Extra.java").write_text("class Extra {}", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.BuildError, "inventory drift"):
            MODULE._bridge_sources(root, config)

    def test_bridge_jar_includes_only_allowlisted_bridge_classes(self):
        classes = self.base / "classes"
        package = classes / "com/sec/internal/google"
        package.mkdir(parents=True)
        for name in ("ModernOne.class", "ModernOne$Inner.class", "GoogleImsService.class"):
            (package / name).write_bytes(name.encode())
        jar = self.base / "bridge.jar"
        result = MODULE._bridge_jar(classes, jar, {
            "bridge_source": {"top_level_classes": ["ModernOne"]}})
        self.assertEqual(result["class_count"], 2)
        with zipfile.ZipFile(jar) as archive:
            self.assertEqual(set(archive.namelist()), {
                "com/sec/internal/google/ModernOne.class",
                "com/sec/internal/google/ModernOne$Inner.class"})

    @staticmethod
    def write_zip(path, entries):
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

    def test_final_zip_gate_preserves_every_unrelated_entry(self):
        stock = self.base / "stock.apk"
        candidate = self.base / "candidate.apk"
        stock_entries = {"AndroidManifest.xml": b"old-manifest", "classes.dex": b"old-dex",
                         "res/raw/a": b"keep", "META-INF/CERT.RSA": b"sig"}
        final_entries = {"AndroidManifest.xml": b"new-manifest", "classes.dex": b"primary",
                         "classes2.dex": b"bridge", "res/raw/a": b"keep"}
        self.write_zip(stock, stock_entries)
        self.write_zip(candidate, final_entries)
        config = {"final_dex_invariants": {"entries": {
            "classes.dex": hashlib.sha256(b"primary").hexdigest(),
            "classes2.dex": hashlib.sha256(b"bridge").hexdigest()},
            "unsigned_apk_sha256": MODULE.sha256_file(candidate)}}
        result = MODULE._verify_zip(stock, candidate, config)
        self.assertEqual(result["dex_sha256"]["classes.dex"],
                         hashlib.sha256(b"primary").hexdigest())
        wrong_apk = json.loads(json.dumps(config))
        wrong_apk["final_dex_invariants"]["unsigned_apk_sha256"] = "0" * 64
        with self.assertRaisesRegex(MODULE.BuildError, "unsigned APK hash"):
            MODULE._verify_zip(stock, candidate, wrong_apk)
        final_entries["res/raw/a"] = b"changed"
        self.write_zip(candidate, final_entries)
        with self.assertRaisesRegex(MODULE.BuildError, "undeclared"):
            MODULE._verify_zip(stock, candidate, config)

    def test_candidate_inspection_reports_hashes_without_relaxing_structure(self):
        stock = self.base / "stock.apk"
        candidate = self.base / "candidate.apk"
        stock_entries = {"AndroidManifest.xml": b"old", "classes.dex": b"old-dex",
                         "res/raw/a": b"keep", "META-INF/CERT.SF": b"sig"}
        final_entries = {"AndroidManifest.xml": b"new", "classes.dex": b"primary",
                         "classes2.dex": b"bridge", "res/raw/a": b"keep"}
        self.write_zip(stock, stock_entries)
        self.write_zip(candidate, final_entries)
        observed = MODULE._inspect_zip(stock, candidate)
        self.assertEqual(observed["dex_sha256"]["classes.dex"],
                         hashlib.sha256(b"primary").hexdigest())
        self.assertEqual(observed["dex_sha256"]["classes2.dex"],
                         hashlib.sha256(b"bridge").hexdigest())
        self.assertEqual(observed["apk_sha256"], MODULE.sha256_file(candidate))
        config = {"final_dex_invariants": {"entries": {
            "classes.dex": "0" * 64, "classes2.dex": "1" * 64},
            "unsigned_apk_sha256": "2" * 64}}
        with self.assertRaisesRegex(MODULE.BuildError, "classes.dex hash mismatch"):
            MODULE._verify_pinned_invariants(observed, config)
        final_entries["res/raw/a"] = b"changed"
        self.write_zip(candidate, final_entries)
        with self.assertRaisesRegex(MODULE.BuildError, "undeclared"):
            MODULE._inspect_zip(stock, candidate)

    def test_mode_gate_is_explicit_and_fail_closed(self):
        needs = {"final_dex_invariants": {"pin_state": "needs-promotion"}}
        pinned = {"final_dex_invariants": {"pin_state": "pinned"}}
        with self.assertRaisesRegex(MODULE.BuildError, "promoted"):
            MODULE._validate_mode(argparse.Namespace(mode="strict", output=self.base / "x"), needs)
        with self.assertRaisesRegex(MODULE.BuildError, "requires --output"):
            MODULE._validate_mode(argparse.Namespace(mode="strict", output=None), pinned)
        self.assertEqual(MODULE._validate_mode(
            argparse.Namespace(mode="strict", output=self.base / "x"), pinned), "strict")
        self.assertEqual(MODULE._validate_mode(
            argparse.Namespace(mode="candidate-invariants", output=None), needs),
            "candidate-invariants")
        with self.assertRaisesRegex(MODULE.BuildError, "requires needs-promotion"):
            MODULE._validate_mode(argparse.Namespace(
                mode="candidate-invariants", output=None), pinned)
        with self.assertRaisesRegex(MODULE.BuildError, "does not publish"):
            MODULE._validate_mode(argparse.Namespace(
                mode="candidate-invariants", output=self.base / "x"), needs)

    def test_parser_defaults_to_strict_and_candidate_is_explicit(self):
        required = []
        for option in ("--stock-apk", "--framework-res-apk", "--imsmanager-jar",
                       "--framework-jar", "--apktool-jar", "--java", "--javac",
                       "--javap", "--r8-jar", "--zipalign", "--report"):
            required.extend((option, "placeholder"))
        self.assertEqual(MODULE.parser().parse_args(required).mode, "strict")
        self.assertEqual(MODULE.parser().parse_args(
            required + ["--mode", "candidate-invariants"]).mode,
            "candidate-invariants")

    def test_candidate_payload_is_unambiguously_unpublished_and_private(self):
        observed = {"entry_count": 3,
            "changed_entries": ["AndroidManifest.xml", "classes.dex", "classes2.dex"],
            "manifest_sha256": "3" * 64,
            "dex_sha256": {"classes.dex": "4" * 64, "classes2.dex": "5" * 64},
            "apk_sha256": "6" * 64}
        expected = {"pin_state": "needs-promotion",
            "pin_basis": "stale-runtime-reference",
            "entries": {"classes.dex": "0" * 64, "classes2.dex": "5" * 64},
            "unsigned_apk_sha256": "1" * 64}
        payload = MODULE._candidate_payload({"schema_version": 1,
            "mode": "candidate-invariants"}, observed, expected)
        self.assertEqual(payload["status"], "PIN_DISCOVERY")
        for field in ("strict_pins_verified", "artifact_published", "release_eligible",
                      "runtime_validated"):
            self.assertFalse(payload[field])
        self.assertEqual(payload["pin_matches"], {
            "classes.dex": False, "classes2.dex": True,
            "unsigned_apk_sha256": False})
        rendered = json.dumps(payload)
        self.assertNotIn(str(self.base), rendered)
        self.assertNotIn(".smali", rendered)

    def test_candidate_report_is_atomic_nonoverwriting_and_config_unchanged(self):
        report = self.base / "candidate.json"
        config = self.base / "config.json"
        config.write_bytes(b'{"unchanged":true}\n')
        before = config.read_bytes()
        payload = {"status": "PIN_DISCOVERY", "artifact_published": False}
        MODULE._publish_report(report, payload)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8")), payload)
        self.assertEqual(config.read_bytes(), before)
        with self.assertRaisesRegex(MODULE.BuildError, "overwrite"):
            MODULE._publish_report(report, payload)
        self.assertEqual(config.read_bytes(), before)

        failed = self.base / "failed.json"
        with mock.patch.object(MODULE.os, "link", side_effect=OSError("synthetic")):
            with self.assertRaisesRegex(OSError, "synthetic"):
                MODULE._publish_report(failed, payload)
        self.assertFalse(failed.exists())
        self.assertEqual(list(self.base.glob(".failed.json.*.tmp")), [])

    def test_observed_invariants_promote_to_strict_exactly(self):
        observed = {"dex_sha256": {"classes.dex": "a" * 64,
                                    "classes2.dex": "b" * 64},
                    "apk_sha256": "c" * 64}
        promoted = {"final_dex_invariants": {
            "entries": dict(observed["dex_sha256"]),
            "unsigned_apk_sha256": observed["apk_sha256"]}}
        MODULE._verify_pinned_invariants(observed, promoted)
        promoted["final_dex_invariants"]["entries"]["classes2.dex"] = "d" * 64
        with self.assertRaisesRegex(MODULE.BuildError, "classes2.dex hash mismatch"):
            MODULE._verify_pinned_invariants(observed, promoted)

    def test_atomic_pair_publish_and_rollback(self):
        candidate = self.base / "candidate.apk"
        output = self.base / "output.apk"
        report = self.base / "report.json"
        candidate.write_bytes(b"apk")
        MODULE._publish_pair(candidate, output, report, {"status": "PASS"})
        self.assertEqual(output.read_bytes(), b"apk")
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "PASS")

        candidate2 = self.base / "candidate2.apk"
        output2 = self.base / "output2.apk"
        report2 = self.base / "report2.json"
        candidate2.write_bytes(b"apk2")
        with mock.patch.object(MODULE.os, "link", side_effect=OSError("synthetic")):
            with self.assertRaisesRegex(OSError, "synthetic"):
                MODULE._publish_pair(candidate2, output2, report2, {"status": "PASS"})
        self.assertFalse(output2.exists())
        self.assertFalse(report2.exists())
        self.assertEqual(list(self.base.glob(".report2.json.*.tmp")), [])

    def test_output_report_collision_and_nonoverwrite_fail(self):
        candidate = self.base / "candidate.apk"
        candidate.write_bytes(b"apk")
        same = self.base / "same"
        with self.assertRaisesRegex(MODULE.BuildError, "distinct"):
            MODULE._publish_pair(candidate, same, same, {})
        output, report = self.base / "output", self.base / "report"
        output.write_bytes(b"keep")
        with self.assertRaisesRegex(MODULE.BuildError, "overwrite"):
            MODULE._publish_pair(candidate, output, report, {})
        self.assertEqual(output.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
