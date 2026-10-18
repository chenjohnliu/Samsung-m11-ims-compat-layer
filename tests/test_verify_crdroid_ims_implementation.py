import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "verify_crdroid_ims_implementation.py"
SPEC = importlib.util.spec_from_file_location("verify_crdroid_ims_implementation", TOOL)
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class VerifyCrDroidImsImplementationTests(unittest.TestCase):
    def test_makepaths_keeps_proprietary_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            device = root / VERIFY.DEV
            mk = device / "ims" / "Android.mk"
            mk.parent.mkdir(parents=True)
            mk.write_text("LOCAL_SRC_FILES := proprietary/lib/arm/libexample.so\n", encoding="utf-8")
            payload = device / "ims" / "proprietary" / "lib" / "arm" / "libexample.so"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"public source fixture")
            self.assertEqual(VERIFY.makepaths(root), {"checked": 1, "missing": []})

    def test_prebuilt_jni_parser_stops_at_next_local_variable(self):
        block = """LOCAL_PREBUILT_JNI_LIBS := \\
    libkept.so \\
    libsecond.so
LOCAL_JNI_SHARED_LIBRARIES := libm11q_sve_compat lib_android_FrameCapture
LOCAL_REQUIRED_MODULES := svemanager
"""
        self.assertEqual(VERIFY.prebuilt_jni_entries(block), ["libkept.so", "libsecond.so"])

    def test_native_wiring_requires_media_headers_for_sve_compat(self):
        bp = '''cc_library_shared {
    name: "libm11q_sve_compat",
    compile_multilib: "32",
    header_libs: ["libmedia_headers"],
}
cc_library_shared {
    name: "lib_android_FrameCapture",
    compile_multilib: "32",
}'''
        mk = '''LOCAL_MODULE := sveservice
LOCAL_JNI_SHARED_LIBRARIES := libm11q_sve_compat lib_android_FrameCapture
include $(BUILD_PREBUILT)'''
        self.assertTrue(VERIFY.check_native_wiring(bp, mk)["media_headers"])
        with self.assertRaisesRegex(ValueError, "must declare libmedia_headers"):
            VERIFY.check_native_wiring(bp.replace('header_libs: ["libmedia_headers"],', ""), mk)

    def test_uw1_identity_uses_public_contract(self):
        contract = {"transformation_id": "contract-defined-uw1"}
        self.assertEqual(VERIFY.check_uw1_identity(
            {"transformation_id": "contract-defined-uw1"}, contract), "contract-defined-uw1")
        with self.assertRaises(ValueError):
            VERIFY.check_uw1_identity({"transformation_id": "guessed-id"}, contract)


if __name__ == "__main__":
    unittest.main()
