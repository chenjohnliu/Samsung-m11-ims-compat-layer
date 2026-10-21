# Samsung Galaxy M11 IMS 相容層

本專案將 Samsung IMS 通訊堆疊移植至 Galaxy M11 的 Android 13 自訂 ROM，並公開相容原始碼與 ROM 整合說明，也提供簡單工具解碼你自己的韌體中的 `imsservice.apk`。本專案不包含 Samsung 韌體，也不是可刷入的 ROM。

[English README](README.md) · [原始碼與 patch 索引](docs/SOURCE_INDEX.md) · [文件導覽](docs/README.md) · [驗證結果](docs/VALIDATED_FEATURES.md)

**電信業者測試結果：台灣大哥大**（維護者實測）與**印度 Jio**（測試者回報）均確認 VoLTE、VoWiFi 正常，且雙向 handover 時通話不中斷。請看[下方結果](#carrier-results)。

## 解碼 `imsservice.apk`

解碼工具會讀取 APK 以及同一版韌體中的 `framework-res.apk`，並將解碼後的檔案寫入新目錄。它不會修改 APK、不會重新打包 APK，也不會建置 Android。

### 1. 安裝需求並複製 repository

以下指令使用 Linux 或 WSL 的 Bash。需要 Python 3、JDK 11 或 JDK 17 的 Java，以及 apktool 2.9.3。請另外從[官方 apktool 2.9.3 發布頁](https://github.com/iBotPeaches/Apktool/releases/tag/v2.9.3)下載 JAR，並確認 shell 可執行 `python3` 與 `java`。使用 WSL 時，請將解碼輸出放在 Linux 家目錄，保留檔名大小寫的差異。接著複製公開相容層 repository：

```sh
mkdir -p "$HOME/src" "$HOME/tools" "$HOME/firmware/m115f-cwk3" "$HOME/work"
git clone https://github.com/chenjohnliu/Samsung-m11-ims-compat-layer.git "$HOME/src/Samsung-m11-ims-compat-layer"
```

這兩個 APK 要從自己的 Samsung 手機或韌體取得，本 Git repository 不提供它們。兩個檔案必須來自同一版原廠韌體；本移植以 `M115FXXS5CWK3`（Android 12）為基準。下一步說明取得方法。

### 2. 設定檔案路徑

以下範例將兩個 APK 存在 `~/firmware/m115f-cwk3`，並假設 apktool 2.9.3 位於 `~/tools`。若檔案在其他位置，請修改路徑。每次執行都請選擇新的輸出目錄。

```sh
export COMPAT_ROOT="$HOME/src/Samsung-m11-ims-compat-layer"
export STOCK_APK="$HOME/firmware/m115f-cwk3/imsservice.apk"
export FRAMEWORK_RES="$HOME/firmware/m115f-cwk3/framework-res.apk"
export APKTOOL="$HOME/tools/apktool_2.9.3.jar"
export DECODED="$HOME/work/imsservice-cwk3-decoded"
```

**方法 A：從仍使用 Samsung 原廠 ROM 的手機拉出檔案。** 安裝 [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)，開啟 USB 偵錯，接上手機並允許偵錯。`adb devices` 應顯示裝置狀態為 `device`。先查詢 APK 的實際路徑，再複製到電腦：

```sh
adb devices
adb shell pm path com.sec.imsservice
IMS_APK_PATH="$(adb shell pm path com.sec.imsservice | tr -d '\r' | sed -n 's/^package://p' | head -n 1)"
if [ -n "$IMS_APK_PATH" ]; then
  adb pull "$IMS_APK_PATH" "$STOCK_APK"
  adb pull /system/framework/framework-res.apk "$FRAMEWORK_RES"
else
  echo "IMS package not found. Check the device connection and package name." >&2
fi
```

這會取得手機**目前安裝的** IMS APK。已刷 CherishOS 或 crDroid 的手機會提供修改版，不能把它當成原始 Samsung 輸入。需要重現原廠移植流程時，請使用原廠手機，或以下方法 B。

**方法 B：從原廠韌體解出檔案。** 如果手機已不在原廠 ROM，先取得相符韌體並解開其中的 system 檔案系統。要找的是該檔案系統內的這兩個位置：

```text
system/priv-app/imsservice/imsservice.apk
system/framework/framework-res.apk
```

將它們分別複製到 `$STOCK_APK` 與 `$FRAMEWORK_RES`。Samsung AP 壓縮包可能包含壓縮、sparse 或動態分割區映像，僅解開 AP 壓縮包不一定能直接看到 APK。映像檔解包與 APK 反編譯是不同步驟；[CWK3 解包紀錄](docs/FRESH_EXTRACTION_VALIDATION.md)記載本專案使用的配置及雜湊，其中的映像解包輔助工具並未隨本 repository 提供。

### 3. 執行解碼工具

請在 clone 下來的 repository 目錄中執行。預設會從 `PATH` 使用 `java`。若 Java 執行檔名稱不同或不在 `PATH`，可使用 `--java` 指定位置。

```sh
cd "$COMPAT_ROOT"
python3 tools/decompile_imsservice.py \
  --apk "$STOCK_APK" \
  --framework-res "$FRAMEWORK_RES" \
  --apktool "$APKTOOL" \
  --output "$DECODED"
```

輸出目錄包含 apktool 解碼後的 manifest、資源與 Samsung smali 位元碼。可以檢視 `AndroidManifest.xml`、`res/` 與 `smali/`；如果有 `smali_classes2/`，其中則是另一個 DEX 的位元碼。Smali 是較易閱讀的 Android 編譯位元碼，不是原始 Java 程式碼。工具會為提供的 `framework-res.apk` 使用獨立 apktool framework cache，不依賴電腦上全域的 apktool cache。

輸出結構如下：

```text
$DECODED/
├── framework/                 # 獨立的 apktool framework cache
├── decoded/
│   ├── AndroidManifest.xml
│   ├── res/
│   ├── smali/
│   └── smali_classes2/         # APK 含有另一個 DEX 時才會出現
└── receipt.json
```

若要搜尋 Samsung 原有後端及該 package 的類別，可執行：

```sh
find "$DECODED/decoded" -type f \( -name 'GoogleImsService.smali' -o -name 'GoogleModern*.smali' \)
```

原廠後端通常位於 `smali/com/sec/internal/google/GoogleImsService.smali`；若類別在第二個 DEX，則會位於 `smali_classes2/`。`GoogleModernImsService` 與 `GoogleModernMmTelFeature` 是本專案相容 patch 新增的類別，因此不會出現在未修改的原廠 APK 解碼結果中。工具會將執行紀錄寫入根目錄的 `receipt.json`。

Samsung 韌體與解碼內容仍受 Samsung 授權條款約束。請將輸入與輸出保留在私有目錄，不要將它們公開在本 repository。

## 建置或套用 ROM 相容修改

APK 解碼與 Android 相容修改的建置、套用是不同工作。CherishOS 請從 [Android 13 原始碼交接指南](docs/CHERISH_ANDROID13_IMS_HANDOFF.md)及[原始碼索引](docs/SOURCE_INDEX.md)開始；crDroid 請參閱[七專案原始碼整合指南](docs/CRDROID_IMS_SOURCE_VERIFIED_20261018.md)。這些文件說明原始碼套用、私有 payload 準備、整合與 ROM 實機驗證；它們不是一鍵建置完整 ROM 的工具。

最新 crDroid IMS APK 已包含 10 月 21 日的 Wi-Fi 簡訊修改，但公開 APK builder 仍固定檢查較早的橋接程式原始碼雜湊。[10 月 21 日修正紀錄](docs/SMS_IWLAN_FIX_20261021.md)記載此修改與已檢視 APK 的識別資訊。若要從乾淨輸入重建該最新 IMS payload，仍須更新並審查產生合約。10 月 18 日的產生指南是較早基線，不能用來宣稱可重建最新 APK。最新 CherishOS 版本已建置、發布並完成原始碼／ZIP 驗證，但尚未回報該版本手機簡訊驗證。

## ROM 下載

若要安裝 ROM，請使用已發布的 [CherishOS 版本](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261020-13-Cherish)或 [crDroid 版本](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261021-13-CrDroid)，並依照其安裝說明操作。本 repository 不提供可刷入的套件。

<a id="carrier-results"></a>

## 電信業者結果

| 電信業者 | VoLTE | VoWiFi | VoWiFi → VoLTE | VoLTE → VoWiFi | 證據來源 |
| --- | --- | --- | --- | --- | --- |
| 台灣大哥大，台灣 | 通過 | 通過 | 通過 | 通過 | [維護者實測](docs/VALIDATED_FEATURES.md) |
| Jio，印度 | 通過 | 通過 | 通過 | 通過 | [測試者回報](docs/cases/JIO_M115F.md#jio-handover-followup) |

兩個 handover 欄位均表示切換期間進行中的通話保持連線。Jio 於 10 月 21 日回報雙向 handover 成功，未提供該次測試的確切 build。下方詳細功能表記錄的是台灣大哥大的測試結果。

## 功能支援狀態

以下功能表是在 Galaxy M11（`SM-M115F`）、Android 13 與台灣大哥大環境，以**一次啟用一張 SIM**進行測試，與上方 Jio 測試者回報分開列示。版本與證據請見[驗證詳情](docs/VALIDATED_FEATURES.md)。最新 crDroid 簡訊結果是維護者回報；尚未回報最新 CherishOS 版本的手機簡訊驗證。

| 功能 | CherishOS 4.12 | crDroid 9.20 |
| --- | --- | --- |
| 啟用中的 SIM 放在 SIM1 或 SIM2 時均可註冊 IMS | 支援 | 支援 |
| VoLTE 撥出與接聽 | 支援 | 支援 |
| Wi-Fi 通話（VoWiFi）撥出與接聽 | 支援 | 支援 |
| 雙向通話音訊與正常掛斷 | 支援 | 支援 |
| 傳送與接收簡訊 | 較早版本已驗證；最新版本尚未回報 | 維護者回報 10 月 21 日版本已測試 |
| 通話中由 Wi-Fi 通話換手至 VoLTE | 支援 | 支援 |
| 通話中由 VoLTE 換手至 Wi-Fi 通話 | 支援 | 支援 |
| 離開訊號較弱的 Wi-Fi 範圍時通話不中斷 | 支援 | 支援 |
| ViLTE（IMS 視訊通話） | 不支援 | 不支援 |
| 兩張 SIM 同時啟用 IMS（DSDS） | 不支援 | 不支援 |
| 透過 LTE 或 Wi-Fi 撥打緊急電話 | 尚未驗證 | 尚未驗證 |

SIM1 與 SIM2 分開測試，不支援同時啟用兩個 IMS 訂閱。其他電信業者與機型尚未通過實機驗證。尚未實際撥打緊急電話，不支援 ViLTE，換手時可能短暫停頓。Jio 的有限測試回報請見[Jio 案例紀錄](docs/cases/JIO_M115F.md)。

## 專案內容

| 目錄 | 用途 |
| --- | --- |
| `tools/` | APK 解碼、原廠 payload 轉換與驗證 |
| `bridge/` | Android／Samsung IMS 相容程式碼與 Android ABI 測試素材 |
| `platform/`、`patches/` | Android framework、Telephony、Telecom 與 ROM 整合修改 |
| `devices/m11q/` | 固定輸入檔雜湊、合約及來源／驗收清單 |
| `tests/` | 原始碼與主機端檢查；不能取代手機測試 |
| `docs/` | 整合指南、技術資料與開發歷程 |

目前文件入口請見[文件導覽](docs/README.md)。除錯請參閱 [IMS 除錯手冊](docs/IMS_DEBUGGING.zh-TW.md)、[英文完整版](docs/IMS_DEBUGGING.md)與[問題回報模板](docs/ISSUE_TEMPLATE.md)。

## 致謝與授權

- [myesxc/Samsung-s20-ims-compat-layer](https://github.com/myesxc/Samsung-s20-ims-compat-layer)：本專案參考的原廠 IMS 調整與相容層作法。
- **@ifoodplayer**：核心原始碼，以及原始裝置與 vendor tree。
- **chenjohnliu**：M11 整合、ROM 建置與實機驗證；實作與分析過程有 ChatGPT/Codex 協助。

[Apache-2.0](LICENSE) 適用於本專案自行撰寫的內容。Samsung 衍生輸入仍受其各自條款約束；請參閱 [NOTICE](NOTICE) 與[修補來源說明](docs/PATCH_PROVENANCE.md)。
