import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
JAVA = ROOT / "bridge" / "java" / "com" / "sec" / "internal" / "google"


def source(name):
    return (JAVA / name).read_text(encoding="utf-8")


class ModernSlotPolicyTests(unittest.TestCase):
    def test_service_advertises_exactly_two_mmtel_slots(self):
        text = source("GoogleModernImsService.java")
        query = text[text.index("querySupportedImsFeatures()"):
                     text.index("createMmTelFeatureForSubscription")]
        self.assertEqual(re.findall(r"\.addFeature\((\d+),\s*(\d+)\)", query),
                         [("0", "1"), ("1", "1")])

    def test_service_requires_one_active_exact_slot_subscription_pair(self):
        text = source("GoogleModernImsService.java")
        self.assertIn("slot != 0 && slot != 1", text)
        self.assertIn("SubscriptionManager.isUsableSubscriptionId(subscription)", text)
        self.assertIn("SubscriptionManager.getPhoneId(subscription) != slot", text)
        self.assertIn("SubscriptionManager.getSlotIndex(subscription) != slot", text)
        self.assertIn("subscriptions.getActiveSubscriptionInfo(subscription)", text)
        self.assertIn("subscriptions.getActiveSubscriptionInfoCount()", text)
        self.assertIn("subscriptions.getActiveSubscriptionInfoCount() != 1", text)
        self.assertIn("active.getSubscriptionId() == subscription", text)
        self.assertIn("active.getSimSlotIndex() == slot", text)
        self.assertIn("if (!isSingleActivePair(this, slot, subscription)) return null;", text)

    def test_context_identity_includes_phone_and_subscription(self):
        text = source("GoogleModernImsService.java")
        self.assertIn("context.phoneId != slot || context.subscription != subscription", text)
        self.assertIn("new ModernVoiceContext(this, slot, subscription)", text)
        for method in ("createMmTelFeature(int slot)", "getRegistration(int slot)",
                       "getConfig(int slot)"):
            self.assertRegex(text, re.escape(method) + r" \{ return null; \}")

    def test_stale_existing_context_is_removed_before_requested_pair_check(self):
        text = source("GoogleModernImsService.java")
        existing = ("!isSingleActivePair(this, context.phoneId, "
                    "context.subscription)")
        requested = "if (!isSingleActivePair(this, slot, subscription)) return null;"
        self.assertIn(existing, text)
        self.assertLess(text.index(existing), text.index(requested))
        between = text[text.index(existing):text.index(requested)]
        self.assertIn("context.dispose();", between)
        self.assertIn("context = null;", between)

    def test_stale_request_does_not_remove_still_active_context(self):
        text = source("GoogleModernImsService.java")
        requested = "if (!isSingleActivePair(this, slot, subscription)) return null;"
        start = text.index(requested)
        end = text.index("if (context == null ||", start)
        request_gate = text[start:end]
        self.assertNotIn("context.dispose()", request_gate)
        self.assertNotIn("context = null", request_gate)

    def test_native_backend_and_registration_snapshots_use_owner_phone(self):
        text = source("ModernVoiceContext.java")
        self.assertIn("final int phoneId;", text)
        self.assertIn("backend.open(phoneId, 1, unused", text)
        self.assertIn("backend.getRegistration(phoneId)", text)
        self.assertEqual(text.count("r.getPhoneId() == phoneId"), 2)
        self.assertNotIn("backend.open(0,", text)
        self.assertNotIn("backend.getRegistration(0)", text)
        self.assertIn("phone != target.phoneId", text)
        self.assertIn('extras.getInt("android:imsServiceId", -1) != serviceId', text)

    def test_enablement_retention_is_pair_scoped(self):
        text = source("ModernVoiceContext.java")
        self.assertIn("retainedPhoneId == phoneId", text)
        self.assertIn("retainedSubscription == subscription", text)
        self.assertIn("retainedPhoneId = phoneId", text)
        self.assertIn("retainedSubscription = subscription", text)
        self.assertIn("voiceEnabled = samePair && retainedVoiceEnabled", text)
        self.assertIn("smsEnabled = samePair ? retainedSmsEnabled : true", text)

    def test_sms_delegates_all_native_operations_to_owner_phone(self):
        text = source("ModernSmsBridge.java")
        self.assertNotIn("PHONE_ID", text)
        self.assertIn("owner.phoneId == 0 || owner.phoneId == 1", text)
        self.assertIn("owner.activePair()", text)
        self.assertIn("supportsPhone() && ready", text)
        self.assertIn("if (!supportsPhone())", text)
        self.assertIn("if (!supportsPhone() || !ready", text)
        self.assertIn("attachedBackend == owner.backend && supportsPhone()", text)
        self.assertIn("onSmsReady(owner.phoneId)", text)
        for operation in ("setSmsListener", "setRetryCount", "sendSms", "acknowledgeSms",
                          "acknowledgeSmsReport"):
            self.assertRegex(text, operation + r"\(\s*owner\.phoneId,")

    def test_sms_smsc_and_lifecycle_are_owner_pair_scoped(self):
        text = source("ModernSmsBridge.java")
        self.assertIn("getSmsManagerForSubscriptionId(\n                    owner.subscription)", text)
        self.assertIn("registration.getPhoneId() != owner.phoneId", text)
        self.assertIn("backend.setSmsListener(owner.phoneId, null)", text)
        context = source("ModernVoiceContext.java")
        self.assertIn("boolean activePair()", context)
        self.assertIn("isSingleActivePair(app, phoneId, subscription)", context)

    def test_registration_safety_gates_remain(self):
        text = source("ModernVoiceContext.java")
        self.assertGreaterEqual(text.count("getCurrentRat() != 18"), 2)
        self.assertGreaterEqual(text.count("!r.getImsProfile().hasEmergencySupport()"), 2)
        self.assertGreaterEqual(text.count("r.getImsProfile().getCmcType() == 0"), 2)
        feature = source("GoogleModernMmTelFeature.java")
        self.assertIn("if (tech != 0) return false;", feature)
        self.assertIn("pair.getRadioTech() == 0", feature)


if __name__ == "__main__":
    unittest.main()
