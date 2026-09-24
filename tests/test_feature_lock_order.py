import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "bridge" / "java" / "com" / "sec" / "internal" / "google"


def source(name):
    return (SOURCE / name).read_text(encoding="utf-8")


def method(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(f"unterminated method: {signature}")


class FeatureLockOrderTests(unittest.TestCase):
    def test_framework_lifecycle_callbacks_do_not_take_owner_monitor(self):
        text = source("GoogleModernMmTelFeature.java")
        ready = method(text, "@Override public void onFeatureReady()")
        removed = method(text, "@Override public void onFeatureRemoved()")
        self.assertNotIn("synchronized (owner)", ready)
        self.assertNotIn("synchronized (owner)", removed)
        self.assertIn("owner.featureReady(this)", ready)
        self.assertIn("owner.featureRemoved(this)", removed)

    def test_feature_publication_is_deferred_and_uses_complete_snapshot(self):
        context = source("ModernVoiceContext.java")
        publish = method(context, "void publish()")
        self.assertIn("handler.post", publish)
        self.assertIn("sequence != publishSequence", publish)
        self.assertRegex(publish, re.compile(
            r"target\.publish\(ready, voice, sms\)", re.MULTILINE))

        feature = source("GoogleModernMmTelFeature.java")
        feature_publish = method(feature,
            "void publish(boolean ready, boolean voice, boolean smsReady)")
        self.assertNotIn("sms.available()", feature_publish)
        self.assertIn("if (smsReady)", feature_publish)

    def test_voice_message_framework_callback_is_outside_owner_monitor(self):
        text = source("ModernVoiceContext.java")
        callback = method(text, "public void voiceMessageCountUpdate(int count)")
        synchronized_end = callback.index("}\n                if (target != null)")
        notify = callback.index("target.notifyVoiceMessageCountUpdate(count)")
        self.assertGreater(notify, synchronized_end)

    def test_capability_error_callback_is_outside_owner_monitor(self):
        text = source("GoogleModernMmTelFeature.java")
        change = method(text,
            "@Override public void changeEnabledCapabilities(CapabilityChangeRequest request,")
        owner_end = change.index("}\n        for (CapabilityChangeRequest.CapabilityPair pair : unsupported)")
        callback = change.index("callback.onChangeCapabilityConfigurationError")
        self.assertGreater(callback, owner_end)


if __name__ == "__main__":
    unittest.main()
