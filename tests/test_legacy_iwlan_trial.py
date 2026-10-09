import hashlib
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import legacy_iwlan_trial as T


def digest(data):
    return hashlib.sha256(data).hexdigest()


def chunk(kind, header, body):
    size = 8 + len(body)
    return struct.pack("<HHI", kind, header, size) + body


def binary_vendor(encoding="utf8", enabled=False, integer_mnc=False):
    """Construct a small Android binary XML carrier_config tree."""
    values = ["carrier_config_list", "carrier_config", "mcc", "466", "mnc",
              "01", "05", "92", "97", "boolean", "name", "value",
              T.KEY, "carrier_wfc_ims_available_bool", "true", "false"]
    if encoding == "utf8":
        encoded = []
        for value in values:
            raw = value.encode("utf-8")
            encoded.append(bytes((len(value), len(raw))) + raw + b"\0")
        flags = 0x100
    else:
        encoded = []
        for value in values:
            raw = value.encode("utf-16-le")
            encoded.append(struct.pack("<H", len(value)) + raw + b"\0\0")
        flags = 0
    offsets, pool_data = [], b""
    for item in encoded:
        offsets.append(len(pool_data))
        pool_data += item
    pool_header = 28
    pool = (struct.pack("<IIIII", len(values), 0, flags,
                        pool_header + 4 * len(values), 0) +
            b"".join(struct.pack("<I", off) for off in offsets) + pool_data)
    pool_chunk = chunk(1, pool_header, pool)

    def start(name, attrs=()):
        attr_start, attr_size = 20, 20
        body = (struct.pack("<II", 1, 0xffffffff) +
                struct.pack("<IIHHHHHH", 0xffffffff, name, attr_start, attr_size,
                            len(attrs), 0, 0, 0))
        for attr_name, raw_index, value_type, value in attrs:
            body += struct.pack("<IIIHBBI", 0xffffffff, attr_name, raw_index,
                                8, 0, value_type, value)
        return chunk(0x102, 16, body)

    def end(name):
        return chunk(0x103, 16, struct.pack("<IIII", 1, 0xffffffff, 0xffffffff, name))

    # Attribute strings use raw string indices. Boolean value below uses typed bool.
    def carrier(mnc_index, with_trial=False):
        mnc_attr = ((4, 0xffffffff, 0x10, int(values[mnc_index]))
                    if integer_mnc else (4, mnc_index, 3, mnc_index))
        parts = [start(1, ((2, 3, 3, 3), mnc_attr))]
        parts.append(start(9, ((10, 13, 3, 13), (11, 14, 3, 14))))
        parts.append(end(9))
        if with_trial:
            parts.append(start(9, ((10, 12, 3, 12),
                                   (11, 0xffffffff, 0x12, int(enabled)))))
            parts.append(end(9))
        parts.append(end(1))
        return b"".join(parts)

    body = (pool_chunk + start(0) + carrier(5) + carrier(6) + carrier(7) +
            carrier(8, with_trial=True) + end(0))
    return struct.pack("<HHI", 3, 8, 8 + len(body)) + body


class LegacyIwlanTrialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.android = self.root / "android"
        self.state = self.root / "state"
        self.original = {
            T.PROP: b"ro.product.device=m11q\n",
            T.VENDOR: (b"<carrier_config_list>\n" +
                       b'<carrier_config mcc="466" mnc="01"><boolean name="carrier_wfc_ims_available_bool" value="true"/></carrier_config>\n' +
                       b'<carrier_config mcc="466" mnc="05"><boolean name="carrier_wfc_ims_available_bool" value="true"/></carrier_config>\n' +
                       b'<carrier_config mcc="466" mnc="92"><boolean name="carrier_wfc_ims_available_bool" value="true"/></carrier_config>\n' +
                       b'<!-- Experimental: preserve an established ordinary IMS voice call on\n             W2L. Idle transitions retain the fresh-bearer policy below. -->\n' +
                       f'<carrier_config mcc="466" mnc="97"><boolean name="carrier_wfc_ims_available_bool" value="true"/><boolean name="{T.KEY}" value="true"/></carrier_config>\n'.encode() +
                       b"</carrier_config_list>\n"),
        }
        self.prerequisites = {
            "frameworks/opt/telephony/src/java/com/android/internal/telephony/data/AccessNetworksManager.java": b"access",
            "frameworks/opt/telephony/src/java/com/android/internal/telephony/data/DataNetworkController.java": b"data",
            "device/samsung/m11q/ims/proprietary/priv-app/EpdgService/EpdgService.apk": b"epdg",
            "device/samsung/m11q/ims/proprietary/priv-app/imsservice/imsservice.apk": b"ims",
        }
        self.android.mkdir()
        self.write_android_files()
        self.patcher = mock.patch.multiple(
            T, ORIGINAL={p: digest(b) for p, b in self.original.items()},
            PREREQUISITES={p: digest(b) for p, b in self.prerequisites.items()})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, root, relative, data):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_android_files(self):
        for relative, data in self.original.items():
            self.write(self.android, relative, data)
        for relative, data in self.prerequisites.items():
            self.write(self.android, relative, data)

    def prepared(self):
        T.prepare(self.android, self.state)
        return T.bundle(self.state)

    def test_prepare_is_read_only_and_apply_rollback_are_guarded_and_idempotent(self):
        before = {r: (self.android / r).read_bytes() for r in T.ORIGINAL}
        T.prepare(self.android, self.state)
        self.assertEqual(before, {r: (self.android / r).read_bytes() for r in T.ORIGINAL})
        self.assertEqual(T.verify_source(self.android, self.state, expected="original")["source_state"], "original-ap-assisted")
        original, candidate = T.bundle(self.state)
        prop = self.android / T.PROP
        vendor = self.android / T.VENDOR
        os.chmod(prop, 0o640)
        os.chmod(vendor, 0o600)
        prop_times = (prop.stat().st_atime_ns, prop.stat().st_mtime_ns)
        vendor_times = (vendor.stat().st_atime_ns, vendor.stat().st_mtime_ns)
        applied = T.change(self.android, self.state)
        self.assertEqual(applied["source_state"], "legacy-r1")
        self.assertIn(b"ro.telephony.iwlan_operation_mode=legacy\n", prop.read_bytes())
        self.assertIn(b"ro.m11q.ims_trial=legacy-r1\n", prop.read_bytes())
        self.assertIn(b'value="false"', vendor.read_bytes())
        self.assertEqual(stat_mode(prop), 0o640)
        self.assertEqual(stat_mode(vendor), 0o600)
        self.assertGreater(prop.stat().st_mtime_ns, prop_times[1])
        self.assertGreater(vendor.stat().st_mtime_ns, vendor_times[1])
        self.assertFalse(T.change(self.android, self.state)["configuration_changed"])
        rolled = T.change(self.android, self.state, rollback=True)
        self.assertEqual(rolled["source_state"], "original-ap-assisted")
        self.assertEqual({r: (self.android / r).read_bytes() for r in original}, original)
        self.assertFalse(T.change(self.android, self.state, rollback=True)["configuration_changed"])

    def test_prepare_rejects_ineligible_source_without_writing_config(self):
        self.write(self.android, "device/samsung/m11q/system.prop", self.original[T.PROP] + b"ro.telephony.iwlan_operation_mode=other\n")
        T.ORIGINAL[T.PROP] = digest((self.android / T.PROP).read_bytes())
        T.ORIGINAL[T.VENDOR] = digest(self.original[T.VENDOR])
        with self.assertRaises(ValueError):
            T.prepare(self.android, self.state)
        self.assertFalse(self.state.exists())

    def test_apply_refuses_mixed_unknown_or_changed_prerequisite_without_writes(self):
        original, candidate = self.prepared()
        self.write(self.android, T.PROP, candidate[T.PROP])
        self.write(self.android, T.VENDOR, b"user edit\n")
        with self.assertRaisesRegex(ValueError, "unrelated edit"):
            T.change(self.android, self.state)
        self.assertEqual((self.android / T.PROP).read_bytes(), candidate[T.PROP])
        self.assertEqual((self.android / T.VENDOR).read_bytes(), b"user edit\n")
        self.write(self.android, T.VENDOR, original[T.VENDOR])
        rel = next(iter(self.prerequisites))
        self.write(self.android, rel, b"changed prerequisite")
        before = {r: (self.android / r).read_bytes() for r in T.ORIGINAL}
        with self.assertRaisesRegex(ValueError, "prerequisite drift"):
            T.change(self.android, self.state)
        self.assertEqual(before, {r: (self.android / r).read_bytes() for r in T.ORIGINAL})

    def test_prepare_existing_state_recovers_mixed_known_apply_state(self):
        original, candidate = self.prepared()
        self.write(self.android, T.PROP, candidate[T.PROP])
        self.assertEqual(T.change(self.android, self.state)["source_state"], "legacy-r1")
        self.assertEqual((self.android / T.VENDOR).read_bytes(), candidate[T.VENDOR])
        self.assertEqual(T.change(self.android, self.state)["source_state"], "legacy-r1")

    def test_candidate_and_prerequisite_drift_are_refused(self):
        self.prepared()
        backup = self.state / ("backup-" + Path(T.PROP).name)
        backup.write_bytes(b"altered original")
        with self.assertRaisesRegex(ValueError, "backup drift"):
            T.bundle(self.state)
        backup.write_bytes(self.original[T.PROP])
        candidate = self.state / ("candidate-" + Path(T.PROP).name)
        candidate.write_bytes(b"altered candidate")
        with self.assertRaisesRegex(ValueError, "candidate drift"):
            T.bundle(self.state)

    def test_symlink_target_is_rejected(self):
        self.prepared()
        path = self.android / T.PROP
        real = self.root / "real.prop"
        real.write_bytes(path.read_bytes())
        path.unlink()
        try:
            path.symlink_to(real)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "symlink refused"):
            T.change(self.android, self.state)

    def test_second_atomic_replacement_failure_restores_first_target(self):
        original, candidate = self.prepared()
        real_replace = T.os.replace
        calls = 0
        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second replace failure")
            return real_replace(source, destination)
        with mock.patch.object(T.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "simulated"):
                T.change(self.android, self.state)
        self.assertEqual({r: (self.android / r).read_bytes() for r in original}, original)

    def make_product(self, mode=b"legacy", label=b"legacy-r1", duplicate=False):
        product = self.root / "product"
        props = b"ro.telephony.iwlan_operation_mode=" + mode + b"\nro.m11q.ims_trial=" + label + b"\n"
        if duplicate:
            props += b"ro.telephony.iwlan_operation_mode=false\n"
        self.write(product, "system/build.prop", props)
        self.write(product, "vendor/build.prop", b"# no duplicate\n")
        overlay = product / "vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk"
        overlay.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(overlay, "w") as archive:
            archive.writestr("res/xml/vendor.xml", binary_vendor("utf8"))
        return product

    def test_product_requires_unique_correct_boot_properties_and_disabled_overlay(self):
        for kwargs in ({"mode": b"", "label": b"legacy-r1"},
                       {"mode": b"legacy", "label": b"legacy-r1", "duplicate": True}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, "packaged boot properties"):
                    T.verify_product(self.make_product(**kwargs))
        product = self.make_product()
        self.write(product, "vendor/build.prop", b"ro.telephony."
                   b"iwlan_operation_mode=other\n")
        with self.assertRaisesRegex(ValueError, "packaged boot properties"):
            T.verify_product(product)

    def test_product_overlay_requires_false_and_source_prerequisite_gates(self):
        product = self.make_product()
        overlay = product / "vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk"
        with zipfile.ZipFile(overlay, "w") as archive:
            archive.writestr("res/xml/vendor.xml", binary_vendor("utf8", enabled=True))
        with self.assertRaisesRegex(ValueError, "explicitly disabled"):
            T.verify_product(product)
        with zipfile.ZipFile(overlay, "w") as archive:
            archive.writestr("res/xml/vendor.xml", binary_vendor("utf8"))
        combined = mock.Mock()
        pins = {"fixture": "pinned"}
        builder = mock.Mock(DEFAULT_PINS=pins)
        framework = mock.Mock()
        framework.verify_framework.return_value = {
            "service_state_legacy_abi_verified": True, "framework_sha256": "fixture"}
        with mock.patch.dict(sys.modules, {
                "verify_ims_w2l_trial_artifacts": combined,
                "build_imsservice_w2l_trial": builder,
                "legacy_service_state_compat": framework}):
            # Product verification reaches both APK gates and returns PASS.
            with mock.patch.object(T, "zipfile") as unused:
                unused.ZipFile = zipfile.ZipFile
                result = T.verify_product(product)
        self.assertEqual(result["status"], "PASS")
        combined.verify.assert_called_once_with(
            product / "system/system_ext/priv-app/EpdgService/EpdgService.apk",
            product / "system/system_ext/priv-app/imsservice/imsservice.apk", pins,
            epdg_prefix_pins=ROOT / "devices/m11q/legacy-epdg-prefix-build.json")
        framework.verify_framework.assert_called_once_with(product / "system/framework/framework.jar")
        self.assertTrue(result["service_state_legacy_abi_verified"])

    def test_product_missing_framework_abi_cannot_pass(self):
        product = self.make_product()
        framework = mock.Mock()
        framework.verify_framework.side_effect = ValueError("packaged legacy framework ABI missing")
        with mock.patch.dict(sys.modules, {
                "verify_ims_w2l_trial_artifacts": mock.Mock(),
                "build_imsservice_w2l_trial": mock.Mock(DEFAULT_PINS={}),
                "legacy_service_state_compat": framework}):
            with self.assertRaisesRegex(ValueError, "framework ABI missing"):
                T.verify_product(product)

    def test_optional_real_compiled_overlay_parser_check(self):
        overlay = os.environ.get("LEG1_OVERLAY_APK")
        if not overlay:
            self.skipTest("set LEG1_OVERLAY_APK to an aapt-built CarrierConfig overlay APK")
        with zipfile.ZipFile(overlay) as archive:
            xml = archive.read("res/xml/vendor.xml")
        tree = T.binary_xml(xml)
        self.assertEqual(tree.tag, "carrier_config_list")
        carrier = [c for c in tree.findall("carrier_config")
                   if c.get("mcc") == "466" and c.get("mnc") == "97"]
        self.assertEqual(len(carrier), 1)
        flags = [e for e in carrier[0].findall("boolean") if e.get("name") == T.KEY]
        self.assertEqual(len(flags), 1)
        # Support both the previous AP-assisted output and a future LEG1 build.
        self.assertIn(flags[0].get("value"), ("true", "false"))
        if flags[0].get("value") == "true":
            with self.assertRaisesRegex(ValueError, "explicitly disabled"):
                T.validate_vendor(tree)
        else:
            T.validate_vendor(tree)

    def test_product_refuses_plain_xml_duplicate_entry_and_bad_apk(self):
        product = self.make_product()
        overlay = product / "vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk"
        with zipfile.ZipFile(overlay, "w") as archive:
            archive.writestr("res/xml/vendor.xml", self.original[T.VENDOR])
        with self.assertRaisesRegex(ValueError, "compiled Android XML"):
            T.verify_product(product)
        with zipfile.ZipFile(overlay, "w") as archive:
            archive.writestr("res/xml/vendor.xml", binary_vendor())
            with self.assertWarns(UserWarning):
                archive.writestr("res/xml/vendor.xml", binary_vendor())
        with self.assertRaisesRegex(ValueError, "missing/duplicate"):
            T.verify_product(product)
        with zipfile.ZipFile(overlay, "w") as archive:
            archive.writestr("res/xml/vendor.xml", binary_vendor())
        combined = mock.Mock()
        combined.verify.side_effect = ValueError("APK identity mismatch")
        with mock.patch.dict(sys.modules, {
                "verify_ims_w2l_trial_artifacts": combined,
                "build_imsservice_w2l_trial": mock.Mock(DEFAULT_PINS={})}):
            with self.assertRaisesRegex(ValueError, "APK identity mismatch"):
                T.verify_product(product)

    def test_binary_xml_utf8_utf16_boolean_and_malformed_documents(self):
        for encoding in ("utf8", "utf16"):
            with self.subTest(encoding=encoding):
                tree = T.binary_xml(binary_vendor(encoding))
                T.validate_vendor(tree)
                integer_tree = T.binary_xml(binary_vendor(encoding, integer_mnc=True))
                self.assertEqual(integer_tree.findall("carrier_config")[0].get("mnc"), "1")
                T.validate_vendor(integer_tree)
                enabled = T.binary_xml(binary_vendor(encoding, enabled=True))
                with self.assertRaisesRegex(ValueError, "explicitly disabled"):
                    T.validate_vendor(enabled)
        valid = binary_vendor()
        invalids = (b"not xml", valid[:-1],
                    valid[:8] + struct.pack("<HHI", 1, 28, len(valid)) + valid[16:],
                    valid[:-24])
        for data in invalids:
            with self.subTest(data=data[:12]), self.assertRaises((ValueError, IndexError, struct.error)):
                T.binary_xml(data)

    def test_mnc_normalization_preserves_missing_false_and_duplicate_rejections(self):
        tree = T.binary_xml(binary_vendor(integer_mnc=True))
        first = tree.findall("carrier_config")[0]
        first.set("mnc", "001")
        with self.assertRaisesRegex(ValueError, "46601"):
            T.validate_vendor(tree)
        first.set("mnc", "1")
        first.find("boolean").set("value", "false")
        with self.assertRaisesRegex(ValueError, "46601"):
            T.validate_vendor(tree)
        first.find("boolean").set("value", "true")
        import copy
        duplicate = copy.deepcopy(first)
        duplicate.set("mnc", "01")
        tree.append(duplicate)
        with self.assertRaisesRegex(ValueError, "46601"):
            T.validate_vendor(tree)


def stat_mode(path):
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
