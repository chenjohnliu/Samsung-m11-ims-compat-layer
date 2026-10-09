import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "legacy_wfc_gate_transform.py"
RUNTIME = ROOT / "tests" / "epdg_w2l_smali_runtime.py"
EXACT = ROOT.parent / "work" / "bv1_exact_current_ims_20261003" / "smali"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


T = load(TOOL, "legacy_wfc_gate_transform")
R = load(RUNTIME, "legacy_wfc_gate_smali_runtime")
Obj = R.Obj
Runtime = R.Runtime
SmaliClass = R.SmaliClass
SmaliThrown = R.SmaliThrown
method = R.method


class LegacyRuntime(Runtime):
    def _handler(self, smali_method, pc, kind):
        found = super()._handler(smali_method, pc, kind)
        if found is not None:
            return found
        if kind == "Ljava/lang/Exception;":
            for caught, start, end, handler in smali_method.catches:
                if caught == kind and smali_method.labels.get(start, -1) <= pc < smali_method.labels.get(end, -1):
                    return handler
        return None


def patched_classes(directory):
    manager = T.patch_manager((EXACT / T.MANAGER).read_text(encoding="utf-8"))
    observer = T.patch_observer((EXACT / T.OBSERVER).read_text(encoding="utf-8"))
    manager_path = directory / "WfcEpdgManager.smali"
    observer_path = directory / "WfcEpdgManager$VoWifiSettingObserver.smali"
    manager_path.write_text(manager, encoding="utf-8", newline="\n")
    observer_path.write_text(observer, encoding="utf-8", newline="\n")
    return SmaliClass(manager_path), SmaliClass(observer_path)


class TransformEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXACT.is_dir():
            raise unittest.SkipTest("private exact BV1 smali root unavailable")

    def copy_sources(self, destination):
        for relative in T.PATCHERS:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(EXACT / relative, target)

    def test_exact_hashes_transform_only_two_classes(self):
        for relative in T.PATCHERS:
            self.assertEqual(T.sha256((EXACT / relative).read_bytes()), T.INPUT_SHA256[relative])
        with tempfile.TemporaryDirectory(dir=ROOT.parent / "work") as raw:
            temp = Path(raw)
            source, overlay, report = temp / "source", temp / "overlay", temp / "report.json"
            self.copy_sources(source)
            payload = T.transform(source, overlay, report)
            self.assertEqual(payload, json.loads(report.read_text(encoding="utf-8")))
            self.assertEqual(set(path.relative_to(overlay).as_posix() for path in overlay.rglob("*.smali")), set(T.PATCHERS))
            for relative in T.PATCHERS:
                self.assertEqual(T.sha256((overlay / relative).read_bytes()), T.OUTPUT_SHA256[relative])
                self.assertEqual((source / relative).read_bytes(), (EXACT / relative).read_bytes())

    def test_unknown_repeated_mixed_and_existing_outputs_are_refused(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent / "work") as raw:
            temp = Path(raw)
            source = temp / "source"
            self.copy_sources(source)
            (source / T.MANAGER).write_text("unknown", encoding="utf-8")
            with self.assertRaisesRegex(T.TransformError, "input hash drift"):
                T.transform(source, temp / "a", temp / "a.json")
            self.assertFalse((temp / "a").exists())

        with tempfile.TemporaryDirectory(dir=ROOT.parent / "work") as raw:
            temp = Path(raw)
            source = temp / "source"
            self.copy_sources(source)
            first_overlay, first_report = temp / "first", temp / "first.json"
            T.transform(source, first_overlay, first_report)
            with self.assertRaisesRegex(T.TransformError, "already applied"):
                T.transform(first_overlay, temp / "second", temp / "second.json")
            mixed = temp / "mixed"
            self.copy_sources(mixed)
            shutil.copyfile(first_overlay / T.MANAGER, mixed / T.MANAGER)
            with self.assertRaisesRegex(T.TransformError, "mixed"):
                T.transform(mixed, temp / "third", temp / "third.json")
            with self.assertRaisesRegex(T.TransformError, "overwrite"):
                T.transform(source, first_overlay, temp / "fourth.json")

    def test_static_scope_has_no_setting_writes_or_carrier_override(self):
        manager = T.patch_manager((EXACT / T.MANAGER).read_text(encoding="utf-8"))
        observer = T.patch_observer((EXACT / T.OBSERVER).read_text(encoding="utf-8"))
        additions = manager + observer
        self.assertIn('"content://telephony/siminfo"', additions)
        self.assertIn("ContentResolver;->query", manager)
        self.assertIn("Cursor;->getType", manager)
        self.assertIn("Cursor;->close", manager)
        self.assertIn("isActiveSubscriptionId", manager)
        self.assertIn("getSubscriptionId", manager)
        self.assertIn("getSimSlotIndex", manager)
        self.assertNotIn("SimUtil;->getSubId", additions)
        self.assertNotIn("getIntegerSubscriptionProperty", additions)
        self.assertNotIn("setSubscriptionProperty", additions)
        self.assertNotIn("Settings$System;->put", additions)
        self.assertNotIn('"46697"', additions)
        self.assertEqual(observer.count("sendMessage(II)V"), 3)


class PatchedSmaliRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXACT.is_dir():
            raise unittest.SkipTest("private exact BV1 smali root unavailable")

    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory(dir=ROOT.parent / "work")
        self.manager_class, self.observer_class = patched_classes(Path(self.temp_context.name))
        self.context = Obj("context")
        self.manager = Obj("manager", {"mContext": self.context})
        self.sim = Obj("sim", {"available": 1, "slot": 0, "sub": 1})
        self.subman = Obj("subman", {"active": 1})
        self.resolver = Obj("resolver")
        self.cursor = Obj("cursor", {"row": 1, "type": 1, "value": 1, "closed": 0})

    def tearDown(self):
        self.temp_context.cleanup()

    def active_setting(self, value=1, exception=False, row=True, field_type=1,
                       cursor_none=False, close_exception=False, column_index=1,
                       read_exception=False, after_query=None):
        rt = LegacyRuntime(self.manager_class)
        self.cursor.fields.update({"row": int(row), "type": field_type,
                                   "value": value, "closed": 0})
        b = rt.bind
        b("Lcom/sec/internal/ims/core/sim/SimManagerFactory;->getSimManagerFromSimSlot(I)Lcom/sec/internal/interfaces/ims/core/ISimManager;", lambda phone: self.sim if phone == 0 else None)
        b("Lcom/sec/internal/interfaces/ims/core/ISimManager;->isSimAvailable()Z", lambda sim: sim.fields["available"])
        b("Lcom/sec/internal/interfaces/ims/core/ISimManager;->getSimSlotIndex()I", lambda sim: sim.fields["slot"])
        b("Lcom/sec/internal/interfaces/ims/core/ISimManager;->getSubscriptionId()I", lambda sim: sim.fields["sub"])
        b("Landroid/telephony/SubscriptionManager;->isValidSubscriptionId(I)Z", lambda sub: int(sub >= 0))
        b("Landroid/telephony/SubscriptionManager;->from(Landroid/content/Context;)Landroid/telephony/SubscriptionManager;", lambda context: self.subman)
        b("Landroid/telephony/SubscriptionManager;->isActiveSubscriptionId(I)Z", lambda subman, sub: subman.fields["active"])
        b("Landroid/telephony/SubscriptionManager;->getPhoneId(I)I", lambda sub: 0 if sub == 1 else -1)
        b("Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;", lambda context: self.resolver)
        b("Landroid/net/Uri;->parse(Ljava/lang/String;)Landroid/net/Uri;", lambda value: Obj("uri", {"value": value}))
        b("Ljava/lang/String;->valueOf(I)Ljava/lang/String;", lambda value: str(value))
        def query(resolver, uri, projection, selection, args, sort):
            if exception:
                raise SmaliThrown("Ljava/lang/Exception;")
            self.assertEqual(projection, ["_id", "wfc_ims_enabled"])
            self.assertEqual(selection, "_id=?")
            self.assertEqual(args, ["1"])
            if after_query is not None:
                after_query()
            return None if cursor_none else self.cursor
        b("Landroid/content/ContentResolver;->query(Landroid/net/Uri;[Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;Ljava/lang/String;)Landroid/database/Cursor;", query)
        b("Landroid/database/Cursor;->moveToFirst()Z", lambda cursor: cursor.fields["row"])
        b("Landroid/database/Cursor;->getColumnIndex(Ljava/lang/String;)I", lambda cursor, column: column_index if column == "wfc_ims_enabled" else -1)
        b("Landroid/database/Cursor;->getType(I)I", lambda cursor, index: cursor.fields["type"])
        def get_int(cursor, index):
            if read_exception:
                raise SmaliThrown("Ljava/lang/Exception;")
            return cursor.fields["value"]
        b("Landroid/database/Cursor;->getInt(I)I", get_int)
        def close(cursor):
            cursor.fields["closed"] += 1
            if close_exception:
                raise SmaliThrown("Ljava/lang/Exception;")
        b("Landroid/database/Cursor;->close()V", close)
        return rt.run(method(self.manager_class, "getActiveAndroidWfcSetting(I)I"), self.manager, 0)

    def test_active_subscription_read_accepts_only_minus_one_zero_one(self):
        for value in (-1, 0, 1):
            with self.subTest(value=value):
                self.assertEqual(self.active_setting(value), value)
                self.assertEqual(self.cursor.fields["closed"], 1)
        for value in (-2, 2, 99):
            with self.subTest(value=value):
                self.assertEqual(self.active_setting(value), -2)

    def test_active_subscription_read_fails_closed_on_each_identity_boundary(self):
        mutations = (
            lambda: self.sim.fields.__setitem__("available", 0),
            lambda: self.sim.fields.__setitem__("slot", 1),
            lambda: self.sim.fields.__setitem__("sub", -1),
            lambda: self.subman.fields.__setitem__("active", 0),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.sim.fields.update({"available": 1, "slot": 0, "sub": 1})
                self.subman.fields["active"] = 1
                mutate()
                self.assertEqual(self.active_setting(), -2)
        self.sim.fields.update({"available": 1, "slot": 0, "sub": 1})
        self.subman.fields["active"] = 1
        self.assertEqual(self.active_setting(exception=True), -2)

    def test_active_subscription_read_revalidates_identity_after_query(self):
        mutations = (
            lambda: self.sim.fields.__setitem__("available", 0),
            lambda: self.sim.fields.__setitem__("slot", 1),
            lambda: self.sim.fields.__setitem__("sub", 2),
            lambda: self.subman.fields.__setitem__("active", 0),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.sim.fields.update({"available": 1, "slot": 0, "sub": 1})
                self.subman.fields["active"] = 1
                self.assertEqual(self.active_setting(after_query=mutate), -2)
                self.assertEqual(self.cursor.fields["closed"], 1)

    def test_direct_cursor_read_distinguishes_default_from_malformed_and_failures(self):
        self.assertEqual(self.active_setting(-1, field_type=1), -1)
        self.assertEqual(self.cursor.fields["closed"], 1)
        self.assertEqual(self.active_setting(0, field_type=3), -2)  # text "0" is malformed
        self.assertEqual(self.cursor.fields["closed"], 1)
        self.assertEqual(self.active_setting(0, field_type=0), -2)  # NULL
        self.assertEqual(self.cursor.fields["closed"], 1)
        self.assertEqual(self.active_setting(row=False), -2)
        self.assertEqual(self.cursor.fields["closed"], 1)
        self.assertEqual(self.active_setting(column_index=-1), -2)
        self.assertEqual(self.cursor.fields["closed"], 1)
        self.assertEqual(self.active_setting(read_exception=True), -2)
        self.assertEqual(self.cursor.fields["closed"], 1)
        self.assertEqual(self.active_setting(cursor_none=True), -2)
        self.assertEqual(self.cursor.fields["closed"], 0)
        self.assertEqual(self.active_setting(1, close_exception=True), -2)
        self.assertEqual(self.cursor.fields["closed"], 1)

    def test_mode_match_is_exact_case_sensitive(self):
        signature = method(self.manager_class, "isExplicitLegacyIwlanMode()Z")
        for value, expected in (("legacy", 1), ("LEGACY", 0), ("Legacy", 0), ("", 0), ("AP-Assisted", 0)):
            with self.subTest(value=value):
                rt = LegacyRuntime(self.manager_class)
                rt.bind("Landroid/os/SemSystemProperties;->get(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;", lambda key, default, value=value: value)
                self.assertEqual(rt.run(signature, self.manager), expected)

    def wfc_enabled(self, *, legacy, android, samsung, supported=1, required=0, entitled=1, canada=0, usa=0):
        rt = LegacyRuntime(self.manager_class)
        mno = Obj("mno", {"canada": canada, "usa": usa})
        resolver = Obj("resolver")
        owner = "Lcom/sec/internal/ims/core/WfcEpdgManager;->"
        rt.bind(owner + "isEntitlementRequired(Landroid/content/Context;I)Z", lambda manager, context, phone: required)
        rt.bind(owner + "isEntitlementResult(Landroid/content/Context;I)Z", lambda manager, context, phone: entitled)
        rt.bind(owner + "isVowifiSupported(I)Z", lambda manager, phone: supported)
        rt.bind(owner + "isExplicitLegacyIwlanMode()Z", lambda manager: legacy)
        rt.bind(owner + "getActiveAndroidWfcSetting(I)I", lambda manager, phone: android)
        rt.bind("Lcom/sec/internal/helper/SimUtil;->getSimMno(I)Lcom/sec/internal/constants/Mno;", lambda phone: mno)
        rt.bind("Lcom/sec/internal/constants/Mno;->isCanada()Z", lambda value: value.fields["canada"])
        rt.bind("Lcom/sec/internal/constants/Mno;->isUSA()Z", lambda value: value.fields["usa"])
        rt.bind("Landroid/content/Context;->getContentResolver()Landroid/content/ContentResolver;", lambda context: resolver)
        rt.bind("Landroid/provider/Settings$System;->getInt(Landroid/content/ContentResolver;Ljava/lang/String;I)I", lambda resolver, key, default: samsung)
        return rt.run(method(self.manager_class, "isWFCEnabled(I)Z"), self.manager, 0)

    def test_android_value_is_authoritative_only_in_explicit_legacy_mode(self):
        self.assertEqual(self.wfc_enabled(legacy=0, android=1, samsung=0), 0)
        self.assertEqual(self.wfc_enabled(legacy=0, android=0, samsung=1), 1)
        self.assertEqual(self.wfc_enabled(legacy=1, android=1, samsung=0), 1)
        self.assertEqual(self.wfc_enabled(legacy=1, android=0, samsung=1), 0)
        self.assertEqual(self.wfc_enabled(legacy=1, android=-1, samsung=1), 1)
        self.assertEqual(self.wfc_enabled(legacy=1, android=-1, samsung=0), 0)
        self.assertEqual(self.wfc_enabled(legacy=1, android=-2, samsung=1), 0)

    def test_original_entitlement_support_and_north_america_gates_remain(self):
        self.assertEqual(self.wfc_enabled(legacy=1, android=1, samsung=1, supported=0), 0)
        self.assertEqual(self.wfc_enabled(legacy=1, android=1, samsung=1, required=1, entitled=0), 0)
        self.assertEqual(self.wfc_enabled(legacy=0, android=-2, samsung=0, canada=1), 1)
        self.assertEqual(self.wfc_enabled(legacy=1, android=0, samsung=0, usa=1), 0)
        self.assertEqual(self.wfc_enabled(legacy=1, android=-1, samsung=0, usa=1), 1)

    def test_siminfo_observer_reuses_message_four_for_each_phone_only_in_legacy(self):
        def run(mode, uri_text="content://telephony/siminfo/1"):
            rt = LegacyRuntime(self.observer_class)
            outer = Obj("outer")
            observer = Obj("observer", {"this$0": outer})
            uri = Obj("uri")
            sent = []
            rt.bind("Landroid/net/Uri;->toString()Ljava/lang/String;", lambda value: uri_text)
            rt.bind("Lcom/sec/internal/ims/core/WfcEpdgManager;->access$200()Ljava/lang/String;", lambda: "WfcEpdgManager")
            rt.bind("Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I", lambda tag, text: 0)
            rt.bind("Ljava/lang/String;->startsWith(Ljava/lang/String;)Z", lambda value, prefix: int(value.startswith(prefix)))
            rt.bind("Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z", lambda value, part: int(part in value))
            rt.bind("Landroid/os/SemSystemProperties;->get(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;", lambda key, default: mode)
            rt.bind("Lcom/sec/internal/helper/SimUtil;->getPhoneCount()I", lambda: 2)
            rt.bind("Lcom/sec/internal/ims/core/WfcEpdgManager;->sendMessage(II)V", lambda manager, what, phone: sent.append((what, phone)))
            rt.run(method(self.observer_class, "onChange(ZLandroid/net/Uri;)V"), observer, 0, uri)
            return sent
        self.assertEqual(run("legacy"), [(4, 0), (4, 1)])
        self.assertEqual(run("legacy", "content://telephony/siminfo"), [(4, 0), (4, 1)])
        self.assertEqual(run("legacy", "content://telephony/siminfoevil"), [])
        self.assertEqual(run("AP-Assisted"), [])
        self.assertEqual(run("LEGACY"), [])
        self.assertEqual(run("Legacy"), [])
        self.assertEqual(run(""), [])


if __name__ == "__main__":
    unittest.main()
