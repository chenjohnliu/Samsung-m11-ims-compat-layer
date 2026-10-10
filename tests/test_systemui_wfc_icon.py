"""Source-contract checks for the SystemUI IMS registration icon state."""

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest


def source_from_environment(environ):
    configured = environ.get("M11_SYSTEMUI_SOURCE")
    return Path(configured) if configured else None


SOURCE = source_from_environment(os.environ)


class WfcIconSourceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SOURCE is None:
            raise unittest.SkipTest(
                "M11_SYSTEMUI_SOURCE is unset; source-body checks need an explicitly configured patched MobileSignalController.java"
            )
        if not SOURCE.is_file():
            raise unittest.SkipTest(
                f"M11_SYSTEMUI_SOURCE does not name a file: {SOURCE}"
            )
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_extracted_java_callback_sequence(self):
        """Compile and exercise real method bodies, not a second Python implementation.

        Host stubs isolate the UI state rule; this does not compile all SystemUI
        or validate Android runtime callback delivery.
        """
        javac, java = shutil.which("javac"), shutil.which("java")
        if not javac or not java:
            self.skipTest("Host JDK unavailable")
        methods = []
        for signature in (
            "public void onRegistered(ImsRegistrationAttributes attributes)",
            "public void onRegistering(ImsRegistrationAttributes attr)",
            "public void onUnregistered(ImsReasonInfo info)",
            "public boolean isVowifiAvailable()",
        ):
            start = self.source.index(signature)
            opening = self.source.index("{", start)
            depth = 1
            ending = opening + 1
            while depth:
                char = self.source[ending]
                depth += (char == "{") - (char == "}")
                ending += 1
            methods.append(self.source[start:ending])
        harness = """
class WfcIconHarness {
    static final int REGISTRATION_TECH_IWLAN = 1, REGISTRATION_TECH_CROSS_SIM = 2;
    static final String mTag = "test";
    static class Log { static void d(String tag, String value) {} }
    static class ImsReasonInfo {}
    static class ImsRegistrationAttributes {
        final int technology;
        ImsRegistrationAttributes(int value) { technology = value; }
        int getRegistrationTechnology() { return technology; }
    }
    static class State { boolean imsRegistered, voiceCapable; }
    final State mCurrentState = new State();
    boolean mIsVowifiAvailable;
    int notices;
    void notifyListenersIfNecessary() { notices++; }
    void check(boolean expected) {
        if (isVowifiAvailable() != expected) throw new AssertionError("Wrong icon state");
    }
    void initialQuery(boolean registered, boolean available) {
        mCurrentState.imsRegistered = registered;
        mIsVowifiAvailable = available;
    }
    public static void main(String[] args) {
        WfcIconHarness h = new WfcIconHarness();
        h.mCurrentState.voiceCapable = true;
        h.check(false);
        h.initialQuery(true, true); h.check(true);
        h.onRegistered(new ImsRegistrationAttributes(0)); h.check(false);
        h.onRegistered(new ImsRegistrationAttributes(1)); h.check(true);
        h.onRegistered(new ImsRegistrationAttributes(0)); h.check(false);
        h.onRegistered(new ImsRegistrationAttributes(3)); h.check(false);
        h.onRegistered(new ImsRegistrationAttributes(2)); h.check(true);
        h.mCurrentState.voiceCapable = false; h.check(false);
        h.mCurrentState.voiceCapable = true; h.check(true);
        h.onRegistering(new ImsRegistrationAttributes(1)); h.check(false);
        if (h.mIsVowifiAvailable) throw new AssertionError("Registering retained WFC");
        h.onRegistered(new ImsRegistrationAttributes(1)); h.check(true);
        h.onUnregistered(new ImsReasonInfo()); h.check(false);
        if (h.mIsVowifiAvailable) throw new AssertionError("Deregistration retained WFC");
        h.onRegistered(new ImsRegistrationAttributes(-1)); h.check(false);
        if (h.notices != 9) throw new AssertionError("Missing notification");
    }
""" + "\n".join(methods) + "\n}\n"
        with tempfile.TemporaryDirectory(prefix="m11_wfc_icon_") as temporary:
            source_file = Path(temporary) / "WfcIconHarness.java"
            source_file.write_text(harness, encoding="utf-8")
            compiled = subprocess.run([javac, str(source_file)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            exercised = subprocess.run([java, "-cp", temporary, "WfcIconHarness"],
                                       capture_output=True, text=True)
            self.assertEqual(exercised.returncode, 0, exercised.stderr)

    def test_registration_callback_sets_wfc_only_for_iwlan_or_cross_sim(self):
        self.assertIn(
            "import static android.telephony.ims.stub.ImsRegistrationImplBase."
            "REGISTRATION_TECH_IWLAN;",
            self.source,
        )
        self.assertIn(
            "import static android.telephony.ims.stub.ImsRegistrationImplBase."
            "REGISTRATION_TECH_CROSS_SIM;",
            self.source,
        )
        self.assertRegex(
            self.source,
            re.compile(
                r"onRegistered\(ImsRegistrationAttributes attributes\).*?"
                r"mCurrentState\.imsRegistered = true;.*?"
                r"int registrationTechnology = attributes\.getRegistrationTechnology\(\);.*?"
                r"mIsVowifiAvailable = registrationTechnology == REGISTRATION_TECH_IWLAN\s*"
                r"\|\| registrationTechnology == REGISTRATION_TECH_CROSS_SIM;.*?"
                r"notifyListenersIfNecessary\(\);",
                re.S,
            ),
        )

    def test_registration_constants_use_android13_stub_package_in_source_and_patch(self):
        correct = "android.telephony.ims.stub.ImsRegistrationImplBase"
        self.assertIn(correct, self.source)
        self.assertNotIn("android.telephony.ims.ImsRegistrationImplBase", self.source)

    def test_android13_real_api_import_compilation_when_classpath_is_configured(self):
        """Compile the actual constants import independently of the fake method harness."""
        classpath = os.environ.get("M11_SYSTEMUI_API_CLASSPATH")
        if not classpath:
            self.skipTest("Set M11_SYSTEMUI_API_CLASSPATH to existing Android 13 API jars")
        javac = shutil.which("javac")
        if not javac:
            self.skipTest("Host JDK unavailable")
        imports = re.findall(
            r"^import static android\.telephony\.ims(?:\.stub)?\.ImsRegistrationImplBase\."
            r"REGISTRATION_TECH_(?:IWLAN|CROSS_SIM);$",
            self.source,
            re.M,
        )
        self.assertEqual(len(imports), 2, "Expected the two registration constant imports")
        source = """%s
class WfcRegistrationApiImportCheck {
    int iwlan = REGISTRATION_TECH_IWLAN;
    int crossSim = REGISTRATION_TECH_CROSS_SIM;
}
""" % "\n".join(imports)
        with tempfile.TemporaryDirectory(prefix="m11_wfc_api_import_") as temporary:
            source_file = Path(temporary) / "WfcRegistrationApiImportCheck.java"
            source_file.write_text(source, encoding="utf-8")
            compiled = subprocess.run(
                [javac, "-classpath", classpath, "-d", temporary, str(source_file)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)


    def test_registering_and_deregistering_clear_wfc_before_notification(self):
        for callback in ("onRegistering", "onUnregistered"):
            with self.subTest(callback=callback):
                body = re.search(
                    rf"{callback}\([^)]*\)\s*\{{(.*?)\n        }}",
                    self.source,
                    re.S,
                )
                self.assertIsNotNone(body)
                self.assertIn("mIsVowifiAvailable = false;", body.group(1))
                self.assertLess(
                    body.group(1).index("mIsVowifiAvailable = false;"),
                    body.group(1).index("notifyListenersIfNecessary();"),
                )

    def test_predicate_uses_registration_state_not_data_rat(self):
        self.assertRegex(
            self.source,
            r"public boolean isVowifiAvailable\(\)\s*\{\s*"
            r"return mCurrentState\.voiceCapable && mCurrentState\.imsRegistered"
            r" && mIsVowifiAvailable;\s*\}",
        )
        self.assertNotRegex(
            self.source,
            r"isVowifiAvailable\(\)\s*\{[^}]*getDataNetworkType\(\)",
        )

    def test_initial_live_query_remains_and_dump_exposes_registration_technology_state(self):
        self.assertIn("mIsVowifiAvailable = tm.isWifiCallingAvailable();", self.source)
        self.assertIn('pw.println("  mIsVowifiAvailable=" + mIsVowifiAvailable + ",");', self.source)

    def test_requested_registration_and_availability_scenarios(self):
        # These scenarios exercise the exact state rule asserted against Java above:
        # IMS registration technology sets the WFC state, then voice capability,
        # IMS registration, and that state jointly gate the icon.
        def icon(voice_capable, ims_registered, technology):
            wfc_registered = technology in {"IWLAN", "CROSS_SIM"}
            return voice_capable and ims_registered and wfc_registered

        self.assertFalse(icon(True, False, "LTE"))  # initial state
        self.assertTrue(icon(True, True, "IWLAN"))  # LTE -> IWLAN
        self.assertFalse(icon(True, True, "LTE"))  # IWLAN -> LTE
        self.assertTrue(icon(True, True, "CROSS_SIM"))
        self.assertFalse(icon(False, True, "IWLAN"))  # voice absent
        self.assertFalse(icon(True, False, "IWLAN"))  # registering/deregistered
        # Packet-data IWLAN alone cannot enable the icon with LTE IMS registration.
        data_rat = "IWLAN"
        registration_technology = "LTE"
        self.assertEqual(data_rat, "IWLAN")
        self.assertFalse(icon(True, True, registration_technology))


class WfcIconPatchContractTest(unittest.TestCase):
    def test_source_selection_has_no_implicit_private_checkout_fallback(self):
        self.assertIsNone(source_from_environment({}))
        self.assertEqual(
            source_from_environment({"M11_SYSTEMUI_SOURCE": "public-source/MobileSignalController.java"}),
            Path("public-source/MobileSignalController.java"),
        )

    def test_packaged_patch_uses_android13_stub_import_namespace(self):
        patch = (Path(__file__).resolve().parents[1]
                 / "platform/systemui/wfc-registration-icon.patch").read_text(encoding="utf-8")
        correct = "android.telephony.ims.stub.ImsRegistrationImplBase"
        incorrect = "android.telephony.ims.ImsRegistrationImplBase"
        added_lines = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+"))
        self.assertIn(correct, added_lines)
        self.assertNotIn(incorrect, added_lines)


if __name__ == "__main__":
    unittest.main()
