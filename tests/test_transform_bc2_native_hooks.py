import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_bc2_native_hooks.py"
CONTRACT = ROOT / "devices" / "m11q" / "bc2-native-hooks-contract.json"
STUB_TOOL = ROOT / "tools" / "generate_compile_stubs.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load("transform_bc2_native_hooks", TOOL)
STUBS = load("generate_compile_stubs_for_bc2_test", STUB_TOOL)

SERVICE_PATH = "com/sec/internal/google/GoogleImsService.smali"
SESSION_PATH = "com/sec/internal/google/ImsCallSessionImpl.smali"
NOTIFIER_PATH = "com/sec/internal/google/ImsNotifier.smali"


SERVICE = """.class public Lcom/sec/internal/google/GoogleImsService;
.super Lcom/android/ims/internal/IImsService$Stub;
.field static mInstance:Lcom/sec/internal/google/GoogleImsService;
.field mVolteServiceModule:Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;
# direct methods
.method static constructor <clinit>()V
    .locals 0
    return-void
.end method
"""

SESSION = """.class public Lcom/sec/internal/google/ImsCallSessionImpl;
.super Lcom/android/ims/internal/IImsCallSession$Stub;
.method public constructor <init>(Landroid/telephony/ims/ImsCallProfile;Lcom/sec/ims/volte2/IImsCallSession;Landroid/telephony/ims/aidl/IImsCallSessionListener;Lcom/sec/internal/google/GoogleImsService;)V
    .locals 0
    const/4 p1, 0x0
    iput-object p3, p0, Lcom/sec/internal/google/ImsCallSessionImpl;->mListener:Landroid/telephony/ims/aidl/IImsCallSessionListener;
    return-void
.end method
.method public untouched()V
    .locals 0
    return-void
.end method
"""

NOTIFIER = """.class public Lcom/sec/internal/google/ImsNotifier;
.super Ljava/lang/Object;
.method public onIncomingCall(II)V
    .locals 7
    const/4 v0, 0x0
    invoke-interface {v4, p2, v5}, Lcom/android/ims/internal/ISecImsMmTelEventListener;->onIncomingCall(ILandroid/os/Bundle;)V
    return-void
.end method
.method public untouched()V
    .locals 0
    return-void
.end method
"""


class NativeHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "private" / "smali"
        self.overlay = self.base / "overlay"
        self.report = self.base / "report.json"
        self.write(SERVICE_PATH, SERVICE)
        self.write(SESSION_PATH, SESSION)
        self.write(NOTIFIER_PATH, NOTIFIER)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, text):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")

    def run_transform(self, allow_identical=False):
        return MODULE.transform(CONTRACT, self.source, self.overlay, self.report,
                                allow_identical)

    def test_success_emits_only_three_overlay_files_and_private_report(self):
        result = self.run_transform()
        self.assertTrue(result["changed"])
        files = {p.relative_to(self.overlay).as_posix() for p in self.overlay.rglob("*") if p.is_file()}
        self.assertEqual(files, MODULE.EXPECTED_PATHS)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual({f["target"] for f in report["files"]}, MODULE.EXPECTED_PATHS)
        report_text = self.report.read_text(encoding="utf-8")
        self.assertNotIn(str(self.base), report_text)
        self.assertNotIn("const/4", report_text)
        self.assertNotIn(".method", report_text)

    def test_unrelated_methods_and_bytes_are_preserved(self):
        originals = {name: (self.source / name).read_text(encoding="utf-8")
                     for name in MODULE.EXPECTED_PATHS}
        self.run_transform()
        for name in (SESSION_PATH, NOTIFIER_PATH):
            before = MODULE._method_spans(originals[name], "untouched()V")[0][2]
            after_text = (self.overlay / name).read_text(encoding="utf-8")
            after = MODULE._method_spans(after_text, "untouched()V")[0][2]
            self.assertEqual(before, after)
        self.assertTrue((self.overlay / SERVICE_PATH).read_text().startswith(SERVICE.split("# direct methods")[0]))

    def test_missing_duplicate_and_descriptor_drift_fail_closed(self):
        cases = [
            (SESSION_PATH, SESSION.replace("    iput-object p3", "    # removed\n    iput-object p2"), "anchor"),
            (SESSION_PATH, SESSION.replace("    return-void", "    iput-object p3, p0, Lcom/sec/internal/google/ImsCallSessionImpl;->mListener:Landroid/telephony/ims/aidl/IImsCallSessionListener;\n    return-void", 1), "anchor"),
            (SESSION_PATH, SESSION.replace(";)V\n    .locals", ";I)V\n    .locals"), "target method"),
            (SERVICE_PATH, SERVICE.replace(".super Lcom/android", ".super Ljava/lang/Object;\n# .super Lcom/android"), "superclass"),
        ]
        for relative, content, message in cases:
            with self.subTest(relative=relative, message=message):
                self.write(relative, content)
                with self.assertRaisesRegex(MODULE.TransformError, message):
                    self.run_transform()
                self.assertFalse(self.overlay.exists())
                self.assertFalse(self.report.exists())
                self.write(relative, {SERVICE_PATH: SERVICE, SESSION_PATH: SESSION}.get(relative, NOTIFIER))

    def test_register_drift_fails(self):
        for directive in (".locals 6", ".registers 9"):
            with self.subTest(directive=directive):
                self.write(NOTIFIER_PATH, NOTIFIER.replace(".locals 7", directive))
                with self.assertRaisesRegex(MODULE.TransformError, "register/local drift"):
                    self.run_transform()
                self.assertFalse(self.overlay.exists())

    def test_class_field_and_target_access_drift_fail(self):
        cases = [
            (SERVICE_PATH, SERVICE.replace(".class public ", ".class private "), "class identity"),
            (SERVICE_PATH, SERVICE.replace(".field static mInstance", ".field mInstance"), "required field drift"),
            (SERVICE_PATH, SERVICE.replace(".field mVolteServiceModule", ".field static mVolteServiceModule"), "required field drift"),
            (SESSION_PATH, SESSION.replace(".method public constructor", ".method private constructor"), "method access drift"),
            (NOTIFIER_PATH, NOTIFIER.replace(".method public onIncomingCall", ".method private onIncomingCall"), "method access drift"),
        ]
        originals = {SERVICE_PATH: SERVICE, SESSION_PATH: SESSION, NOTIFIER_PATH: NOTIFIER}
        for relative, content, message in cases:
            with self.subTest(relative=relative, message=message):
                self.write(relative, content)
                with self.assertRaisesRegex(MODULE.TransformError, message):
                    self.run_transform()
                self.assertFalse(self.overlay.exists())
                self.assertFalse(self.report.exists())
                self.write(relative, originals[relative])

    def test_already_and_partial_application_fail(self):
        self.run_transform()
        patched = {name: (self.overlay / name).read_text(encoding="utf-8")
                   for name in MODULE.EXPECTED_PATHS}
        for name in MODULE.EXPECTED_PATHS:
            with self.subTest(name=name):
                # Restore clean inputs, then replace only the selected class.
                self.write(SERVICE_PATH, SERVICE); self.write(SESSION_PATH, SESSION); self.write(NOTIFIER_PATH, NOTIFIER)
                self.write(name, patched[name])
                other_overlay = self.base / ("other-" + Path(name).stem)
                other_report = self.base / ("other-" + Path(name).stem + ".json")
                with self.assertRaisesRegex(MODULE.TransformError, "already applied"):
                    MODULE.transform(CONTRACT, self.source, other_overlay, other_report)
        partial = SERVICE.replace("# direct methods\n", "# direct methods\n.method public static declared-synchronized getInstanceIfReady()Lcom/sec/internal/google/GoogleImsService;\n    .locals 1\n    return-object v0\n.end method\n")
        self.write(SERVICE_PATH, partial); self.write(SESSION_PATH, SESSION); self.write(NOTIFIER_PATH, NOTIFIER)
        with self.assertRaisesRegex(MODULE.TransformError, "partially applied"):
            MODULE.transform(CONTRACT, self.source, self.base / "partial", self.base / "partial.json")

    def test_hook_outside_allowlisted_method_fails(self):
        polluted = SESSION.replace("    return-void\n.end method\n", "    invoke-static {p3}, Lcom/sec/internal/google/ModernCallRelay;->constructionListener(Landroid/telephony/ims/aidl/IImsCallSessionListener;)Landroid/telephony/ims/aidl/IImsCallSessionListener;\n    return-void\n.end method\n", 1)
        self.write(SESSION_PATH, polluted)
        with self.assertRaisesRegex(MODULE.TransformError, "partially applied|already applied"):
            self.run_transform()

    def test_output_service_hooks_satisfy_compile_stub_contract(self):
        self.run_transform()
        parsed = STUBS.parse_smali(self.overlay / SERVICE_PATH)
        contract = STUBS.load_contract(ROOT / "devices" / "m11q" / "compile-stub-contract.json")
        cls = next(x for x in contract["classes"] if x["descriptor"] == "Lcom/sec/internal/google/GoogleImsService;")
        # The synthetic fixture lacks unrelated stock methods, but both project hooks
        # must have the exact flags/descriptors accepted by the stub verifier.
        hook_contract = dict(cls)
        hook_contract["methods"] = [item for item in cls["methods"] if item[0] == "project_hooks"]
        STUBS.verify_class(hook_contract, parsed)

    def test_nonoverwrite_identical_idempotence_and_conflict(self):
        self.run_transform()
        before = self.report.read_bytes()
        with self.assertRaisesRegex(MODULE.TransformError, "overwrite"):
            self.run_transform()
        result = self.run_transform(allow_identical=True)
        self.assertFalse(result["changed"])
        self.report.write_text("conflict", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "overwrite"):
            self.run_transform(allow_identical=True)
        self.assertNotEqual(self.report.read_bytes(), before)

    def test_path_symlink_and_output_collision_are_rejected(self):
        with self.assertRaisesRegex(MODULE.TransformError, "distinct"):
            MODULE.transform(CONTRACT, self.source, self.report, self.report)
        with self.assertRaisesRegex(MODULE.TransformError, "outside"):
            MODULE.transform(CONTRACT, self.source, self.source / "overlay",
                             self.base / "outside.json")
        link = self.base / "link"
        try:
            link.symlink_to(self.source, target_is_directory=True)
        except OSError:
            return
        with self.assertRaisesRegex(MODULE.TransformError, "non-symlink"):
            MODULE.transform(CONTRACT, link, self.overlay, self.report)

    def test_atomic_failure_rolls_back_overlay_report_and_temps(self):
        with mock.patch.object(MODULE.os, "rename", side_effect=OSError("synthetic")):
            with self.assertRaisesRegex(OSError, "synthetic"):
                self.run_transform()
        self.assertFalse(self.overlay.exists())
        self.assertFalse(self.report.exists())
        self.assertEqual(list(self.base.glob(".overlay.*")), [])
        self.assertEqual(list(self.base.glob(".report.json.*.tmp")), [])

    def test_contract_is_strict_and_contains_no_stock_context(self):
        raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(raw["transformation_id"], MODULE.TRANSFORMATION_ID)
        text = CONTRACT.read_text(encoding="utf-8")
        for forbidden in (".line ", "try_start", "const-string", "gethistoryinfo", "sec_feature"):
            self.assertNotIn(forbidden, text.lower())
        changed = json.loads(text)
        changed["targets"][1]["expected_anchor"] = 2
        bad = self.base / "bad.json"
        bad.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "contract drift"):
            MODULE.load_contract(bad)


if __name__ == "__main__":
    unittest.main()
