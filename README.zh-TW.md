# Samsung Galaxy M11 IMS 相容層

**在 Samsung Galaxy M11 的 Android 13 自訂 ROM 上使用 VoLTE、Wi-Fi 通話與 IMS 簡訊。**

本專案將 Samsung 原廠 IMS 通訊堆疊調整為可搭配 Galaxy M11（`SM-M115F`、`m11q`）上的 **CherishOS 4.12** 與 **crDroid 9.20** 使用，並公開相容程式碼、Android 原始碼修補、轉換工具與開發紀錄。

本移植工作有 ChatGPT/Codex 協助。維護者親自建置並刷入 ROM，在手機上撥打電話、測試簡訊與換手；下方功能狀態以這些實機結果為準。

[English README](README.md) · [文件導覽](docs/README.md) · [驗證結果與範圍](docs/VALIDATED_FEATURES.md)

## 功能支援狀態

下表列出支援、不支援及尚未實際驗證的功能。支援項目已在 M11／台灣大哥大環境，以**一次啟用一張 SIM**完成驗證：

| 功能 | CherishOS 4.12 | crDroid 9.20 |
| --- | --- | --- |
| 啟用中的 SIM 放在 SIM1 或 SIM2 時均可註冊 IMS | 支援 | 支援 |
| VoLTE 撥出與接聽 | 支援 | 支援 |
| Wi-Fi 通話（VoWiFi）撥出與接聽 | 支援 | 支援 |
| 雙向通話音訊與正常掛斷 | 支援 | 支援 |
| 傳送與接收簡訊，包含 IMS 簡訊橋接 | 支援 | 支援 |
| 通話進行中由 Wi-Fi 通話換手至 VoLTE | 支援 | 支援 |
| 通話進行中由 VoLTE 換手至 Wi-Fi 通話 | 支援 | 支援 |
| 離開訊號較弱的 Wi-Fi 範圍時，通話不中斷 | 支援 | 支援 |
| ViLTE（IMS 視訊通話） | 不支援 | 不支援 |
| 兩張 SIM 同時啟用 IMS（DSDS） | 不支援 | 不支援 |
| 透過 LTE 或 Wi-Fi 撥打緊急電話 | 尚未實際驗證 | 尚未實際驗證 |

SIM1 與 SIM2 是分開測試的，兩者沒有同時啟用 IMS。這不代表支援兩張 SIM 同時啟用 IMS。在最新的 CherishOS 測試中，Wi-Fi 訊號恢復後，進行中的通話約兩分鐘後回到 Wi-Fi 通話；實際所需時間可能不同。

## 支援範圍與限制

- 測試裝置為 **Samsung Galaxy M11 SM-M115F**，原廠輸入為 **M115FXXS5CWK3**，目標系統為 **Android 13**。
- 實機結果來自**台灣大哥大**與本次測試的 Wi-Fi 環境。原廠設定檔涵蓋較多電信業者的組態，但其他業者與機型尚未通過實機驗證。
- **不支援兩張 SIM 同時啟用 IMS（DSDS）。**
- **尚未實際撥打緊急電話測試**，包含透過 Wi-Fi 撥打緊急電話。能力回歸測試不會真的撥出電話。
- **不支援 ViLTE（IMS 視訊通話）。** 其他音訊配件不在本次驗證範圍內。換手時可能短暫停頓。

請見[目前的功能驗證紀錄](docs/VALIDATED_FEATURES.md)，了解測試證據與限制。較早的失敗紀錄與已退休的實驗仍保留在文件中，作為開發歷程參考。

## 從哪裡開始

**想使用 ROM：**下載 [CherishOS](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261012-13-Cherish) 或 [crDroid](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261010-13-CrDroid) 版本，並依照各版本的安裝說明操作。本專案不提供可直接刷入的套件。

**想重現 CherishOS 移植：**請從 [Android 13 原始碼整合交接指南](docs/CHERISH_ANDROID13_IMS_HANDOFF.md)開始。該指南會帶你找到固定版本的原始碼檢查點、兩份補充修補，以及原廠輸入檔案的處理流程。整合時使用合併後的檢查點一次即可，不要再疊加舊的修補系列。

**想了解運作方式：**請看[文件導覽](docs/README.md)，其中將目前的整合步驟、各元件技術資料與歷史實驗分開說明。

## 專案內容

| 目錄 | 用途 |
| --- | --- |
| `bridge/` | Android／Samsung IMS 相容程式碼與 Android ABI 測試素材 |
| `platform/`、`patches/` | Android framework、Telephony、Telecom 與 ROM 整合修改 |
| `tools/` | 原廠 payload 轉換、原始碼套用與驗證工具 |
| `devices/m11q/` | 固定版本的輸入檔雜湊、合約，以及原始碼／驗收項目清單 |
| `tests/` | 原始碼與主機端測試；不能取代手機實機測試 |
| `docs/` | 整合指南、技術資料與開發歷程 |

你需要自行準備相符的原廠韌體，並私下保管。此處不提供 Samsung APK、JAR、函式庫、解碼後程式碼、ROM ZIP 或簽署金鑰。

可正常運作的移植版本，和逐位元重建完全相同的成品，是兩件不同的事：最新 CherishOS ROM 已通過手機驗證，但在既有的嚴格產生成品合約下，還無法逐位元重建新的 IMS APK。這不是能替任意 ROM 一鍵完成移植的工具。詳情請見[原始碼交接指南](docs/CHERISH_ANDROID13_IMS_HANDOFF.md)。

## 致謝與授權

- [myesxc/Samsung-s20-ims-compat-layer](https://github.com/myesxc/Samsung-s20-ims-compat-layer)：提供本專案參考的原廠 IMS 調整與相容層作法。
- **@ifoodplayer**：核心原始碼，以及原始裝置與 vendor tree。
- **chenjohnliu**：M11 整合、ROM 建置與實機驗證；實作與分析過程有 ChatGPT/Codex 協助。

[Apache-2.0](LICENSE) 授權適用於本專案自行撰寫的內容。Samsung 衍生輸入仍受其各自授權條款約束；請參閱 [NOTICE](NOTICE) 與[修補來源說明](docs/PATCH_PROVENANCE.md)。
