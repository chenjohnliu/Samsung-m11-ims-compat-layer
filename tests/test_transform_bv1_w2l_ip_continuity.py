import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_bv1_w2l_ip_continuity.py"
CONTRACT = ROOT / "devices" / "m11q" / "bv1-w2l-ip-continuity-trial-contract.json"
HELPER = ROOT / "tools" / "ims_w2l_trial" / "M11qW2LIPContinuity.smali"
RUNTIME = ROOT / "tests" / "epdg_w2l_smali_runtime.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


T = load(TOOL, "transform_bv1_w2l_ip_continuity")
R = load(RUNTIME, "bv1_smali_runtime")
Obj = R.Obj
Runtime = R.Runtime
SmaliClass = R.SmaliClass
SmaliThrown = R.SmaliThrown
method = R.method


class TrialRuntime(Runtime):
    """Add Java Exception-supertype handling without changing the shared runtime."""

    def _handler(self, smali_method, pc, kind):
        found = super()._handler(smali_method, pc, kind)
        if found is not None:
            return found
        if kind in ("Ljava/lang/RuntimeException;", "Landroid/os/RemoteException;"):
            for caught, start, end, handler in smali_method.catches:
                if caught == "Ljava/lang/Exception;" and smali_method.labels.get(start, -1) <= pc < smali_method.labels.get(end, -1):
                    return handler
        return None


class TransformEnvelopeTests(unittest.TestCase):
    def test_contract_and_helper_are_strict_and_pinned(self):
        parsed = T.load_contract(CONTRACT)
        self.assertEqual(parsed["transformation_id"], "BV1-w2l-ip-continuity-trial")
        self.assertEqual(parsed["targets"][0]["path"], T.TARGET)
        self.assertEqual(parsed["additions"][0]["path"], T.ADDITION)
        self.assertEqual(T._sha(HELPER.read_bytes()), parsed["additions"][0]["output_sha256"])
        helper = HELPER.read_text(encoding="utf-8")
        for marker in (
            "m11q_active_call_w2l_handover_bool",
            'const-string v1, "46697"',
            "getSlotIndex",
            "epdg_data[0-9]+",
            "rmnet_data[0-9]+",
            "hasActiveCall",
            "getTotalCallCount",
            "getVideoCallCount",
            "getDowngradedCallCount",
            "getE911CallCount",
            "getForegroundSession",
            "getCallStateOrdinal",
            "CallConstants$STATE;->InCall",
            "reject:ordinary-connected",
            "reject:retained-main",
            "reject:retained-all",
            "reject:retained-pcscf",
            "reject:runtime-exception",
            "getAllAddresses",
            "getPcscfServers",
            "containsAll",
        ):
            self.assertIn(marker, helper)
        for forbidden in ("setDeregiReason", "tryDeregisterInternal", "onEpdgDisconnected", "updateRegistration"):
            self.assertNotIn(forbidden, helper)

    def test_exact_baseline_transform_when_explicitly_supplied(self):
        raw = os.environ.get("M11Q_BV1_IMS_SMALI_ROOT")
        if not raw:
            self.skipTest("set M11Q_BV1_IMS_SMALI_ROOT for private exact-baseline audit")
        source_root = Path(raw)
        spec = T.load_contract(CONTRACT)["targets"][0]
        self.assertEqual(T._sha((source_root / T.TARGET).read_bytes()), spec["input_sha256"])
        temp_parent = ROOT / "work" / "tmp"
        temp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_parent) as raw_temp:
            temp = Path(raw_temp)
            source = temp / "smali"
            target = source / T.TARGET
            target.parent.mkdir(parents=True)
            shutil.copyfile(source_root / T.TARGET, target)
            overlay = temp / "overlay"
            report = temp / "report.json"
            payload = T.transform(CONTRACT, source, overlay, report)
            self.assertEqual(payload, json.loads(report.read_text(encoding="utf-8")))
            self.assertEqual({item["target"] for item in payload["files"]}, {T.TARGET, T.ADDITION})
            self.assertEqual(T._sha((overlay / T.TARGET).read_bytes()), spec["output_sha256"])
            self.assertEqual(
                T._sha((overlay / T.ADDITION).read_bytes()),
                T.load_contract(CONTRACT)["additions"][0]["output_sha256"],
            )

    def test_hash_drift_fails_before_output(self):
        temp_parent = ROOT / "work" / "tmp"
        temp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_parent) as raw_temp:
            temp = Path(raw_temp)
            source = temp / "smali"
            target = source / T.TARGET
            target.parent.mkdir(parents=True)
            target.write_text("drift", encoding="utf-8")
            overlay = temp / "overlay"
            report = temp / "report.json"
            with self.assertRaisesRegex(T.TransformError, "input hash drift"):
                T.transform(CONTRACT, source, overlay, report)
            self.assertFalse(overlay.exists())
            self.assertFalse(report.exists())

    def test_contract_identity_pins_fail_closed(self):
        original = json.loads(CONTRACT.read_text(encoding="utf-8"))
        mutations = (
            lambda data: data["source_baseline"].__setitem__("apk_sha256", "0" * 64),
            lambda data: data["targets"][0].__setitem__("input_sha256", "0" * 64),
            lambda data: data["targets"][0].__setitem__("output_sha256", "0" * 64),
            lambda data: data["additions"][0].__setitem__("output_sha256", "0" * 64),
            lambda data: data.__setitem__("unexpected", True),
        )
        temp_parent = ROOT / "work" / "tmp"
        temp_parent.mkdir(parents=True, exist_ok=True)
        for mutate in mutations:
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory(dir=temp_parent) as raw_temp:
                changed = json.loads(json.dumps(original))
                mutate(changed)
                path = Path(raw_temp) / "contract.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(T.TransformError):
                    T.load_contract(path)


class HelperSmaliRuntimeTests(unittest.TestCase):
    """Execute the authored helper's smali, with only platform boundaries mocked."""

    def setUp(self):
        self.smali = SmaliClass(HELPER)
        self.rt = TrialRuntime(self.smali)
        self.context = Obj("context")
        self.bundle = Obj("bundle", {"identified": 1, "enabled": 1})
        self.carrier = Obj("carrier", {"bundle": self.bundle})
        self.telephony = Obj("telephony", {"operator": "46697"})
        self.context.fields.update({"carrier_config": self.carrier, "phone": self.telephony})
        self.session = Obj("session", {"phone": 0, "state": 5})
        self.volte = Obj("volte", {"active": 1, "total": 1, "video": 0, "downgraded": 0, "e911": 0, "foreground": self.session})
        self.modules = Obj("modules", {"volte": self.volte})
        self.controller = Obj("controller")
        self.old = self.lp("epdg_data0", ["v6a"], ["v6a"], ["p6a", "p6b"])
        self.new = self.lp("rmnet_data2", ["v4a", "v6a"], ["v4a", "v6a"], ["p4a", "p6a", "p6b"])
        self.callback = Obj(
            "callback",
            {"mNetworkType": 11, "mPhoneId": 0, "mLinkProperties": self.old, "this$0": self.controller},
        )
        self.logs = []
        self._bind()

    @staticmethod
    def lp(interface, main, all_addresses, pcscf):
        return Obj("lp", {"interface": interface, "main": list(main), "all": list(all_addresses), "pcscf": list(pcscf)})

    def _internal(self, suffix):
        signature = method(self.smali, suffix)
        return lambda *args: self.rt.run(signature, *args)

    def _bind(self):
        b = self.rt.bind
        owner = "Lcom/sec/internal/ims/core/M11qW2LIPContinuity;->"
        b(owner + "hasAllRetained(Ljava/util/List;Ljava/util/List;)Z", self._internal("hasAllRetained(Ljava/util/List;Ljava/util/List;)Z"))
        b(owner + "hasOrdinaryActiveVoice(I)Z", self._internal("hasOrdinaryActiveVoice(I)Z"))
        b(owner + "hasTrialOptIn(Landroid/content/Context;II)Z", self._internal("hasTrialOptIn(Landroid/content/Context;II)Z"))
        b(owner + "isW2LInterfaceChange(Ljava/lang/String;Ljava/lang/String;)Z", self._internal("isW2LInterfaceChange(Ljava/lang/String;Ljava/lang/String;)Z"))
        b(owner + "logReject(Ljava/lang/String;)V", self._internal("logReject(Ljava/lang/String;)V"))
        b("Lcom/sec/internal/ims/registry/ImsRegistry;->getContext()Landroid/content/Context;", lambda: self.context)
        b("Lcom/sec/internal/ims/registry/ImsRegistry;->getServiceModuleManager()Lcom/sec/internal/interfaces/ims/servicemodules/IServiceModuleManager;", lambda: self.modules)
        b("Lcom/sec/internal/helper/SimUtil;->getSubId(I)I", lambda phone: 1 if phone == 0 else -1)
        b("Landroid/telephony/SubscriptionManager;->getSlotIndex(I)I", lambda sub: 0 if sub == 1 else -1)
        b("Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;", lambda context, name: context.fields.get(name))
        b("Landroid/telephony/CarrierConfigManager;->getConfigForSubId(I)Landroid/os/PersistableBundle;", lambda carrier, sub: carrier.fields["bundle"] if sub == 1 else None)
        b("Landroid/telephony/CarrierConfigManager;->isConfigForIdentifiedCarrier(Landroid/os/PersistableBundle;)Z", lambda bundle: bundle.fields["identified"])
        b("Landroid/os/PersistableBundle;->getBoolean(Ljava/lang/String;Z)Z", lambda bundle, key, default: bundle.fields["enabled"] if key == "m11q_active_call_w2l_handover_bool" else default)
        b("Landroid/telephony/TelephonyManager;->createForSubscriptionId(I)Landroid/telephony/TelephonyManager;", lambda telephony, sub: telephony if sub == 1 else None)
        b("Landroid/telephony/TelephonyManager;->getSimOperator()Ljava/lang/String;", lambda telephony: telephony.fields["operator"])
        b("Lcom/sec/internal/interfaces/ims/servicemodules/IServiceModuleManager;->getVolteServiceModule()Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;", lambda modules: modules.fields["volte"])
        b("Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->hasActiveCall(I)Z", lambda volte, phone: volte.fields["active"] if phone == 0 else 0)
        b("Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getTotalCallCount(I)I", lambda volte, phone: volte.fields["total"] if phone == 0 else 0)
        b("Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getVideoCallCount(I)I", lambda volte, phone: volte.fields["video"] if phone == 0 else 0)
        b("Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getDowngradedCallCount(I)I", lambda volte, phone: volte.fields["downgraded"] if phone == 0 else 0)
        b("Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getE911CallCount(I)I", lambda volte, phone: volte.fields["e911"] if phone == 0 else 0)
        b("Lcom/sec/internal/interfaces/ims/servicemodules/volte2/IVolteServiceModule;->getForegroundSession()Lcom/sec/ims/volte2/IImsCallSession;", lambda volte: volte.fields["foreground"])
        b("Lcom/sec/ims/volte2/IImsCallSession;->getPhoneId()I", lambda session: session.fields["phone"])
        b("Lcom/sec/ims/volte2/IImsCallSession;->getCallStateOrdinal()I", lambda session: session.fields["state"])
        self.rt.enums["Lcom/sec/internal/constants/ims/servicemodules/volte2/CallConstants$STATE;->InCall"] = Obj("enum", {"ordinal": 5})
        b("Ljava/lang/Enum;->ordinal()I", lambda enum: enum.fields["ordinal"])
        b("Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getInterfaceName()Ljava/lang/String;", lambda lp: lp.fields["interface"])
        b("Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getAddresses()Ljava/util/List;", lambda lp: lp.fields["main"])
        b("Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getAllAddresses()Ljava/util/List;", lambda lp: lp.fields["all"])
        b("Lcom/sec/internal/helper/os/LinkPropertiesWrapper;->getPcscfServers()Ljava/util/List;", lambda lp: lp.fields["pcscf"])
        b("Lcom/sec/internal/ims/core/PdnController;->filterAddresses(Ljava/lang/Iterable;)Ljava/util/List;", lambda controller, values: None if values is None else [value for value in values if value])
        b("Ljava/util/List;->isEmpty()Z", lambda values: int(not values))
        b("Ljava/util/List;->containsAll(Ljava/util/Collection;)Z", lambda values, old: int(all(value in values for value in old)))
        b("Ljava/lang/String;->matches(Ljava/lang/String;)Z", lambda value, pattern: int(re.fullmatch(pattern, value) is not None))
        b("Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I", lambda tag, message: self.logs.append((tag, message)) or 0)

    def classify(self):
        return self.rt.run(method(self.smali, "shouldClassifyAsStacked(Lcom/sec/internal/ims/core/PdnController$NetworkCallback;Lcom/sec/internal/helper/os/LinkPropertiesWrapper;)Z"), self.callback, self.new)

    def test_positive_executes_actual_smali(self):
        self.assertEqual(self.classify(), 1)

    def test_all_fail_closed_gates_execute_actual_smali(self):
        mutations = (
            lambda: self.callback.fields.__setitem__("mNetworkType", 0),
            lambda: self.bundle.fields.__setitem__("identified", 0),
            lambda: self.bundle.fields.__setitem__("enabled", 0),
            lambda: self.telephony.fields.__setitem__("operator", "00101"),
            lambda: self.volte.fields.__setitem__("active", 0),
            lambda: self.volte.fields.__setitem__("total", 2),
            lambda: self.volte.fields.__setitem__("video", 1),
            lambda: self.volte.fields.__setitem__("downgraded", 1),
            lambda: self.volte.fields.__setitem__("e911", 1),
            lambda: self.session.fields.__setitem__("phone", 1),
            lambda: self.session.fields.__setitem__("state", 3),
            lambda: self.old.fields.__setitem__("interface", "wlan0"),
            lambda: self.new.fields.__setitem__("interface", "rmnet_data"),
            lambda: self.new.fields.__setitem__("main", ["v4a"]),
            lambda: self.new.fields.__setitem__("all", ["v4a"]),
            lambda: self.new.fields.__setitem__("pcscf", ["p6a"]),
            lambda: self.old.fields.__setitem__("main", []),
            lambda: self.old.fields.__setitem__("all", []),
            lambda: self.old.fields.__setitem__("pcscf", []),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.setUp()
                mutate()
                self.assertEqual(self.classify(), 0)

    def test_runtime_exception_fails_closed(self):
        key = "Lcom/sec/internal/ims/registry/ImsRegistry;->getContext()Landroid/content/Context;"
        self.rt.bind(key, lambda: (_ for _ in ()).throw(SmaliThrown("Ljava/lang/RuntimeException;")))
        self.assertEqual(self.classify(), 0)

    def test_reject_logging_is_bounded_to_exact_w2l_shape(self):
        self.volte.fields["active"] = 0
        self.assertEqual(self.classify(), 0)
        self.assertEqual(self.logs, [("M11Q_W2L_IP", "reject:ordinary-connected")])
        self.setUp()
        self.old.fields["interface"] = "wlan0"
        self.volte.fields["active"] = 0
        self.assertEqual(self.classify(), 0)
        self.assertEqual(self.logs, [])

    def test_remote_exception_fails_closed_and_is_categorized(self):
        key = "Lcom/sec/ims/volte2/IImsCallSession;->getCallStateOrdinal()I"
        self.rt.bind(key, lambda session: (_ for _ in ()).throw(SmaliThrown("Landroid/os/RemoteException;")))
        self.assertEqual(self.classify(), 0)
        self.assertEqual(self.logs, [("M11Q_W2L_IP", "reject:runtime-exception")])


if __name__ == "__main__":
    unittest.main()
