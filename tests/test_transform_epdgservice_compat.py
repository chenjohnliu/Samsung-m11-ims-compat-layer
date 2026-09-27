import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "tools" / "transform_epdgservice_compat.py"
CONTRACT = ROOT / "devices" / "m11q" / "epdgservice-compat-contract.json"


def load():
    spec = importlib.util.spec_from_file_location("transform_epdgservice_compat", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


M = load()


def method(signature, body):
    return f".method {signature}\n{body}.end method"


class EpdgTransformTests(unittest.TestCase):
    def test_contract_is_complete_and_public_safe(self):
        parsed = M.load_contract(CONTRACT)
        self.assertEqual(len(parsed["targets"]), 7)
        self.assertEqual(len(parsed["roundtrip_normalizations"]), 1)
        text = CONTRACT.read_text(encoding="utf-8").lower()
        for forbidden in ("/home/", "d:\\", ".line ", "invoke-", "const-string"):
            self.assertNotIn(forbidden, text)

    def test_qns_and_interface_patches_are_narrow(self):
        qns = method("private updateHandOverEnabled(I)V", "    .locals 0\n    .line 107\n    invoke-super {p0, p1}, Landroid/telephony/data/QualifiedNetworksService$NetworkAvailabilityProvider;->updateHandoverEnabled(I)V\n\n    .line 108\n    return-void\n")
        self.assertNotIn("invoke-super", M._patch_qns(qns))
        interface = method("private makeInterfaceUp(Ljava/lang/String;Ljava/util/List;)V", """    .locals 6
    if-nez v3, :cond_3

    .line 123
    if-eqz v1, :cond_2

    .line 124
    invoke-interface {v3, p1}, Landroid/os/INetworkManagementService;->enableIpv6(Ljava/lang/String;)V
    :cond_2
    iget-object v3, p0, Lx;->x:Ljava/lang/Object;
    .line 129
    :cond_3
    iget-object v3, p0, Lx;->x:Ljava/lang/Object;
    return-void
""")
        updated = M._patch_interface(interface)
        self.assertIn("getIpv6Address", updated)
        self.assertNotIn("if-nez v3, :cond_3", updated)

    def test_telephony_patches_prefix_and_bounds_cid(self):
        fixture = method("private constructor <init>(I)V", """    .locals 4
    const-string v2, "ril.data.intfprefix"

    const-string v3, "rmnet"

    invoke-static {v2, v3}, Landroid/os/SystemProperties;->get(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;

    move-result-object v2
    return-void
""") + "\n" + method("public setupDataCall(ILandroid/telephony/data/DataProfile;ZZILandroid/net/LinkProperties;Landroid/os/Message;)V", """    .locals 16
    and-int/lit8 v14, v4, 0xf

    .line 163
    .local v14, "cid":I
    return-void
""")
        updated = M._patch_telephony(fixture)
        self.assertIn('const-string v2, "epdg_data"', updated)
        self.assertIn("if-lez v14, :cond_6", updated)
        self.assertIn("if-le v14, v4, :cond_7", updated)

    def test_subscription_wifi_and_observer_patches(self):
        subscription = method("protected getVowifiSetting()I", """    .locals 5

    .line 296
    iget v0, p0, Lcom/sec/epdg/EpdgSubScriptionBase;->mPhoneId:I
    if-eqz v1, :cond_1
    if-eqz v1, :cond_0
    :cond_0
    const/4 v1, 0x0
    :cond_1
    iget-object v1, p0, Lx;->x:Ljava/lang/Object;
    return v1
""")
        self.assertIn("getIntegerSubscriptionProperty", M._patch_subscription(subscription))
        wifi = "\n".join(method(sig, """    .locals 6
    check-cast v0, Landroid/net/wifi/WifiManager;

    .local v0, "wifiManager":Landroid/net/wifi/WifiManager;
    if-eqz v1, :cond_0
    :cond_0
    return-void
""") for sig in M.TARGETS["com/sec/epdg/utils/WifiInterface/EpdgWifiInfo.smali"]["methods"])
        patched_wifi = M._patch_wifi(wifi)
        self.assertEqual(patched_wifi.count("if-nez v0, :cond_0"), 3)
        observer = method("public onChangeSlowPath(ZLandroid/net/Uri;)V", """    .locals 13
    invoke-virtual {v12, v4}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v3

    if-eqz v3, :cond_0
    return-void
""") + "\n" + method("public registerObserver(I)V", """    .locals 6
    :goto_0
    invoke-static {}, Lcom/sec/epdg/EpdgService;->isCrossSimSupportedbyDevice()Z
    return-void
""")
        patched_observer = M._patch_observer(observer)
        self.assertEqual(patched_observer.count("content://telephony/siminfo"), 1)
        self.assertIn('const-string v3, "telephony/siminfo"', patched_observer)

    def test_anchor_drift_and_repeat_apply_fail_closed(self):
        with self.assertRaisesRegex(M.TransformError, "anchor drift"):
            M._replace_once("unchanged", "missing", "new", "test")
        spec = next(iter(M.TARGETS.values()))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.json"
            raw = json.loads(CONTRACT.read_text(encoding="utf-8"))
            raw["targets"][0]["operations"] = ["drift"]
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(M.TransformError, "contract drift"):
                M.load_contract(path)
        self.assertEqual(len(spec["input"]), 64)


if __name__ == "__main__":
    unittest.main()
