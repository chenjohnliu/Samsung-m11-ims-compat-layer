import hashlib
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_bg1_stats_guard.py"
CANONICAL = ROOT / "devices" / "m11q" / "bg1-stats-guard-contract.json"


def load():
    spec = importlib.util.spec_from_file_location("transform_bg1_stats_guard", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load()
H = MODULE.H

HANDLER = f""".class public {H}
.super Landroid/os/Handler;
# instance fields
.field private mIface:Ljava/lang/String;
.field private mLocalVideoRtcp:I
.field private mLocalVideoRtp:I
.field private mRemoteVideoRtcp:I
.field private mRemoteVideoRtp:I
.field private mReportingNetworkStatsOnPort:Z
.method private start()V
    .locals 6
    const-string v0, "fixture"
    if-eqz v0, :cond_4
    if-eqz v0, :cond_1
    return-void
    .line 52
    :cond_1
    return-void
    :cond_4
    :goto_1
    return-void
.end method
.method private stop()V
    .locals 1
    return-void
.end method
.method private startNetworkStatsOnPorts(Ljava/lang/String;II)V
    .locals 1
    return-void
.end method
.method private stopNetworkStatsOnPorts(Ljava/lang/String;II)V
    .locals 1
    return-void
.end method
.method public declared-synchronized getNetworkStatsVideoCall()J
    .locals 1
    const-wide/16 v0, 0x0
    return-wide v0
.end method
.method public untouched()V
    .locals 0
    return-void
.end method
"""

CALL = """.class public Lcom/sec/internal/ims/servicemodules/volte2/CallStateMachine;
.super Lcom/sec/internal/helper/StateMachine;
.method protected getNetworkStatsVideoCall()J
    .locals 3
    const-wide/16 v0, 0x0
    return-wide v0
.end method
.method protected requestCallDataUsage()V
    .locals 4
    invoke-virtual {p0}, Lcom/sec/internal/ims/servicemodules/volte2/CallStateMachine;->getNetworkStatsVideoCall()J
    move-result-wide v0
    invoke-interface {v2, v3, v0, v1}, Lcom/sec/internal/ims/servicemodules/volte2/IImsMediaController;->onChangeCallDataUsage(IJ)V
    return-void
.end method
.method protected stopNetworkStatsOnPorts()V
    .locals 0
    return-void
.end method
.method public untouched()V
    .locals 0
    return-void
.end method
"""


class Bg1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "private" / "smali"
        self.overlay = self.base / "overlay"
        self.report = self.base / "report.json"
        self.write(MODULE.HANDLER_PATH, HANDLER)
        self.write(MODULE.CALL_PATH, CALL)
        raw = json.loads(CANONICAL.read_text(encoding="utf-8"))
        fixture_hashes = {}
        for item in raw["targets"]:
            item["input_sha256"] = hashlib.sha256(
                (self.source / item["path"]).read_bytes()).hexdigest()
            fixture_hashes[item["path"]] = item["input_sha256"]
        self.hash_patch = mock.patch.dict(MODULE.EXPECTED_INPUT_SHA256,
                                          fixture_hashes, clear=True)
        self.hash_patch.start()
        self.contract = self.base / "contract.json"
        self.contract.write_text(json.dumps(raw), encoding="utf-8")

    def tearDown(self):
        self.hash_patch.stop()
        self.temp.cleanup()

    def write(self, rel, text):
        path = self.source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")

    def run_transform(self, allow_identical=False):
        return MODULE.transform(self.contract, self.source, self.overlay,
                                self.report, allow_identical)

    def refresh_hash(self, rel):
        raw = json.loads(self.contract.read_text(encoding="utf-8"))
        for item in raw["targets"]:
            if item["path"] == rel:
                item["input_sha256"] = hashlib.sha256((self.source / rel).read_bytes()).hexdigest()
                MODULE.EXPECTED_INPUT_SHA256[rel] = item["input_sha256"]
        self.contract.write_text(json.dumps(raw), encoding="utf-8")

    def test_success_emits_only_private_two_file_overlay_and_safe_report(self):
        result = self.run_transform()
        self.assertTrue(result["changed"])
        files = {p.relative_to(self.overlay).as_posix()
                 for p in self.overlay.rglob("*") if p.is_file()}
        self.assertEqual(files, MODULE.EXPECTED_PATHS)
        report_text = self.report.read_text(encoding="utf-8")
        self.assertNotIn(str(self.base), report_text)
        self.assertNotIn(".method", report_text)
        self.assertNotIn("const-string", report_text)

    def test_expected_guard_semantics_and_unrelated_methods_survive(self):
        before = MODULE._method_spans(HANDLER, "public untouched()V")[0][2]
        self.run_transform()
        handler = (self.overlay / MODULE.HANDLER_PATH).read_text(encoding="utf-8")
        call = (self.overlay / MODULE.CALL_PATH).read_text(encoding="utf-8")
        self.assertEqual(before, MODULE._method_spans(handler, "public untouched()V")[0][2])
        self.assertEqual(handler.count('->getMethod('), 3)
        self.assertIn("Landroid/net/NetworkStats;", handler)
        self.assertNotIn("Ljava/lang/Throwable;", handler)
        self.assertIn("const-wide/16 v1, -0x1", handler)
        self.assertIn("const-wide/16 v0, -0x1", MODULE._method_spans(
            call, "protected getNetworkStatsVideoCall()J")[0][2])
        request = MODULE._method_spans(call, "protected requestCallDataUsage()V")[0][2]
        self.assertIn("if-ltz v4, :stats_unavailable", request)

    def test_hash_identity_method_and_anchor_drift_fail_closed(self):
        cases = [
            (MODULE.HANDLER_PATH, HANDLER + "\n", False, "input hash drift"),
            (MODULE.HANDLER_PATH, HANDLER.replace(".class public", ".class private"), True, "class identity"),
            (MODULE.HANDLER_PATH, HANDLER.replace("    .line 52", "    .line 53"), True, "prefix anchor"),
            (MODULE.CALL_PATH, CALL.replace("protected stopNetworkStatsOnPorts", "private stopNetworkStatsOnPorts"), True, "required method"),
        ]
        originals = {MODULE.HANDLER_PATH: HANDLER, MODULE.CALL_PATH: CALL}
        for rel, content, refresh, message in cases:
            with self.subTest(message=message):
                self.write(rel, content)
                if refresh:
                    self.refresh_hash(rel)
                with self.assertRaisesRegex(MODULE.TransformError, message):
                    self.run_transform()
                self.assertFalse(self.overlay.exists())
                self.assertFalse(self.report.exists())
                self.write(rel, originals[rel]); self.refresh_hash(rel)

    def test_already_and_partial_application_fail_before_hash(self):
        self.run_transform()
        patched = (self.overlay / MODULE.HANDLER_PATH).read_text(encoding="utf-8")
        other_overlay, other_report = self.base / "other", self.base / "other.json"
        self.write(MODULE.HANDLER_PATH, patched)
        with self.assertRaisesRegex(MODULE.TransformError, "already or partially"):
            MODULE.transform(self.contract, self.source, other_overlay, other_report)

    def test_nonoverwrite_identical_and_conflict(self):
        self.run_transform()
        with self.assertRaisesRegex(MODULE.TransformError, "overwrite"):
            self.run_transform()
        self.assertFalse(self.run_transform(True)["changed"])
        self.report.write_text("conflict", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "overwrite"):
            self.run_transform(True)

    def test_atomic_failure_rolls_back(self):
        with mock.patch.object(MODULE.os, "rename", side_effect=OSError("synthetic")):
            with self.assertRaisesRegex(OSError, "synthetic"):
                self.run_transform()
        self.assertFalse(self.overlay.exists())
        self.assertFalse(self.report.exists())
        self.assertEqual(list(self.base.glob(".overlay.*")), [])

    def test_output_collision_and_symlink_input_fail(self):
        with self.assertRaisesRegex(MODULE.TransformError, "distinct"):
            MODULE.transform(self.contract, self.source, self.report, self.report)
        link = self.base / "link"
        try:
            link.symlink_to(self.source, target_is_directory=True)
        except OSError:
            return
        with self.assertRaisesRegex(MODULE.TransformError, "non-symlink"):
            MODULE.transform(self.contract, link, self.overlay, self.report)

    def test_contract_is_narrow_and_contains_no_stock_implementation(self):
        text = CANONICAL.read_text(encoding="utf-8")
        for forbidden in (".line ", "invoke-", "const-string", "/" + "home/"):
            self.assertNotIn(forbidden, text.lower())
        self.assertIsNone(re.search(r"[a-z]:\\\\", text.lower()))
        raw = json.loads(text)
        raw["targets"][0]["input_sha256"] = "0" * 64
        bad_hash = self.base / "bad-hash.json"
        bad_hash.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "input hash contract drift"):
            MODULE.load_contract(bad_hash)
        raw = json.loads(text)
        raw["targets"][0]["path"] = "other.smali"
        bad = self.base / "bad.json"
        bad.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.TransformError, "target paths"):
            MODULE.load_contract(bad)


if __name__ == "__main__":
    unittest.main()
