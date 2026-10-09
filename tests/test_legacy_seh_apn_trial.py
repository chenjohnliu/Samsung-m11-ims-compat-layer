import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import legacy_seh_apn_trial as T


def sha(data):
    return hashlib.sha256(data).hexdigest()


class LegacySehApnTrialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.temporary.name)
        self.repo = self.sandbox / "repo"
        self.android = self.sandbox / "android"
        self.state = self.sandbox / "private-state"
        self.repo.mkdir()
        self.android.mkdir()

        self.original = {
            T.RIL: (b"final class RIL {\n    void connect() {\n" + T.RIL_ANCHOR
                    + b"}\n"),
            T.DPM: (b"void update(boolean changed) {\n    if (changed) {\n"
                    b"        changedOnly();\n    }\n" + T.DPM_ANCHOR + b"\n}\n"),
            T.PROP: b"ro.product.device=m11q\n",
            T.POLICY + "property.te": b"system_internal_prop(existing_prop)\n",
            T.POLICY + "property_contexts": b"ro.existing u:object_r:existing_prop:s0 exact bool\n",
            T.POLICY + "radio.te": b"get_prop(radio, existing_prop)\n",
            T.IMS: b"stock imsservice",
        }
        self.prerequisite_data = {
            "frameworks/base/telephony/java/android/telephony/ServiceState.java": b"service state",
            "frameworks/opt/telephony/src/java/com/android/internal/telephony/data/AccessNetworksManager.java": b"access networks",
            "frameworks/opt/telephony/src/java/com/android/internal/telephony/data/DataNetworkController.java": b"data network",
            "device/samsung/m11q/ims/proprietary/priv-app/EpdgService/EpdgService.apk": b"epdg",
            T.LEG1.VENDOR: b"compiled vendor fixture",
            T.IMS: self.original[T.IMS],
        }
        self.assets = {
            name: ("clean-room " + name + "\n").encode()
            for name in ("M11SehApnPolicy.java", "M11SehRadioTransport.java",
                         "M11SehRadioBridge.java", "M11SehProfilePublisher.java")
        }
        for relative, data in {**self.original, **self.prerequisite_data}.items():
            self.write(self.android, relative, data)
        for name, data in self.assets.items():
            self.write(self.repo, "platform/java/com/android/internal/telephony/" + name, data)
        self.pins_path = self.repo / "devices/m11q/seh-apn-bridge-build.json"
        self.write(self.repo, "devices/m11q/seh-apn-bridge-build.json", json.dumps({
            "schema_version": 1,
            "transformation_id": T.TRIAL,
            "java_sources": {name: sha(data) for name, data in self.assets.items()},
        }).encode())

        self.candidate_apk = self.sandbox / "candidate.apk"
        self.candidate_apk.write_bytes(b"strict LG3 candidate")
        self.lg3_pins = {"unsigned_apk_sha256": sha(self.candidate_apk.read_bytes()),
                         "fixture": "reviewed"}
        self.report = self.sandbox / "report.json"
        self.report.write_text(json.dumps({
            "mode": "strict", "status": "PASS", "observed_build_pins": self.lg3_pins,
            "output": {key: True for key in (
                "strict_pins_verified", "artifact_published",
                "all_redecoded_classes_verified", "unrelated_zip_entries_preserved")},
        }))

        prerequisite_hashes = {name: sha(data) for name, data in self.prerequisite_data.items()}
        expected = {name: sha(data) for name, data in self.original.items()}
        patches = (
            mock.patch.object(T, "ROOT", self.repo),
            mock.patch.object(T, "PINS", self.pins_path),
            mock.patch.object(T, "EXPECTED", expected),
            mock.patch.object(T.LEG1, "PREREQUISITES", prerequisite_hashes),
            mock.patch.object(T.LEG1, "binary_xml", return_value=object()),
            mock.patch.object(T.LEG1, "validate_vendor"),
            mock.patch.object(T.LG3, "load_pins", return_value=self.lg3_pins),
            mock.patch.object(T.LG3, "verify_apk", return_value={}),
            mock.patch.object(T.LG2, "verify_apk", return_value={}),
            mock.patch.object(T.SS1, "verify_framework", return_value={}),
            mock.patch.object(T.SS1, "dex_definitions", return_value=[]),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def write(root, relative, data):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def prepare(self):
        return T.prepare(self.android, self.state, self.candidate_apk, self.report)

    def snapshot(self, relatives=None):
        relatives = relatives or self.original
        return {name: (self.android / name).read_bytes() for name in relatives}

    def test_candidates_have_exact_hook_order_and_narrow_policy(self):
        original = dict(self.original)
        assets = T.java_assets()
        candidate = T.candidates(original, self.candidate_apk.read_bytes(), assets)

        expected_ril = original[T.RIL].replace(
            T.RIL_ANCHOR, T.RIL_ANCHOR[:-6] + T.RIL_HOOK + b"    }\n", 1)
        self.assertEqual(candidate[T.RIL], expected_ril)
        self.assertEqual(candidate[T.RIL].count(T.RIL_HOOK), 1)
        self.assertLess(candidate[T.RIL].index(b"Radio HAL version"),
                        candidate[T.RIL].index(T.RIL_HOOK))

        self.assertEqual(candidate[T.DPM], original[T.DPM].replace(
            T.DPM_ANCHOR, T.DPM_HOOK + T.DPM_ANCHOR, 1))
        self.assertLess(candidate[T.DPM].index(b"changedOnly();\n    }\n"),
                        candidate[T.DPM].index(T.DPM_HOOK))
        self.assertLess(candidate[T.DPM].index(T.DPM_HOOK),
                        candidate[T.DPM].index(T.DPM_ANCHOR))

        self.assertEqual(candidate[T.PROP].count((T.FLAG + "=true").encode()), 1)
        self.assertNotIn((T.FLAG + "=false").encode(), candidate[T.PROP])
        self.assertIn(b"system_internal_prop(m11q_seh_trial_prop)",
                      candidate[T.POLICY + "property.te"])
        self.assertIn((T.FLAG + " u:object_r:m11q_seh_trial_prop:s0 exact bool").encode(),
                      candidate[T.POLICY + "property_contexts"])
        radio = candidate[T.POLICY + "radio.te"]
        self.assertIn(b"get_prop(radio, m11q_seh_trial_prop)", radio)
        for broadening in (b"set_prop", b"default_prop", b"hal_", b"allow radio"):
            self.assertNotIn(broadening, radio)
        self.assertEqual(candidate[T.IMS], self.candidate_apk.read_bytes())
        self.assertEqual(set(candidate), set(self.original) | set(assets))

    def test_candidates_refuse_missing_duplicate_or_preexisting_hooks(self):
        for relative, anchor, hook in ((T.RIL, T.RIL_ANCHOR, T.RIL_HOOK),
                                      (T.DPM, T.DPM_ANCHOR, T.DPM_HOOK)):
            for bad in (self.original[relative].replace(anchor, b"", 1),
                        self.original[relative] + anchor,
                        self.original[relative] + hook):
                with self.subTest(relative=relative, bad=bad[-20:]):
                    original = dict(self.original)
                    original[relative] = bad
                    with self.assertRaisesRegex(ValueError, "source hook anchor drift"):
                        T.candidates(original, self.candidate_apk.read_bytes(), T.java_assets())

    def test_prepare_is_read_only_apply_and_rollback_are_idempotent(self):
        before = self.snapshot()
        prepared = self.prepare()
        self.assertEqual(prepared["source_state"], "original")
        self.assertEqual(self.snapshot(), before)

        applied = T.change(self.android, self.state)
        self.assertTrue(applied["source_changed"])
        self.assertEqual(applied["source_state"], "candidate")
        self.assertFalse(T.change(self.android, self.state)["source_changed"])
        for name in self.assets:
            self.assertTrue((self.android / (T.JAVA_PREFIX + name)).is_file())

        rolled = T.change(self.android, self.state, rollback=True)
        self.assertTrue(rolled["source_changed"])
        self.assertEqual(self.snapshot(), before)
        for name in self.assets:
            self.assertFalse((self.android / (T.JAVA_PREFIX + name)).exists())
        self.assertFalse(T.change(self.android, self.state, rollback=True)["source_changed"])

    def test_known_partial_new_file_state_recovers_and_concurrent_creation_is_refused(self):
        self.prepare()
        _, candidate = T.bundle(self.android, self.state)
        new_relative = T.JAVA_PREFIX + next(iter(self.assets))
        self.write(self.android, new_relative, candidate[new_relative])
        self.assertEqual(T.change(self.android, self.state)["source_state"], "candidate")
        T.change(self.android, self.state, rollback=True)
        self.assertFalse((self.android / new_relative).exists())

        target = self.android / new_relative
        original_link = T.os.link
        def race(source, destination):
            Path(destination).write_bytes(b"concurrent owner")
            return original_link(source, destination)
        with mock.patch.object(T.os, "link", side_effect=race):
            with self.assertRaises(FileExistsError):
                T.change(self.android, self.state)
        self.assertEqual(target.read_bytes(), b"concurrent owner")

    def test_refresh_assets_keeps_original_rollback(self):
        self.prepare()
        T.change(self.android, self.state)
        name = "M11SehApnPolicy.java"
        changed = self.assets[name] + b"all carriers\n"
        self.write(self.repo, "platform/java/com/android/internal/telephony/" + name, changed)
        pins = json.loads(self.pins_path.read_text())
        pins["java_sources"][name] = sha(changed)
        self.pins_path.write_text(json.dumps(pins))
        history = self.sandbox / "revision"
        result = T.refresh_assets(self.android, self.state, history)
        self.assertEqual(result["carrier_scope"], "all")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual((history / "candidate" / (T.JAVA_PREFIX + name)).read_bytes(), self.assets[name])
        self.assertEqual((self.android / (T.JAVA_PREFIX + name)).read_bytes(), changed)
        T.change(self.android, self.state, rollback=True)
        self.assertEqual(self.snapshot(), self.original)

    def test_refresh_migrates_legacy_comment(self):
        self.prepare()
        T.change(self.android, self.state)
        legacy_prop = (self.state / "candidate" / T.PROP).read_bytes().replace(
                b"slot0, all operators", b"slot0/TWM only")
        self.write(self.state, "candidate/" + T.PROP, legacy_prop)
        self.write(self.android, T.PROP, legacy_prop)
        manifest_path = self.state / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest.pop("carrier_scope")
        manifest["files"][T.PROP]["candidate_sha256"] = sha(legacy_prop)
        manifest_path.write_text(json.dumps(manifest))
        result = T.refresh_assets(self.android, self.state, self.sandbox / "revision")
        self.assertEqual(result["status"], "PASS")
        self.assertIn(b"all operators", (self.android / T.PROP).read_bytes())
        self.assertIn(b"slot0/TWM only", (self.sandbox / "revision/candidate" / T.PROP).read_bytes())

    def test_refresh_refuses_live_drift_before_backup(self):
        self.prepare()
        T.change(self.android, self.state)
        self.write(self.android, T.RIL, b"later edit")
        history = self.sandbox / "revision"
        with self.assertRaisesRegex(ValueError, "live source drift"):
            T.refresh_assets(self.android, self.state, history)
        self.assertFalse(history.exists())

    def test_hash_guards_refuse_dirty_prerequisite_and_unrelated_managed_edit(self):
        self.write(self.android, T.RIL, self.original[T.RIL] + b"// local edit\n")
        with self.assertRaisesRegex(ValueError, "unrecognized source input"):
            self.prepare()
        self.assertFalse(self.state.exists())
        self.write(self.android, T.RIL, self.original[T.RIL])
        self.prepare()

        self.write(self.android, T.DPM, b"unrelated dirty source")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "unrelated source edit refused"):
            T.change(self.android, self.state)
        self.assertEqual(self.snapshot(), before)
        self.write(self.android, T.DPM, self.original[T.DPM])

        prerequisite = next(name for name in self.prerequisite_data if name != T.IMS)
        self.write(self.android, prerequisite, b"drift")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "legacy prerequisite drift"):
            T.change(self.android, self.state)
        self.assertEqual(self.snapshot(), before)

    def test_concurrent_second_read_refusal_does_not_advance_to_other_targets(self):
        self.prepare()
        first = self.android / T.RIL
        first.write_bytes(self.original[T.RIL])
        called = []
        def concurrent(path, old, new):
            called.append(path)
            path.write_bytes(b"concurrent edit")
            raise ValueError("concurrent edit refused: fixture")
        with mock.patch.object(T.LEG1, "atomic_replace", side_effect=concurrent):
            with self.assertRaisesRegex(ValueError, "concurrent edit refused"):
                T.change(self.android, self.state)
        self.assertEqual(called, [first])
        self.assertEqual((self.android / T.DPM).read_bytes(), self.original[T.DPM])

    def test_atomic_failure_rolls_back_every_completed_replacement(self):
        self.prepare()
        before = self.snapshot()
        real = T.LEG1.atomic_replace
        calls = 0
        def fail_second(path, old, new):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated atomic failure")
            return real(path, old, new)
        with mock.patch.object(T.LEG1, "atomic_replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "simulated atomic failure"):
                T.change(self.android, self.state)
        self.assertEqual(self.snapshot(), before)
        for name in self.assets:
            self.assertFalse((self.android / (T.JAVA_PREFIX + name)).exists())

    def test_java_pin_and_private_manifest_tampering_are_refused(self):
        pins = json.loads(self.pins_path.read_text())
        cases = []
        wrong_identity = dict(pins)
        wrong_identity["transformation_id"] = "other"
        cases.append(wrong_identity)
        missing = json.loads(json.dumps(pins))
        missing["java_sources"].pop(next(iter(missing["java_sources"])))
        cases.append(missing)
        wrong_hash = json.loads(json.dumps(pins))
        wrong_hash["java_sources"][next(iter(wrong_hash["java_sources"]))] = "0" * 64
        cases.append(wrong_hash)
        for value in cases:
            with self.subTest(value=value):
                self.pins_path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    T.java_assets()
        self.pins_path.write_text(json.dumps(pins))

        self.prepare()
        manifest_path = self.state / "manifest.json"
        pristine = manifest_path.read_text()
        manifest = json.loads(pristine)
        manifest["files"][T.RIL]["candidate_sha256"] = "f" * 64
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "hash drift"):
            T.bundle(self.android, self.state)
        manifest_path.write_text(pristine)
        manifest = json.loads(pristine)
        manifest["files"]["unexpected"] = {"original_sha256": None,
                                               "candidate_sha256": "0" * 64}
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "manifest drift"):
            T.bundle(self.android, self.state)

    def test_prepare_rejects_existing_state_and_tampered_lg3_report(self):
        self.state.mkdir()
        with self.assertRaisesRegex(ValueError, "state already exists"):
            self.prepare()
        self.state.rmdir()
        evidence = json.loads(self.report.read_text())
        evidence["output"]["unrelated_zip_entries_preserved"] = False
        self.report.write_text(json.dumps(evidence))
        with self.assertRaisesRegex(ValueError, "complete strict LG3"):
            self.prepare()
        self.assertFalse(self.state.exists())

    def make_product(self, flag="true"):
        product = self.sandbox / ("product-" + flag)
        props = (f"{T.LEG1.MODE}=legacy\n{T.LEG1.LABEL}=legacy-r1\n{T.FLAG}={flag}\n").encode()
        self.write(product, "system/build.prop", props)
        overlay = product / "vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk"
        overlay.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(overlay, "w") as archive:
            archive.writestr("res/xml/vendor.xml", b"\x03\x00compiled fixture")
        self.write(product, "system/system_ext/priv-app/imsservice/imsservice.apk", b"ims")
        self.write(product, "system/system_ext/priv-app/EpdgService/EpdgService.apk", b"epdg")
        self.write(product, "system/framework/framework.jar", b"framework")
        jar = product / "system/framework/telephony-common.jar"
        jar.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(jar, "w") as archive:
            archive.writestr("classes.dex", b"dex fixture")
        return product

    @staticmethod
    def tree_snapshot(root):
        return {str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def test_product_property_mismatch_and_missing_compiled_classes_are_read_only(self):
        bad_property = self.make_product("false")
        before = self.tree_snapshot(bad_property)
        with self.assertRaisesRegex(ValueError, "packaged trial properties mismatch"):
            T.verify_product(bad_property)
        self.assertEqual(self.tree_snapshot(bad_property), before)

        product = self.make_product("true")
        before = self.tree_snapshot(product)
        with self.assertRaisesRegex(ValueError, "packaged SEH1 defined method missing"):
            T.verify_product(product)
        self.assertEqual(self.tree_snapshot(product), before)


if __name__ == "__main__":
    unittest.main()
