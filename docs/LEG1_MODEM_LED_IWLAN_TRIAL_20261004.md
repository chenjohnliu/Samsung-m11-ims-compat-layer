# LEG1：可回復的 modem-led IWLAN 實驗

日期：2026-10-04。這是 M11／台灣大哥大一般語音的實驗版，不是穩定版，
也不是已完成無縫 handover 的宣告。Android ROM build、刷機、重開機與通話由使用者操作。

## 目前交付狀態

2026-10-05 更新：[LG2 legacy 前綴修正](LG2_LEGACY_EPDG_PREFIX_REPAIR_20261005.md)。
已定位原 LEG1 的 IMS CID 解析錯誤；下述「APK bytes 不變」是 LEG1 初始實驗紀錄，
LG2 另修改 ePDG 的單一方法。最新 `verify-product` 必須檢查 LG2 DEX，舊 APK 不能 PASS。
SS1 framework 與兩個 legacy 設定維持不變；新版仍待使用者 build／刷機後驗證。

最新 checkpoint：[第二包與前一包更正](LEG1_SS1_W2L_SAMPLE_NOT_ON_WFC_20261004.md)。
使用者回報雙向未斷話；兩包確認原 session 正常主動掛斷與資料 RAT／控制通知變化。
但 IMS 同時回報 LTE/non-WFC，因此撤回首包「L2W 已實證」宣告。
SS1 已由使用者 build／刷入，版本核對一致。先釐清真正 WFC 註冊基線；
不可把圖示、資料 RAT或modem ACK直接當成通話 bearer handover 驗收。

前一輪實機結果：LEG1 mode 生效，但 ePDG 在 VoWiFi 註冊前因缺少
`ServiceState.getMobileDataRoaming()` crash；已補 [SS1 framework 相容方法與 gate](LEG1_SS1_SERVICE_STATE_CRASH_20261004.md)。
當時 SS1 source 套用後要求使用者重新 build／刷機，現已完成。
先前的 product PASS 已被新 gate 取代，原 crash output 必須 FAIL。
下列兩設定與 APK 均維持不變。

已套用至 `/home/user/android/crdroid`，`verify-source` PASS；只變更下述兩個設定。
備份與候選檔保存在 `D:\m11q\work\leg1_legacy_trial_20261004`。
最新非 build 回歸：226 tests，0 failures/errors/skips（含 14 個 LEG1 tests、9 個
SS1 tests、真實已編譯 framework 與 CarrierConfig overlay 解析）；collector 的 `bash -n` 通過。
測試涵蓋 guarded apply、逐 byte rollback、重跑、未知修改拒絕、symlink 拒絕、
中途寫入失敗回復，以及錯誤 properties／overlay／APK 不可通過刷機前 gate。

套用後 SHA-256：

- `system.prop`：`9487ecb87ab0db357e9fdfa0a63acfdcad59dd98df12bfb92d8d3d110e11ef7f`
- `vendor.xml`：`164515303794e27f4b7bf0ec2c52b20deea504ba52a7fe037dc869c6297cecea`

本任務未執行 ROM build 或修改手機，僅以 ADB 唯讀核對。最初舊 product output 缺少 LEG1 mode/label，
`verify-product` 按預期 FAIL。使用者後續產生的新 product output 已通過 gate：
legacy mode／LEG1 label、實驗開關 false 與兩個 APK DEX 版本均核對成功。
仍須刷對應該次輸出的 ROM、完整重開機並依下述批次驗收；未檢查 OTA zip 或簽名。

新輸出第一次檢查曾誤報 `Taiwan WFC availability drift: 46601`：aapt 將 source
`mnc="01"`／`"05"` 編譯成數字型屬性，解析後為 `1`／`5`。檢查器已修正為只接受
這兩組已知等價表示；缺少設定、WFC false、重複 carrier 或其他 MNC 仍會拒絕。
本次只修正 host 檢查器與測試，不改 Android source／ROM 輸出，不需因此重 build。

## 為何改走這條路

CWK3 stock 的兩通獨立測試都維持各自原通話，沒有重撥：

- W2L：15:57:51.635 接通，15:57:59.770 關 Wi-Fi，15:58:00.443 handover
  成功，15:58:41.816 才正常結束。原 native session 持續存在。
- L2W：15:59:56.373 接通，16:00:15.387 handover 成功，16:00:51.746 正常結束。

Stock 在 VoWiFi 時就讓 IMS 使用 `rmnet_data1`；切換維持相同 IMS 介面、UA 與
call session。它送 `IPC_NET_DATA_HANDOVER`，等 modem 回報成功，才主動刪除
IKE 隧道。crDroid AP-assisted 版本則先收到 peer IKE DELETE，再收到 remote SIP
BYE（503／BEARER_RELEASED），而後 LTE data target 才回報成功。

已確認的是架構與事件順序差異，不是「改一個 property 必定修好」。crDroid 已通知
modem 通話 active；沒有證據支持另補 IMS call-list API。Stock 不做 live UA rebind，
所以也不以缺少 rebind API 當作已證實根因。後續 403 不是原通話結束的起因。
Stock 兩通成功也尚未量測音訊空窗，不能直接當作 <=2 秒完整驗收。

## 本輪變更與風險

LEG1 初始 mode 切換只變更已核對的兩個 source 設定檔；SS1 另補上述
framework `ServiceState.java` 相容方法：

1. `device/samsung/m11q/system.prop` 加入：

   ```properties
   ro.telephony.iwlan_operation_mode=legacy
   ro.m11q.ims_trial=legacy-r1
   ```

2. CarrierConfig `vendor.xml` 的 46697 設定將
   `m11q_active_call_w2l_handover_bool` 改為 `false`，停用 EC2 與 BV1 實驗。

Android 13 的 AccessNetworksManager 明確支援 legacy，並只使用 WWAN data service；
Samsung ePDG 同樣讀取該 property，改走既有 modem IPC handover 分支。
EC2 還有獨立 legacy 拒絕條件。BV1 關閉後回到原本 local-IP 判斷。

保留目前 EC2-r2 ePDG、BV1 IMS、IMS bridge APK bytes，保留 framework patches、
電信 WFC availability、使用者永久 WFC 偏好與原有 4 秒 Wi-Fi deferral。
不修改 modem firmware、IPsec DELETE/BYE 處理、RTP 或任意 timeout。

**IWLAN operation mode 是整台裝置的開機設定，不是每個 carrier 的獨立開關。**
本輪只能先以單一 TWM SIM 驗證，不代表其他電信、DSDS、反向或緊急通話已通過。
不打緊急電話作為測試。原廠穩定 logical interface 是否能由現有 netd／ePDG 相容層
重現，仍是本輪要辨識的不確定性。

不要在執行中的 phone／IMS／ePDG 上即時切換 mode；其物件與 transaction state 已在
初始化時建立。本輪必須從完整重開機後開始。

## 準備、套用與 source 檢查

以下是在 WSL 內執行的設定工具，不會 build ROM：

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/legacy_iwlan_trial.py prepare \
  --android-root /home/user/android/crdroid \
  --state-dir /mnt/d/m11q/work/leg1_legacy_trial_20261004
python3 tools/legacy_iwlan_trial.py apply \
  --android-root /home/user/android/crdroid \
  --state-dir /mnt/d/m11q/work/leg1_legacy_trial_20261004
python3 tools/legacy_iwlan_trial.py verify-source \
  --android-root /home/user/android/crdroid \
  --state-dir /mnt/d/m11q/work/leg1_legacy_trial_20261004
```

工具先核對 original source／framework／APK pins，保存兩個原始設定檔與候選檔，
只接受 known original 或本工具候選內容。其他修改、symlink、備份漂移都拒絕覆寫。
Apply 可重跑；普通中途失敗會回復本次已寫入檔案，若程序崩潰留下已知混合狀態，
可重跑 apply 或 rollback。`verify-source` 拒絕混合狀態。

設定檔更新使用新 mtime，避免沿用舊增量輸出；不刪除 build output／intermediates。
`PASS` 只代表 source/gate 檢查通過，不代表實機 handover 通過。

## 使用者手動 build 後、刷機前

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/legacy_iwlan_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
```

必須 PASS 才刷。此 gate 檢查 installed-partition build.prop 的 mode／trial label，
實際已編譯 CarrierConfig vendor overlay 的 false 開關、兩個 APK DEX 版本，以及
packaged framework 的 legacy ServiceState 方法定義（含 SS1）。
它不驗證 OTA zip、簽名或手機內容；請使用該次 build 對應的 ROM，不使用舊 zip。
舊 AP-assisted 輸出應 FAIL；不可把上一輪 APK gate PASS 當作 LEG1 的 PASS。

## 一次收集的驗證批次

先將更新的 `D:\m11q\tools\capture_ims_wifi_cycle_termux.sh` 複製到手機。
Collector 現在會記錄 IWLAN mode property、trial label、baseband version，並明確使用
Android `/system/bin/pm` 查 APK 路徑。舊 capture 的空白 APK hashes 不是未安装證據；
若新版仍空白，版本識別仍需另外核對，不能當作已驗證 installed bytes。

重開機、尚未通話時先確認：

```sh
getprop ro.telephony.iwlan_operation_mode
getprop ro.m11q.ims_trial
```

應分別為 `legacy`、`legacy-r1`。先完成一般 LTE 通話，再開 Wi-Fi 等正常 VoWiFi
註冊；如果基線就失敗，先停止，不必進行 handover。
在穩定階段的 phone dump 應為 legacy（`isInLegacy=true`，若該 dump 有輸出此欄）。
CarrierConfig active slot 不應有 persistent override 把實驗開關重設為 true；有則停止
並保留 dump，不自動清除使用者設定。

```sh
IMS_CAPTURE_MODE=handover bash capture_ims_wifi_cycle_termux.sh
```

- 基線與切換前只在穩定、未通話階段輸入 `leg1_lte`、`leg1_iwlan1` 標籤。
- 接通一般 VoWiFi 語音電話，確認聲音，關 Wi-Fi。中途只連續 logcat，不跑 dump。
- 若成功，維持同一 call/session，雙向交談至少 30 秒並記錄音訊空窗；結束後、穩定時
  輸入 `leg1_w2l1`。成功才繼續同批另外兩通 W2L。
- 最後再撥一通 LTE，檢查後續撥號與 487／5065 是否復發。
- 第一次失敗就停止，不切飛航或重開機。若切換卡住，不在途中執行 snapshot；用
  `stop` 完成連續 capture，另註記時間與現象。
- 提供 SHARE_THIS 與 PRIVATE_FULL_CAPTURE；private archive 不公開。

分類路徑：

1. Mode/label 不符或 EC2 trigger／pin／msg7、BV1 `classify-stacked:retained` 出現：
   版本／開關污染，先修部署，不評估本輪 handover。
2. Legacy 生效但 LTE／VoWiFi 基線不成立：查 modem PDN request、RIL CID 與 legacy
   interface/netd 接點，不再改音訊或 BYE。
3. 基線成立且有 modem `IPC_NET_DATA_HANDOVER`，卻失敗：對照 stock 的 CID、回報與
   tunnel cleanup 次序，查 modem／native bearer 契約。
4. Modem 成功但原通話結束：按同一 session 的 bearer、registration、media 時間線定位。
5. 原通話與雙向聲音存活：驗收 3 次 W2L、音訊空窗 <=2 秒與最後 LTE 回歸。
   走離 Wi-Fi、反向、快速切換與其他 carrier 後續再做。

## 回復上一輪 AP-assisted source

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/legacy_iwlan_trial.py rollback \
  --android-root /home/user/android/crdroid \
  --state-dir /mnt/d/m11q/work/leg1_legacy_trial_20261004
```

回復的是變更前 EC2-r2/BV1 AP-assisted 實驗 source，**不是 stock，也不是已驗收穩定版**。
工具不碰其他檔案；仍需由使用者手動 build／刷對應版本／完整重開機，才會影響手機。
不可用正在執行的 property flip 作為回復方式。
