import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_epdgservice_w2l_trial.py"
CONTRACT = ROOT / "devices" / "m11q" / "epdgservice-w2l-trial-contract.json"
HELPER = ROOT / "tools" / "epdg_w2l_trial" / "M11qW2LTrial.smali"
RUNTIME = ROOT / "tests" / "epdg_w2l_smali_runtime.py"

runtime_spec = importlib.util.spec_from_file_location("epdg_w2l_smali_runtime", RUNTIME)
runtime_module = importlib.util.module_from_spec(runtime_spec)
assert runtime_spec.loader
sys.modules[runtime_spec.name] = runtime_module
runtime_spec.loader.exec_module(runtime_module)
Obj = runtime_module.Obj
Runtime = runtime_module.Runtime
SmaliClass = runtime_module.SmaliClass
SmaliThrown = runtime_module.SmaliThrown
method = runtime_module.method


def load_tool():
    spec = importlib.util.spec_from_file_location("transform_epdgservice_w2l_trial", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


T = load_tool()


class TransformEnvelopeTests(unittest.TestCase):
    def test_contract_is_strict_complete_and_public_safe(self):
        parsed = T.load_contract(CONTRACT)
        self.assertEqual(parsed["transformation_id"], "EC2-active-w2l-trial")
        self.assertEqual(set(T.TARGETS), {item["path"] for item in parsed["targets"]})
        self.assertEqual(set(T.ADDITIONS), {item["path"] for item in parsed["additions"]})
        text = CONTRACT.read_text(encoding="utf-8").lower()
        for forbidden in ("d:\\", "/home/", ".line ", "invoke-", "const-string"):
            self.assertNotIn(forbidden, text)

    def test_helper_asset_hash_and_required_safety_markers_are_pinned(self):
        parsed = T.load_contract(CONTRACT)
        addition = parsed["additions"][0]
        self.assertEqual(T._sha(HELPER.read_bytes()), addition["output_sha256"])
        helper = HELPER.read_text(encoding="utf-8")
        for marker in (
            "m11q_active_call_w2l_handover_bool",
            "46697",
            "CALL_VOICEONLY",
            "isImsEmergencyCall",
            "getIsCellularAvailable",
            "platformLteVops",
            "getLteVopsSupportInfo",
            "monitor-enter",
            "M11Q_W2L_TRIAL",
        ):
            self.assertIn(marker, helper)
        self.assertNotIn("getIsVoPSEnabled", helper)
        self.assertNotIn("sendMessageDelayed", helper)

    def test_exact_ec1_baseline_when_explicitly_supplied(self):
        root_raw = os.environ.get("M11Q_EC1_SMALI_ROOT")
        if not root_raw:
            self.skipTest("set M11Q_EC1_SMALI_ROOT for private exact-baseline audit")
        root = Path(root_raw)
        for rel, target in T.TARGETS.items():
            self.assertEqual(T._sha((root / rel).read_bytes()), target["input"])
        temp_parent = ROOT / "work" / "tmp"
        temp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_parent) as raw:
            temp = Path(raw)
            source = temp / "smali"
            for rel in T.TARGETS:
                copied = source / rel
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / rel, copied)
            overlay = temp / "overlay"
            report = temp / "report.json"
            payload = T.transform(CONTRACT, source, overlay, report)
            self.assertEqual(payload, json.loads(report.read_text(encoding="utf-8")))
            self.assertEqual({item["target"] for item in payload["files"]}, set(T.TARGETS) | set(T.ADDITIONS))
            for item in payload["files"]:
                expected = (T.TARGETS | T.ADDITIONS)[item["target"]]["output"]
                self.assertEqual(T._sha((overlay / item["target"]).read_bytes()), expected)

    def test_fail_closed_hash_drift_precedes_writes(self):
        parsed = json.loads(CONTRACT.read_text(encoding="utf-8"))
        first = parsed["targets"][0]
        temp_parent = ROOT / "work" / "tmp"
        temp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_parent) as raw:
            temp = Path(raw)
            source = temp / "smali"
            target = source / first["path"]
            target.parent.mkdir(parents=True)
            target.write_text("drift", encoding="utf-8")
            overlay = temp / "overlay"
            report = temp / "report.json"
            with self.assertRaisesRegex(T.TransformError, "input hash drift"):
                T.transform(CONTRACT, source, overlay, report)
            self.assertFalse(overlay.exists())
            self.assertFalse(report.exists())


class HelperRuntimeTests(unittest.TestCase):
    """Execute the helper's smali instructions against deterministic boundaries."""

    def setUp(self):
        self.smali = SmaliClass(HELPER)
        self.rt = Runtime(self.smali)
        self.events = []
        self.sub = Obj("subscription")
        # Samsung's private VoPS cache is deliberately UNKNOWN in the EC2
        # regression.  Eligibility must use the same-subscription platform
        # ServiceState instead of consulting this field.
        self.net = Obj("network", {"cell": 1, "registered": 0, "rat": 13, "vops": "TRI_UNKNOWN"})
        self.ims = Obj("ims", {"emergency": 0})
        self.sub.fields.update({"status": "CALL_VOICEONLY", "connected": 1, "wifi_pdn": 1, "network": self.net, "ims": self.ims})
        self.adapter = Obj("adapter")
        self.bundle = Obj("carrier_bundle", {"identified": 1, "enabled": 1})
        self.carrier = Obj("carrier_config", {"bundle": self.bundle})
        self.platform_vops = Obj("lte_vops", {"supported": 1})
        self.platform_data_info = Obj("data_info", {"lte_vops": self.platform_vops})
        self.wwan_ps = Obj(
            "network_registration_info",
            {"registered": 1, "emergency": 0, "rat": 13, "data_info": self.platform_data_info},
        )
        self.iwlan_ps = Obj(
            "network_registration_info",
            {"registered": 1, "emergency": 0, "rat": 18, "data_info": Obj("data_info", {"lte_vops": Obj("lte_vops", {"supported": 0})})},
        )
        self.service_state = Obj("service_state", {"registrations": {(2, 1): self.wwan_ps, (2, 2): self.iwlan_ps}})
        self.telephony = Obj("telephony", {"operator": "46697", "service_state": self.service_state})
        self.context = Obj("context", {"carrier_config": self.carrier, "phone": self.telephony})
        self.utils = Obj("epdg_utils", {"sub_id": 1})
        self.sm = self.make_sm(0, 1, "ims", self.sub)
        self._bind()
        self.rt.boot()

    @staticmethod
    def make_sm(phone, cid, apn, sub):
        return Obj("sm", {"phone": phone, "cid": cid, "apn": apn, "sub": sub})

    def _bind(self):
        b = self.rt.bind
        b("Lcom/sec/epdg/IPSecDataConnSM;->access$700(Lcom/sec/epdg/IPSecDataConnSM;)I", lambda sm: sm.fields["phone"])
        b("Lcom/sec/epdg/IPSecDataConnSM;->access$1000(Lcom/sec/epdg/IPSecDataConnSM;)Lcom/sec/epdg/EpdgSubScription;", lambda sm: sm.fields["sub"])
        b("Lcom/sec/epdg/IPSecDataConnSM;->getApnType()Ljava/lang/String;", lambda sm: sm.fields["apn"])
        b("Lcom/sec/epdg/IPSecDataConnSM;->getmRilCid()I", lambda sm: sm.fields["cid"])
        b("Lcom/sec/epdg/EpdgSubScription;->getImsCallStatus()Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;", lambda sub: sub.fields["status"])
        b("Lcom/sec/epdg/EpdgSubScription;->getIsImsCallConnected()Z", lambda sub: sub.fields["connected"])
        b("Lcom/sec/epdg/EpdgSubScription;->getNetworkChangeController()Lcom/sec/epdg/NetworkChangeController;", lambda sub: sub.fields["network"])
        b("Lcom/sec/epdg/EpdgSubScription;->getImsManagerHelper()Lcom/sec/epdg/EpdgImsManagerHelper;", lambda sub: sub.fields["ims"])
        b("Lcom/sec/epdg/EpdgSubScription;->getSMForApnType(Ljava/lang/String;)Lcom/sec/epdg/IPSecDataConnSM;", lambda sub, apn: self.sm if sub is self.sub and apn == "ims" else None)
        b("Lcom/sec/epdg/EpdgSubScription;->getEpdgServiceContext()Landroid/content/Context;", lambda sub: self.context)
        b("Lcom/sec/epdg/EpdgSubScription;->isPdnConnectedOverWifi(Ljava/lang/String;)Z", lambda sub, apn: sub.fields["wifi_pdn"] if apn == "ims" else 0)
        b("Lcom/sec/epdg/NetworkChangeController;->getIsCellularAvailable()Z", lambda net: net.fields["cell"])
        b("Lcom/sec/epdg/NetworkChangeController;->getMobileDataReg()I", lambda net: net.fields["registered"])
        b("Lcom/sec/epdg/NetworkChangeController;->getDataRat()I", lambda net: net.fields["rat"])
        b("Lcom/sec/epdg/EpdgImsManagerHelper;->isImsEmergencyCall()Z", lambda ims: ims.fields["emergency"])
        b("Landroid/telephony/SubscriptionManager;->getSlotIndex(I)I", lambda sub_id: 0 if sub_id == 1 else -1)
        b("Lcom/sec/epdg/EpdgUtils;->isIwlanLegacyMode()Z", lambda: 0)
        b("Lcom/sec/epdg/EpdgUtils;->getInstance(I)Lcom/sec/epdg/EpdgUtils;", lambda phone: self.utils if phone == 0 else None)
        b("Lcom/sec/epdg/EpdgUtils;->getSubId(I)I", lambda utils, phone: utils.fields["sub_id"] if phone == 0 else -1)
        b("Landroid/content/Context;->getSystemService(Ljava/lang/String;)Ljava/lang/Object;", lambda context, name: context.fields.get(name))
        b("Landroid/telephony/CarrierConfigManager;->getConfigForSubId(I)Landroid/os/PersistableBundle;", lambda carrier, sub_id: carrier.fields["bundle"] if sub_id == 1 else None)
        b("Landroid/telephony/CarrierConfigManager;->isConfigForIdentifiedCarrier(Landroid/os/PersistableBundle;)Z", lambda bundle: bundle.fields["identified"])
        b("Landroid/os/PersistableBundle;->getBoolean(Ljava/lang/String;Z)Z", lambda bundle, key, default: bundle.fields["enabled"] if key == "m11q_active_call_w2l_handover_bool" else default)
        b("Landroid/telephony/TelephonyManager;->createForSubscriptionId(I)Landroid/telephony/TelephonyManager;", lambda telephony, sub_id: telephony if sub_id == 1 else None)
        b("Landroid/telephony/TelephonyManager;->getSimOperator()Ljava/lang/String;", lambda telephony: telephony.fields["operator"])
        b("Landroid/telephony/TelephonyManager;->getServiceState()Landroid/telephony/ServiceState;", lambda telephony: telephony.fields["service_state"])
        b(
            "Landroid/telephony/ServiceState;->getNetworkRegistrationInfo(II)Landroid/telephony/NetworkRegistrationInfo;",
            lambda state, domain, transport: state.fields["registrations"].get((domain, transport)),
        )
        b("Landroid/telephony/NetworkRegistrationInfo;->isRegistered()Z", lambda info: info.fields["registered"])
        b("Landroid/telephony/NetworkRegistrationInfo;->isEmergencyEnabled()Z", lambda info: info.fields["emergency"])
        b("Landroid/telephony/NetworkRegistrationInfo;->getAccessNetworkTechnology()I", lambda info: info.fields["rat"])
        b(
            "Landroid/telephony/NetworkRegistrationInfo;->getDataSpecificInfo()Landroid/telephony/DataSpecificRegistrationInfo;",
            lambda info: info.fields["data_info"],
        )
        b(
            "Landroid/telephony/DataSpecificRegistrationInfo;->getLteVopsSupportInfo()Landroid/telephony/LteVopsSupportInfo;",
            lambda info: info.fields["lte_vops"],
        )
        b("Landroid/telephony/LteVopsSupportInfo;->isVopsSupported()Z", lambda info: info.fields["supported"])
        b("Lcom/sec/epdg/EpdgSubScription;->notifyQualifiedNetworksChange(Ljava/lang/String;I)V", lambda sub, apn, rat: self.events.append(("pin", apn, rat)))
        b("Lcom/sec/epdg/EpdgSubScription;->notifyQualifiedNetworksChange()V", lambda sub: self.events.append(("recompute",)))
        b("Lcom/sec/epdg/data/Logger/Log;->i(Ljava/lang/String;Ljava/lang/String;)V", lambda tag, message: self.events.append(("log", tag, message)))
        b("Lcom/sec/epdg/apassist/IwlanService/TelephonyAdapter;->getInstance(I)Lcom/sec/epdg/apassist/IwlanService/TelephonyAdapter;", lambda slot: self.adapter)
        b("Lcom/sec/epdg/apassist/IwlanService/TelephonyAdapter;->notifyConnectionStateChanged(IIILandroid/os/Message;)V", lambda adapter, slot, cid, result, msg: self.events.append(("abort", slot, cid, result)))
        b("Lcom/sec/epdg/data/Constants/MapconConstants$MapconApnType;->getIntValue()I", lambda apn: 2)
        b("Lcom/sec/epdg/data/Constants/MapconConstants$MapconMode;->toString()Ljava/lang/String;", lambda mode: mode)
        b("Lcom/sec/epdg/data/Constants/MapconConstants$MapconMode;->getIntValue(Ljava/lang/String;)I", lambda mode: 13)
        b("Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;", lambda value: value)
        b("Ljava/util/List;->set(ILjava/lang/Object;)Ljava/lang/Object;", lambda values, index, value: values.__setitem__(index, value))

    def call(self, suffix, *args):
        return self.rt.run(method(self.smali, suffix), *args)

    def activate_and_attach(self):
        self.assertEqual(self.call("trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z", self.sub, 0, 0), 1)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)

    def active(self, phone=0):
        return bool(self.smali.static["active"][phone])

    def message(self, what, cid=1):
        return Obj("message", {"what": what, "arg1": cid})

    def eligible(self, phone=0, sub_id=1):
        return self.call(
            "eligible(Landroid/content/Context;Lcom/sec/epdg/EpdgSubScription;II)Z",
            self.context,
            self.sub,
            phone,
            sub_id,
        )

    def test_eligibility_executes_all_positive_guards(self):
        self.assertEqual(self.eligible(), 1)

    def test_eligibility_fails_closed_for_every_safety_boundary(self):
        cases = (
            ("unidentified carrier", lambda: self.bundle.fields.__setitem__("identified", 0)),
            ("carrier flag disabled", lambda: self.bundle.fields.__setitem__("enabled", 0)),
            ("wrong SIM operator", lambda: self.telephony.fields.__setitem__("operator", "46692")),
            ("not an ordinary voice call", lambda: self.sub.fields.__setitem__("status", "CALL_VIDEO")),
            ("IMS call disconnected", lambda: self.sub.fields.__setitem__("connected", 0)),
            ("emergency IMS call", lambda: self.ims.fields.__setitem__("emergency", 1)),
            ("not sourced from IWLAN", lambda: self.sub.fields.__setitem__("wifi_pdn", 0)),
            ("cell unavailable", lambda: self.net.fields.__setitem__("cell", 0)),
            ("WWAN PS not registered", lambda: self.net.fields.__setitem__("registered", 1)),
            ("WWAN PS not LTE", lambda: self.net.fields.__setitem__("rat", 20)),
            ("platform LTE VoPS unsupported", lambda: self.platform_vops.fields.__setitem__("supported", 0)),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                self.setUp()
                mutate()
                self.assertEqual(self.eligible(), 0)
        self.setUp()
        self.assertEqual(self.eligible(phone=1), 0, "subscription slot must match the requested phone")
        self.assertEqual(self.eligible(sub_id=-1), 0, "invalid subscription IDs must fail closed")

    def test_eligibility_catches_runtime_exception_and_releases_no_monitor(self):
        key = "Landroid/telephony/CarrierConfigManager;->getConfigForSubId(I)Landroid/os/PersistableBundle;"

        def raise_security_like_runtime(carrier, sub_id):
            raise SmaliThrown("Ljava/lang/RuntimeException;")

        self.rt.bind(key, raise_security_like_runtime)
        self.assertEqual(self.eligible(), 0)
        self.assertTrue(all(depth == 0 for depth in self.rt.monitors.values()))

    def test_samsung_cache_unknown_platform_supported_triggers_attaches_and_defers_source7(self):
        self.assertEqual(self.net.fields["vops"], "TRI_UNKNOWN")
        self.assertEqual(self.call("requestWeak(Lcom/sec/epdg/EpdgSubScription;I)Z", self.sub, 0), 1)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.assertEqual(
            self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(7)),
            1,
        )
        self.assertTrue(self.active())
        self.assertIn(("pin", "ims", 13), self.events)
        messages = [event[2] for event in self.events if event[0] == "log"]
        self.assertTrue(any("event=w2m-enter:attached" in message for message in messages))
        self.assertTrue(any("event=msg7:deferred-once" in message for message in messages))

    def test_platform_vops_unknown_unsupported_and_null_boundaries_reject(self):
        cases = (
            ("unsupported", lambda: self.platform_vops.fields.__setitem__("supported", 0)),
            ("null LTE VoPS info", lambda: self.platform_data_info.fields.__setitem__("lte_vops", None)),
            ("null data-specific info", lambda: self.wwan_ps.fields.__setitem__("data_info", None)),
            ("null WWAN PS registration", lambda: self.service_state.fields["registrations"].__setitem__((2, 1), None)),
            ("null ServiceState", lambda: self.telephony.fields.__setitem__("service_state", None)),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                self.setUp()
                mutate()
                self.assertEqual(self.eligible(), 0)

    def test_platform_vops_selects_ps_wwan_not_ps_wlan(self):
        self.platform_vops.fields["supported"] = 0
        self.iwlan_ps.fields["data_info"].fields["lte_vops"].fields["supported"] = 1
        self.assertEqual(self.eligible(), 0, "IWLAN VoPS support must not substitute for WWAN support")

        self.platform_vops.fields["supported"] = 1
        self.iwlan_ps.fields["data_info"].fields["lte_vops"].fields["supported"] = 0
        self.assertEqual(self.eligible(), 1)

    def test_platform_service_security_exception_fails_closed(self):
        key = "Landroid/telephony/TelephonyManager;->getServiceState()Landroid/telephony/ServiceState;"

        def raise_security_exception(telephony):
            raise SmaliThrown("Ljava/lang/RuntimeException;")

        self.rt.bind(key, raise_security_exception)
        self.assertEqual(self.eligible(), 0)
        messages = [event[2] for event in self.events if event[0] == "log"]
        self.assertTrue(any("event=reject:platform-service-exception" in message for message in messages))

    def test_still_eligible_rejects_wrong_slot_for_current_subscription(self):
        self.assertEqual(self.call("stillEligible(Lcom/sec/epdg/EpdgSubScription;I)Z", self.sub, 0), 1)
        self.assertEqual(self.call("stillEligible(Lcom/sec/epdg/EpdgSubScription;I)Z", self.sub, 1), 0)

    def test_source_first_defers_once_and_duplicate_is_consumed(self):
        self.activate_and_attach()
        self.assertEqual(self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(7)), 1)
        self.assertEqual(self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(7)), 2)
        self.assertTrue(self.active())
        self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.assertFalse(self.active())
        self.assertEqual(self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(7)), 0)
        self.assertEqual(self.events.count(("recompute",)), 1)

    def test_success_first_and_failure_or_native_timeout_exit_cleanup_once(self):
        for label in ("success", "failure", "native-timeout"):
            with self.subTest(label=label):
                self.setUp()
                self.activate_and_attach()
                self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
                self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
                self.assertFalse(self.active())
                self.assertEqual(self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(7)), 0)
                self.assertEqual(self.events.count(("recompute",)), 1)

    def test_framework_cancel_is_cid_scoped(self):
        self.activate_and_attach()
        self.call("onFrameworkCancel(II)V", 0, 7)
        self.assertTrue(self.active())
        self.call("onFrameworkCancel(II)V", 0, 1)
        self.assertFalse(self.active())
        self.assertEqual(self.events.count(("recompute",)), 1)

    def test_framework_cancel_cleans_matching_pending_transaction_before_enter(self):
        self.assertEqual(self.call("trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z", self.sub, 0, 0), 1)
        self.call("onFrameworkCancel(II)V", 0, 7)
        self.assertTrue(self.active(), "a cancellation for another CID must not release the pin")
        self.call("onFrameworkCancel(II)V", 0, 1)
        self.assertFalse(self.active())
        self.assertEqual(self.events.count(("recompute",)), 1)
        self.assertFalse(any(event[0] == "abort" for event in self.events), "pending work has no native transaction to abort")

    def test_weak_request_pins_while_pending_and_matching_cancel_releases_it(self):
        self.assertEqual(self.call("requestWeak(Lcom/sec/epdg/EpdgSubScription;I)Z", self.sub, 0), 1)
        priorities = [90, 91, 92, 93]
        self.call("pinResult(Lcom/sec/epdg/EpdgSubScription;ILjava/util/List;)V", self.sub, 0, priorities)
        self.assertEqual(priorities, [90, 91, 13, 93])
        self.call("onFrameworkCancel(II)V", 0, 1)
        after_cancel = [90, 91, 92, 93]
        self.call("pinResult(Lcom/sec/epdg/EpdgSubScription;ILjava/util/List;)V", self.sub, 0, after_cancel)
        self.assertEqual(after_cancel, [90, 91, 92, 93])

    def test_only_exact_pending_state_machine_can_attach(self):
        self.assertEqual(self.call("trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z", self.sub, 0, 0), 1)
        lookalike = self.make_sm(0, 1, "ims", self.sub)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", lookalike)
        self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", lookalike)
        self.assertTrue(self.active(), "same slot/CID/APN is insufficient without the latched SM identity")
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.assertFalse(self.active())

    def test_old_cleanup_token_cannot_clear_a_later_generation(self):
        self.assertEqual(self.call("trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z", self.sub, 0, 0), 1)
        stale_generation = self.smali.static["generation"][0]
        self.call("onFrameworkCancel(II)V", 0, 1)
        self.assertEqual(self.call("trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z", self.sub, 0, 0), 1)
        self.assertNotEqual(self.smali.static["generation"][0], stale_generation)
        self.call("cleanup(ILjava/lang/String;I)V", 0, "stale-test", stale_generation)
        self.assertTrue(self.active())
        self.call("onFrameworkCancel(II)V", 0, 1)
        self.assertFalse(self.active())

    def test_duplicate_attach_exit_and_cancel_have_one_cleanup(self):
        self.assertEqual(self.call("trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z", self.sub, 0, 0), 1)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.call("onFrameworkCancel(II)V", 0, 1)
        self.assertFalse(self.active())
        self.assertEqual(self.events.count(("recompute",)), 1)

    def test_user_hangup_aborts_existing_native_transaction_then_cleans(self):
        self.activate_and_attach()
        unrelated_sub = Obj("subscription")
        self.call("onCallIdle(Lcom/sec/epdg/EpdgSubScription;I)V", unrelated_sub, 0)
        self.assertTrue(self.active())
        self.call("onCallIdle(Lcom/sec/epdg/EpdgSubScription;I)V", self.sub, 0)
        aborts = [event for event in self.events if event[0] == "abort"]
        self.assertEqual(len(aborts), 1)
        self.assertEqual(aborts[0][1:3], (0, 1))
        self.assertFalse(self.active())
        self.assertEqual(self.events.count(("recompute",)), 1)

    def test_msg6_msg8_wrong_cid_other_phone_and_other_apn_are_not_deferred(self):
        self.activate_and_attach()
        for what in (6, 8):
            self.assertEqual(self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(what)), 0)
        self.assertEqual(self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(7, 2)), 0)
        other_phone = self.make_sm(1, 1, "ims", self.sub)
        other_apn = self.make_sm(0, 1, "mms", self.sub)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", other_phone)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", other_apn)
        self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", other_apn)
        self.assertTrue(self.active())

    def test_source_loss_after_latch_does_not_disable_msg7_retention(self):
        self.activate_and_attach()
        self.sub.fields["wifi_pdn"] = 0
        self.assertEqual(self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(7)), 1)

    def test_monitors_balance_on_all_executed_paths(self):
        self.activate_and_attach()
        self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(7))
        self.call("onFrameworkCancel(II)V", 0, 1)
        self.assertTrue(all(depth == 0 for depth in self.rt.monitors.values()))

    def test_diagnostics_correlate_phone_cid_generation_and_event(self):
        self.activate_and_attach()
        self.call("deferDecision(Lcom/sec/epdg/IPSecDataConnSM;Landroid/os/Message;)I", self.sm, self.message(7))
        self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        messages = [event[2] for event in self.events if event[0] == "log"]
        self.assertTrue(any("phone=0 cid=1 generation=" in message for message in messages))
        self.assertTrue(any("event=msg7:deferred-once" in message for message in messages))
        self.assertTrue(any("event=state-exit" in message for message in messages))

    def test_disabled_clears_pending_but_retains_attached_until_exit(self):
        self.assertEqual(self.call("trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z", self.sub, 0, 1), 1)
        self.call("onTerminalWifiState(Lcom/sec/epdg/EpdgSubScription;II)V", self.sub, 0, 1)
        self.assertFalse(self.active())
        self.setUp()
        self.assertEqual(self.call("trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z", self.sub, 0, 1), 1)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.call("onTerminalWifiState(Lcom/sec/epdg/EpdgSubScription;II)V", self.sub, 0, 1)
        self.assertTrue(self.active())
        self.call("onW2MExit(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.assertFalse(self.active())

    def test_wifi_reenabled_aborts_only_shutdown_originated_transaction(self):
        self.assertEqual(self.call("trigger(Lcom/sec/epdg/EpdgSubScription;IZ)Z", self.sub, 0, 1), 1)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.call("onTerminalWifiState(Lcom/sec/epdg/EpdgSubScription;II)V", self.sub, 0, 3)
        self.assertFalse(self.active())
        self.assertEqual(len([event for event in self.events if event[0] == "abort"]), 1)

    def test_wifi_reenabled_does_not_abort_weak_signal_transaction(self):
        self.assertEqual(self.call("requestWeak(Lcom/sec/epdg/EpdgSubScription;I)Z", self.sub, 0), 1)
        self.call("onW2MEnter(Lcom/sec/epdg/IPSecDataConnSM;)V", self.sm)
        self.call("onTerminalWifiState(Lcom/sec/epdg/EpdgSubScription;II)V", self.sub, 0, 3)
        self.assertTrue(self.active())
        self.assertFalse(any(event[0] == "abort" for event in self.events))
        self.call("onFrameworkCancel(II)V", 0, 1)

    def test_emergency_call_cannot_start_weak_transaction(self):
        self.ims.fields["emergency"] = 1
        self.assertEqual(self.call("requestWeak(Lcom/sec/epdg/EpdgSubScription;I)Z", self.sub, 0), 0)
        self.assertFalse(self.active())

    def test_pin_result_changes_only_ims_entry_while_transaction_is_pinned(self):
        self.activate_and_attach()
        priorities = [90, 91, 92, 93]
        self.call("pinResult(Lcom/sec/epdg/EpdgSubScription;ILjava/util/List;)V", self.sub, 0, priorities)
        self.assertEqual(priorities, [90, 91, 13, 93])


if __name__ == "__main__":
    unittest.main()
