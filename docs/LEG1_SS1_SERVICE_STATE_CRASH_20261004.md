# LEG1 SS1：ServiceState legacy 啟動 crash 修補

後續：SS1 已 build／刷入，見 [首批通話延續紀錄](LEG1_SS1_FIRST_CONTINUITY_CAPTURE_20261004.md)。
後續 [第二包複核](LEG1_SS1_W2L_SAMPLE_NOT_ON_WFC_20261004.md) 撤回「通話內 L2W 已實證」：
資料 RAT變化不等於 IMS bearer handover，兩方向與音訊完整驗收仍未證實。

## 已確認的原因

使用者刷 LEG1 後，尚未出現 VoWiFi 圖示就 crash；ADB 同樣看到 ePDG 在
`NetworkChangeController.onServiceStatusChanged()` 反覆拋出：

```text
NoSuchMethodError: ServiceState.getMobileDataRoaming()Z
```

手機 mode/label 為 `legacy`／`legacy-r1`，root 可用。手機三個檔案與當時
product output SHA-256 相同，因此不是誤刷舊 output：

| 檔案 | SHA-256 |
| --- | --- |
| framework.jar | `2c970f804f65694e76dd2459476cc7b38933eda6c9d6630f47a5eed2075efdb5` |
| EpdgService.apk | `0123c3b5a1b19a92ffd0bc4a6798832609f09a48f827bf8ce0cf21f2153e87be` |
| imsservice.apk | `6a16a7a93e17d7939b7ac021f27cddc361ec77e7ad0b8b3887869147a5bea33e` |

這是 legacy 註冊基線的 framework ABI 缺口，尚未走到通話 handover；
不能用此次 crash 推論 modem／電信不支援通話延續。
原本的 gate 只核對 mode、CarrierConfig 與 APK，未涵蓋此 framework 方法，
所以先前 PASS 不足以排除此類 crash。

## 修補與語意界線

只在現有 Android 13 `ServiceState.java` Samsung 相容方法旁補：

```java
/** @hide */
public boolean getMobileDataRoaming() {
    return getDataRoaming();
}
```

已核對的 stock 方法判斷 Samsung `mMobileDataRoamingType != 0`。
Android 13 的 `getDataRoaming()` 判斷 `getDataRoamingType() != 0`，後者明確讀
PS domain／WWAN transport；這是現有 Android 13 上最接近的 mobile-data 語意，
不是 voice/data 聚合的 `getRoaming()`，也不是硬編碼 false。
Stock 有独立 Samsung 欄位與 producer，所有漫遊／carrier-policy 邊界完全等價
仍未證明；本輪先以 TWM 正常網路驗證。

同一 callback 其餘直接 ServiceState 方法，以及 `EpdgUtils.getVoPS()` 的間接
平台方法已對照 source，未找到第二個缺失的方法。這不是整個 legacy stack
已完整通過 ABI 或實機驗證的宣告。

APK／DEX、兩個 LEG1 設定、modem firmware 與 Wi-Fi deferral 都不變。
新增方法為 `@hide`，不增加公開 SDK API。

## Source 與 gate

WSL source 已套用，原檔包含既有修改並完整備份至：
`D:\m11q\work\leg1_legacy_trial_20261004\backup-ServiceState.java`。

- 原 source SHA-256：`aa4d543b8ac88939626d012948885eefd1a157535b28399b444f37047aa8e54e`
- SS1 source SHA-256：`3248f8549360a5101f5535d18c5bfd5a7b3f189a65099356c67d1e6695e27f88`

`tools/legacy_service_state_compat.py` 以 exact input hash、單一 anchor、完整備份
與既有 atomic writer 進行套用；遇未知編輯／symlink／備份漂移會拒絕覆寫。
`legacy_iwlan_trial.py verify-source` 現在也 pin SS1 source。

刷機前仍使用相同指令，不需要另跑一個可遺忘的 gate：

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/legacy_iwlan_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
```

新 gate 額外讀實際 packaged `system/framework/framework.jar` 的全部標準 DEX，
要求 ServiceState 唯一定義，以及該 legacy callback 所需方法具備正確 signature、
public／static-or-virtual 形態與非 abstract/native code。僅字串或 method reference
存在不能通過。此檢查不是 ART 執行、OTA 簽名或所有行為等價驗證。
目前 crash 版本已被新 gate 按預期拒絕 `getMobileDataRoaming()Z`。

最終非 build 回歸：226 tests，0 failures/errors/skips，包含 9 個 SS1 tests、
真實已編譯 framework／CarrierConfig 檢查與備份、重跑、回復、漂移／symlink 拒絕。
SS1 的 source 檢查也 PASS。未執行 Android ROM build，未安裝或修改手機 framework。

## 下一次單一驗證批次

使用者手動重新 build ROM，gate PASS 後刷對應新 ROM 並完整重開機。
不要熱替換正在使用的 framework.jar；本任務沒有改手機檔案、切網路或重開機。

1. 先確認 LTE／一般通話基線、LEG1 mode/label，以及 ePDG 不再重啟。
2. Wi-Fi 開啟後確認 VoWiFi 能註冊，才測第一通 W2L。
3. 若再 crash：保留 log，依第一個新 exception 定位下一個 ABI 缺口；不測通話。
4. 若不 crash 但 VoWiFi 不註冊：收集 stable dumps 與連續 logs，定位 legacy
   PDN／RIL／netd 路徑，不先調 handover timeout。
5. 若基線成立：沿用 [LEG1 驗收批次](LEG1_MODEM_LED_IWLAN_TRIAL_20261004.md)，
   第一次切換失敗就停止，成功才繼續三次与最後 LTE 回歸。

## 可回復性

只回復 SS1（保留 LEG1 其他設定）的指令：

```sh
python3 tools/legacy_service_state_compat.py rollback \
  --android-root /home/user/android/crdroid \
  --state-dir /mnt/d/m11q/work/leg1_legacy_trial_20261004
```

這會重新引入目前已確認的 legacy crash，不能當作可用 LEG1。
若要完整回復前一轮 AP-assisted source，先執行 LEG1 的 `rollback`，再執行 SS1
`rollback`（LEG1 工具會先核對 SS1 source pin）。每項回復各自逐 byte 檢查；
仍由使用者手動 build／刷機／重開機，不會即時影響手機。
