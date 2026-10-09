import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sa2", ROOT / "tools/sa2_telecom_audio_trial.py")
SA2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SA2)


class Sa2PatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        (self.source / SA2.PREFIX).mkdir(parents=True)
        manager = ("    private Call mForegroundCall;\n"
                   "        mCalls.add(call);\n"
                   "        mCalls.remove(call);\n        sendCallStatusToBluetoothStateReceiver();\n"
                   "    private CallAudioModeStateMachine.MessageArgs makeArgsForModeStateMachine() {\n"
                   "    /**\n     * Starts Samsung's ePDG audio path\n     */\n"
                   "    void onSimCallAudioModeSet() {\n"
                   "        return call.getIsVoipAudioMode();\n")
        mode = ("                mAudioManager.setMode(AudioManager.MODE_NORMAL);\n"
                "            mAudioManager.setMode(AudioManager.MODE_IN_CALL);\n"
                "            mAudioManager.setMode(AudioManager.MODE_IN_COMMUNICATION);\n")
        self.original = {"CallAudioManager.java": manager.encode(),
                         "CallAudioModeStateMachine.java": mode.encode()}
        for name, data in self.original.items():
            (self.source / SA2.PREFIX / name).write_bytes(data)
        pins = {name: hashlib.sha256(data).hexdigest() for name, data in self.original.items()}
        self.pins = patch.object(SA2, "INPUTS", pins)
        self.pins.start()
        self.addCleanup(self.pins.stop)

    def test_prepare_changes_no_source_and_includes_four_files(self):
        result = SA2.prepare(self.source, self.base / "prepared")
        self.assertEqual(set(result["output"]), set(self.original) | set(SA2.HELPERS))
        for name, data in self.original.items():
            self.assertEqual((self.source / SA2.PREFIX / name).read_bytes(), data)
        self.assertIn("onConnectionPropertiesChanged", (self.base / "prepared/CallAudioManager.java").read_text())

    def test_apply_verify_restore_preserve_baseline(self):
        backup = self.base / "backup"
        SA2.apply(self.source, backup)
        self.assertEqual(SA2.verify(self.source, backup)["source_gate"], "PASS")
        SA2.restore(self.source, backup)
        for name, data in self.original.items():
            self.assertEqual((self.source / SA2.PREFIX / name).read_bytes(), data)
        for name in SA2.HELPERS:
            self.assertFalse((self.source / SA2.PREFIX / name).exists())

    def test_drift_fails_before_any_writes(self):
        (self.source / SA2.PREFIX / "CallAudioManager.java").write_text("other changes")
        with self.assertRaises(ValueError): SA2.apply(self.source, self.base / "backup")
        self.assertFalse((self.base / "backup").exists())
        self.assertFalse((self.source / SA2.PREFIX / SA2.HELPERS[0]).exists())

    def test_existing_helper_is_not_overwritten(self):
        (self.source / SA2.PREFIX / SA2.HELPERS[0]).write_text("user helper")
        with self.assertRaises(ValueError): SA2.apply(self.source, self.base / "backup")
        self.assertFalse((self.base / "backup").exists())

    def test_restore_refuses_post_apply_edits(self):
        backup = self.base / "backup"
        SA2.apply(self.source, backup)
        helper = self.source / SA2.PREFIX / SA2.HELPERS[0]
        helper.write_text("later edit")
        with self.assertRaises(ValueError): SA2.restore(self.source, backup)
        self.assertEqual(helper.read_text(), "later edit")

    def test_duplicate_anchor_rejected(self):
        name = "CallAudioManager.java"
        data = self.original[name] + b"        mCalls.add(call);\n"
        (self.source / SA2.PREFIX / name).write_bytes(data)
        SA2.INPUTS[name] = SA2.sha(data)
        with self.assertRaisesRegex(ValueError, "anchor drift"):
            SA2.prepare(self.source, self.base / "prepared")
        self.assertFalse((self.base / "prepared").exists())

    def test_refresh_keeps_original_restore_and_saves_revision(self):
        backup, history = self.base / "backup", self.base / "revision"
        SA2.apply(self.source, backup)
        result = SA2.refresh_helpers(self.source, backup, history)
        self.assertEqual(result["carrier_scope"], "all-operators-single-sim-slot0")
        self.assertTrue((history / "manifest.json").exists())
        self.assertEqual(SA2.verify(self.source, backup)["source_gate"], "PASS")
        SA2.restore(self.source, backup)
        for name, data in self.original.items():
            self.assertEqual((self.source / SA2.PREFIX / name).read_bytes(), data)

    def test_refresh_rejects_drift_before_backup(self):
        backup, history = self.base / "backup", self.base / "revision"
        SA2.apply(self.source, backup)
        (self.source / SA2.PREFIX / SA2.HELPERS[0]).write_text("later edit")
        with self.assertRaises(ValueError): SA2.refresh_helpers(self.source, backup, history)
        self.assertFalse(history.exists())


if __name__ == "__main__": unittest.main()
