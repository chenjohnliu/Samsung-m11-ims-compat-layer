# crDroid 熱點通話驗證與 VoWiFi 圖示修正 — 2026-10-10

## 本輪結論

使用者回報本輪來電、雙向 handover、弱訊號走離／返回與切換後新 LTE 通話均 PASS，雙向音訊正常；剩餘異常是 VoWiFi 圖示。這是本機／目前 SIM／相同行動熱點的成功基準，不代表其他電信、雙 SIM 同時使用或家中 Wi-Fi 都已驗收。音訊停頓未在本次回覆逐項量化，不以 log 宣稱已量測小於 2 秒。

目前 stock 成功紀錄、原廠 APK／framework／native 元件都已保留。這一輪不需補錄 stock；後續以 crDroid 紀錄與既有離線 stock 基準對照，不預設再刷回 stock。

## 錄製與版本

- 原始檔：`ims_stock_handover_20261010_174719_crdroid_hotspot_PRIVATE_ALL.tar.gz`。
- 錄製區間：17:47:19–17:56:21 (+0800)。`READY_CAPTURE_STOPPED`、producer stop VERIFIED，242 封包、0 kernel drops；logcat stderr 空白，xfrm 取樣成功。
- Telecom、telephony-common、imsservice 與 EpdgService 四個雜湊均吻合已核對的 20261009 ROM。
- pre/post idle dumps 因無法確認 idle 而略過，不當作完整穩定期快照。較早的 logcat 快取事件排除在本次時間線外。
- 17:50:00–17:50:05 的未接通撥號，使用者確認為取消撥號／對方未接，非故障。

## 通話時間線

| 通話區間 | 觀察到的切換 |
| --- | --- |
| 17:48:00–17:49:38 來電／接通 | 17:48:24 W2L；17:49:22 L2W，均在 ACTIVE 區間 |
| 17:50:19–17:51:03 ACTIVE | 17:50:39 L2W；17:50:51 W2L |
| 17:52:46–17:55:14 ACTIVE | 17:53:06 弱訊號 W2L；約 120 秒 TEPDG 到期後，17:55:06–08 L2W |
| 17:55:33–17:55:42 ACTIVE | 切換後新通話成功接通 |

完成條件採 IMS RAT 與 ePDG 連線狀態變化，不把重複 handover trigger 當成多次成功。ePDG 與 framework 未以共同 call ID 接合，因此上述為時間相關性；雙向音訊與原通話未重撥由使用者確認，不以圖示或註冊成功替代。

弱訊號返回仍沿用 stock 的 TEPDG／遲滯行為，不新增立即強制 L2W、額外等待或定時重新註冊機制。

## 剩餘圖示：限定 SystemUI 的修正

測試前唯讀 ADB 已確認：Wi-Fi 關閉、ePDG 未連線、Samsung IMS 為 LTE，但 crDroid 的 `vowifi_icon` 仍可見。

來源檢查確認 `MobileSignalController.java` 存在可產生過期顯示的缺陷：註冊回報沒有更新 `mIsVowifiAvailable` 快取，且用一般資料網路 IWLAN 作為 IMS Wi-Fi 接入的替代條件。此 capture 未包含 typed `onRegistered(attributes)`，不能單靠這份 archive 宣稱完整執行期因果已證明。

已套用的小修正：

- 註冊 callback 依實際 IMS registration technology 更新圖示；IWLAN／CROSS_SIM 為 WFC，LTE／NR／未知不是。
- registering／unregistered 清除 WFC 狀態。
- 移除一般資料 RAT 的 fallback；保留初始 `TelephonyManager.isWifiCallingAvailable()` 查詢、voice capability、原有 listener／retry 與 VoLTE 邏輯。
- dump 額外顯示 WFC 狀態供定位。

只修改 WSL `frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/connectivity/MobileSignalController.java`，9 行新增／3 行刪除。未改 IMS、ePDG、Telecom、Wi-Fi 關閉暫緩或 handover 行為，未改手機設定。

可重現 patch：`platform/systemui/wfc-registration-icon.patch`（以 `frameworks/base` 為根目錄）。原始 source SHA-256 為 `da74c9490a1c80e54400ae997229c7e3e778105abbe72a591d8a304f49b3713b`；修正後為 `bbab5222ef0ac5bc4058eb049c1a4abcc5db03142be4c7c4527d17e2741f90c0`。已套用至 WSL，不需再次 apply。

6 項檢查 PASS，包含擷取實際 Java callback／predicate 方法本體，以 host stubs 編譯並執行 LTE↔IWLAN、NR、CROSS_SIM、無 voice、registering、deregistered 序列；不是整個 SystemUI 或 Android ROM 編譯。`git diff --check` PASS。

## 下一次使用者 build／刷機的界線

本輪沒有執行 ROM build、刷機、commit 或 push。手機與先前交付的 20261009 ZIP 仍是圖示修正前版本；不要重刷同一 ZIP 期待圖示修正生效。已通過通話測試的版本可先繼續使用，下一次自行 build 時納入這個 source patch。

新版本重點確認：LTE 註冊不再顯示 crDroid VoWiFi 圖示；IWLAN voice 註冊時顯示；切回 LTE 後更新，且同一通電話仍雙向有聲音。不要在 Wi-Fi 暫緩關閉、IMS 尚在 IWLAN 時單靠 Wi-Fi 開關判定圖示錯誤。
