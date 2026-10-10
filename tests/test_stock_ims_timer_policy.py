import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import stock_ims_timer_policy as T


class StockTimerTests(unittest.TestCase):
    def test_pinned_stock_has_no_override_and_inherits_128_seconds(self):
        data = json.dumps({"profile": [
            {"name": "default", "timer": "A:2000,F:128000"},
            dict(T.BU1.PROFILE_IDENTITY, network=[{"type": "wifi", "services": ["mmtel"]}])]}).encode()
        with patch.object(T, "STOCK_SHA", T.sha(data)):
            T.verify_profile(data)
            self.assertEqual(T.restored_profile(data), data)

    def test_inherited_timer_and_override_are_checked_not_just_hash(self):
        for target, default in (({}, "F:16000"), ({"timer": "F:16000"}, "F:128000"),
                                ({"reg_retry_base_time": 15}, "F:128000")):
            row = dict(T.BU1.PROFILE_IDENTITY, **target,
                       network=[{"type": "wifi", "services": ["mmtel"]}])
            data = json.dumps({"profile": [{"name": "default", "timer": default}, row]}).encode()
            with patch.object(T, "STOCK_SHA", T.sha(data)), self.assertRaises(ValueError):
                T.verify_profile(data)

    def test_unknown_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "input drift"):
            T.restored_profile(b"arbitrary resources")

    def test_exact_insertion_is_inverted_and_stock_hash_checked(self):
        stock = b"prefix\n" + T.BU1.ANCHOR.encode() + b"suffix"
        trial = stock.replace(T.BU1.ANCHOR.encode(), T.BU1.REPLACEMENT.encode())
        with patch.object(T, "TRIAL_SHA", T.sha(trial)), patch.object(T, "verify_profile") as verify:
            self.assertEqual(T.restored_profile(trial), stock)
            verify.assert_called_once_with(stock)
        with patch.object(T, "TRIAL_SHA", T.sha(trial)), self.assertRaisesRegex(ValueError, "hash mismatch"):
            T.restored_profile(trial)

    def test_archive_restoration_preserves_all_dex_and_other_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk, output = root / "old.apk", root / "new.apk"
            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr(T.RESOURCE, b"old profile")
                archive.writestr("classes.dex", b"native unchanged")
                archive.writestr("classes2.dex", b"bridge unchanged")
                archive.writestr("other", b"unchanged")
            with patch.object(T, "PREVIOUS_LG3_APK", T.sha(apk.read_bytes())), \
                    patch.object(T, "restored_profile", return_value=b"stock profile"):
                result = T.restore_apk(apk, output)
                self.assertFalse(result["dex_changed"])
                with zipfile.ZipFile(output) as archive:
                    self.assertEqual(archive.read("classes.dex"), b"native unchanged")
                    self.assertEqual(archive.read("classes2.dex"), b"bridge unchanged")
                    self.assertEqual(archive.read("other"), b"unchanged")
                    self.assertEqual(archive.read(T.RESOURCE), b"stock profile")
                with self.assertRaisesRegex(ValueError, "fresh output"):
                    T.restore_apk(apk, output)


if __name__ == "__main__":
    unittest.main()
