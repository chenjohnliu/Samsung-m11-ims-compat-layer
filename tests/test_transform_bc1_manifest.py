import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOL = Path(__file__).parents[1] / "tools" / "transform_bc1_manifest.py"
CONTRACT = Path(__file__).parents[1] / "devices" / "m11q" / "bc1-manifest-contract.json"
SPEC = importlib.util.spec_from_file_location("transform_bc1_manifest", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

ANDROID = "http://schemas.android.com/apk/res/android"
SERVICE = "com.sec.internal.google.GoogleModernImsService"


def manifest(body='<application android:label="Synthetic"/>', package="com.sec.imsservice",
             namespace=True):
    ns = f' xmlns:android="{ANDROID}"' if namespace else ""
    android_attribute = ' android:versionCode="1"' if namespace else ""
    return f'<?xml version="1.0" encoding="utf-8"?><manifest{ns}{android_attribute} package="{package}">{body}</manifest>'


class TransformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "AndroidManifest.xml"
        self.output = self.base / "AndroidManifest.bc1.xml"
        self.source.write_text(manifest(), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_transform(self, allow_identical=False):
        return MODULE.transform(CONTRACT, self.source, self.output, allow_identical)

    def test_pass_has_exact_project_authored_semantics(self):
        result = self.run_transform()
        self.assertTrue(result["changed"])
        tree = MODULE._parse_xml(self.output.read_bytes())
        root = tree.getroot()
        ns = lambda local: f"{{{ANDROID}}}{local}"
        services = [x for x in root.iter("service") if x.get(ns("name")) == SERVICE]
        self.assertEqual(len(services), 1)
        service = services[0]
        self.assertEqual(service.attrib, {
            ns("name"): SERVICE,
            ns("permission"): "android.permission.BIND_IMS_SERVICE",
            ns("enabled"): "true",
            ns("exported"): "true",
            ns("singleUser"): "true",
        })
        self.assertEqual([x.get(ns("name")) for x in service.iter("action")],
                         ["android.telephony.ims.ImsService"])
        self.assertEqual([(x.get(ns("name")), x.get(ns("value")))
                          for x in service.iter("meta-data")],
                         [("android.telephony.ims.MMTEL_FEATURE", "true")])
        text = self.output.read_text(encoding="utf-8")
        self.assertNotIn("EMERGENCY_MMTEL_FEATURE", text)
        self.assertNotIn("RCS_FEATURE", text)

    def test_package_drift_fails_without_output(self):
        self.source.write_text(manifest(package="example.drift"), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "package drift"):
            self.run_transform()
        self.assertFalse(self.output.exists())

    def test_duplicate_or_missing_application_fails(self):
        for body in ("", "<application android:label=\"a\"/><application android:label=\"b\"/>"):
            with self.subTest(body=body):
                self.source.write_text(manifest(body), encoding="utf-8")
                with self.assertRaisesRegex(MODULE.TransformError, "exactly one application"):
                    self.run_transform()
                self.assertFalse(self.output.exists())

    def test_existing_target_service_even_duplicate_fails(self):
        declaration = f'<service android:name="{SERVICE}"/>'
        for declarations in (declaration, declaration + declaration):
            with self.subTest(count=declarations.count("service")):
                self.source.write_text(manifest(f"<application>{declarations}</application>"),
                                       encoding="utf-8")
                with self.assertRaisesRegex(MODULE.TransformError, "target service already exists"):
                    self.run_transform()
                self.assertFalse(self.output.exists())

    def test_existing_target_action_even_outside_target_service_fails(self):
        action = '<action android:name="android.telephony.ims.ImsService"/>'
        body = f'<application><service android:name="example.Other"><intent-filter>{action}{action}</intent-filter></service></application>'
        self.source.write_text(manifest(body), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "target action already exists"):
            self.run_transform()

    def test_existing_target_or_excluded_metadata_fails(self):
        for name in ("android.telephony.ims.MMTEL_FEATURE",
                     "android.telephony.ims.EMERGENCY_MMTEL_FEATURE",
                     "android.telephony.ims.RCS_FEATURE"):
            with self.subTest(name=name):
                body = f'<application><meta-data android:name="{name}" android:value="true"/><meta-data android:name="{name}" android:value="true"/></application>'
                self.source.write_text(manifest(body), encoding="utf-8")
                with self.assertRaisesRegex(MODULE.TransformError, "IMS metadata already exists"):
                    self.run_transform()
                self.assertFalse(self.output.exists())

    def test_absent_namespace_and_malformed_xml_fail(self):
        cases = (manifest("<application/>", namespace=False),
                 '<manifest xmlns:android="urn:wrong" android:versionCode="1" package="com.sec.imsservice"><application/></manifest>',
                 '<manifest xmlns:android="not-a-uri" package="com.sec.imsservice"><application>',
                 '<wrong xmlns:android="http://schemas.android.com/apk/res/android" android:x="1"/>')
        for content in cases:
            with self.subTest(content=content[:20]):
                self.source.write_text(content, encoding="utf-8")
                with self.assertRaises(MODULE.TransformError):
                    self.run_transform()
                self.assertFalse(self.output.exists())

    def test_non_overwrite_and_opt_in_identical_idempotence(self):
        self.run_transform()
        original = self.output.read_bytes()
        with self.assertRaisesRegex(MODULE.TransformError, "refusing to overwrite"):
            self.run_transform()
        result = self.run_transform(allow_identical=True)
        self.assertFalse(result["changed"])
        self.assertEqual(self.output.read_bytes(), original)
        self.output.write_text("conflict", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "refusing to overwrite"):
            self.run_transform(allow_identical=True)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "conflict")

    def test_same_path_symlink_and_missing_parent_rejected(self):
        with self.assertRaisesRegex(MODULE.TransformError, "different paths"):
            MODULE.transform(CONTRACT, self.source, self.source)
        with self.assertRaisesRegex(MODULE.TransformError, "output parent"):
            MODULE.transform(CONTRACT, self.source, self.base / "missing" / "out.xml")
        link = self.base / "link.xml"
        try:
            link.symlink_to(self.source)
        except OSError:
            return
        with self.assertRaisesRegex(MODULE.TransformError, "non-symlink"):
            MODULE.transform(CONTRACT, link, self.output)

    def test_atomic_publish_failure_leaves_no_output_or_temp(self):
        with mock.patch.object(MODULE.os, "link", side_effect=OSError("synthetic")):
            with self.assertRaisesRegex(OSError, "synthetic"):
                self.run_transform()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.base.glob(".AndroidManifest.bc1.xml.*.tmp")), [])

    def test_contract_is_strict_and_contains_no_stock_context(self):
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(raw["transformation_id"], "BC1-modern-mmtel-discovery")
        build = json.loads((Path(__file__).parents[1] / "devices/m11q/imsservice-build.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(build["transformation_contracts"][raw["transformation_id"]],
                         "devices/m11q/bc1-manifest-contract.json")
        contract_text = CONTRACT.read_text(encoding="utf-8")
        for forbidden in ("com.samsung", "sec_feature", "uses-library", "activity ",
                          "provider ", "receiver "):
            self.assertNotIn(forbidden, contract_text.lower())
        changed = json.loads(contract_text)
        changed["service"]["metadata"]["android.telephony.ims.EMERGENCY_MMTEL_FEATURE"] = True
        bad = self.base / "bad.json"
        bad.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "MMTEL_FEATURE=true only"):
            MODULE.load_contract(bad)


if __name__ == "__main__":
    unittest.main()
