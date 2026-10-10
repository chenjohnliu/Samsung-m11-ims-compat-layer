import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import legacy_seh_apn_trial as T
from test_legacy_service_state_compat import synthetic_dex


class SehPackagedAbiTests(unittest.TestCase):
    def dex(self, owner, signature, static=True, **options):
        with mock.patch.object(T.SS1, "OWNER", owner), mock.patch.object(
                T.SS1, "REQUIRED", {signature: static}):
            return synthetic_dex(**options)

    def test_owner_parameter_requires_definition_not_reference(self):
        owner = "Lcom/android/internal/telephony/M11SehRadioBridge;"
        method = "maybeStart(Lcom/android/internal/telephony/RIL;Landroid/content/Context;I)V"
        data = self.dex(owner, method)
        self.assertEqual(T.SS1.dex_definitions(data), [])
        definitions = T.SS1.dex_definitions(data, owner)
        self.assertEqual(len(definitions), 1)
        self.assertIn(method, definitions[0])
        self.assertTrue(definitions[0][method][0] & 8)
        absent = self.dex(owner, method, omit=(method,))
        self.assertNotIn(method, T.SS1.dex_definitions(absent, owner)[0])

    def test_product_gate_accepts_defined_entry_points_and_rejects_wrong_staticness(self):
        entries = {
            "M11SehRadioBridge": "maybeStart(Lcom/android/internal/telephony/RIL;Landroid/content/Context;I)V",
            "M11SehProfilePublisher": "publish(Lcom/android/internal/telephony/Phone;Ljava/util/List;)V",
            "M11SehRadioTransport": "register(Landroid/os/IHwBinder;)V",
            "M11SehApnPolicy": "fallback(Lcom/android/internal/telephony/M11SehApnPolicy$Snapshot;IILjava/lang/String;Ljava/lang/String;Z)Lcom/android/internal/telephony/M11SehApnPolicy$Profile;",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "system/framework").mkdir(parents=True)
            (root / "system/build.prop").write_text(
                T.LEG1.MODE + "=legacy\n" + T.LEG1.LABEL + "=legacy-r1\n" + T.FLAG + "=true\n")
            overlay = root / "vendor/overlay/CarrierConfig__auto_generated_rro_vendor.apk"
            overlay.parent.mkdir(parents=True)
            with zipfile.ZipFile(overlay, "w") as archive:
                archive.writestr("res/xml/vendor.xml", b"\x03compiled")
            jar = root / "system/framework/telephony-common.jar"

            def write_jar(wrong=False):
                with zipfile.ZipFile(jar, "w") as archive:
                    for index, (name, signature) in enumerate(entries.items(), 1):
                        kwargs = {"method_flags": {signature: 1}} if wrong and index == 1 else {}
                        data = self.dex("Lcom/android/internal/telephony/" + name + ";",
                            signature, name != "M11SehRadioTransport", **kwargs)
                        if name == "M11SehApnPolicy":
                            with mock.patch.object(T.SS1, "OWNER", "Lcom/android/internal/telephony/M11SehApnPolicy;"), mock.patch.object(
                                    T.SS1, "REQUIRED", {signature: True, "validOperator(Ljava/lang/String;)Z": True,
                                                        "supportedPhone(I)Z": True}):
                                data = synthetic_dex()
                        if name == "M11SehRadioBridge":
                            with mock.patch.object(T.SS1, "OWNER", "Lcom/android/internal/telephony/M11SehRadioBridge;"), mock.patch.object(
                                    T.SS1, "REQUIRED", {signature: True, "isEnabledForPhone(I)Z": True}):
                                data = synthetic_dex(**kwargs)
                        archive.writestr("classes" + ("" if index == 1 else str(index)) + ".dex", data)

            write_jar()
            with mock.patch.object(T.LEG1, "binary_xml", return_value=None), mock.patch.object(
                    T.LEG1, "validate_vendor"), mock.patch.object(T.LG3, "verify_apk"), mock.patch.object(
                    T.LG2, "verify_apk"), mock.patch.object(T.SS1, "verify_framework"):
                self.assertEqual(T.verify_product(root)["status"], "PASS")
                write_jar(wrong=True)
                with self.assertRaisesRegex(ValueError, "entry point invalid"):
                    T.verify_product(root)


if __name__ == "__main__":
    unittest.main()
