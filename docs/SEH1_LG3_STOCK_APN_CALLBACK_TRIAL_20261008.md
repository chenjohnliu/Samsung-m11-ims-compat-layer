# SEH1 + LG3：恢復 stock APN 回報與首次啟動 WFC 開關

2026-10-09 更新：依使用者要求移除 SEH1 的 46697 限制，接受所有有效電信
MCC/MNC；保留單一有效 SIM／slot 0、訂閱一致性、provider 優先與 APN 驗證。
已透過有版本檢查與備份的工具升級 WSL source，非 ROM 測試通過。
下列 10/08 的 TWM 範圍與尚未實測說明屬歷史；最新
[實測與 Git 盤點](CONVERSATION_CHANGE_AND_GIT_AUDIT_20261009.md)為準。

狀態（2026-10-08）：source 與 LG3 IMS APK 已備份、套用到
`/home/user/android/crdroid`，source gate 通過。**尚未執行 ROM build、刷機或實機驗收。**
目前 `out/target/product/m11q` 仍是舊產物，新 product gate 已確認會拒絕它。
這不是穩定版，也不是已證明的通話延續修復。

## 為什麼是這個批次

10/05 受控測試已區分出兩個阻礙，詳見
[首次啟動 checkpoint](LG2_FIRST_BOOT_WFC_GATE_CHECKPOINT_20261005.md)：

- Android 的有效 SIM 開關為 1，Samsung `wifi_call_enable1` 為 0；外層 WfcEpdgManager
  不啟動 ePDG。短暫鏡射後服務立即啟動，實驗結束已還原 Samsung 開關。
- 下一個最早的 native 失敗為 `mSehRadioIndication == NULL` →
  `SecLoadApnProfFromDB failed` → `TryHandoverCall: Failed to load apn profile`。
  此時仍未證明真正的 Wi-Fi IMS registration。

Stock CWK3 的 SemRIL 會註冊 Samsung 回報介面；目前 AOSP RIL 沒有對應 client。
SEH1 補這個 stock 契約，不新增另一套 handover 演算法；保留 LEG1 modem-led legacy
模式、LG2 interface prefix、SS1 ServiceState 相容層及 Android 原有 Wi-Fi 暫緩關閉。
EC2/BV1 的 AP-assisted 實驗開關維持 false，Wi-Fi 等待時間／RSSI 門檻都不改。

## 已實作

LG3 只修改 WfcEpdgManager 與其 setting observer。在明確 `legacy` 模式，讀取目前
有效 SIM 的 Android `wfc_ims_enabled`；0／1 遵守使用者選擇，真正未設定的 -1 才
回到原 Samsung 計算。SIM／slot／sub 不符、查詢失敗或異常欄位值皆不強制啟用。
只讀取設定，不改寫 Android 或 Samsung 偏好；新增 siminfo 變更觀察。

SEH1 由既有 RIL constructor 啟動唯一 callback owner，另由 DataProfileManager handler
發布 immutable snapshot。只有 `m11q`、明確 legacy、boot opt-in 與 phone 0 才啟動；
APN／setting／packet 回報再限於 **slot 0、單一有效 SIM、台灣大哥大 46697**。
其他台灣電信既有 WFC availability 不變，但不推廣這次 bridge／handover 試驗。

Samsung provider 查詢優先、selection 原樣傳入。只有零筆資料且精確符合 native IMS
selection 時，才回傳 Android 實際建立的唯一 IMS-only、enabled、LTE-compatible profile。
不插入 APN DB、不硬編碼 APN／credentials／CID，不對 provider null／exception 做 fallback。
SIM 切換、Cursor close 失敗或 stale vendor epoch 均回空值；vendor death 後自動重連，
每次重試等待最多 10 秒，不改通話 handover timeout。

Stock 私有 `allocateCid`／`releaseCid` 尚未 port：回 -1 並只記錄一次，不猜 CID。
如果新 log 顯示它們成為下一個阻礙，再追對應 stock 流程。

## ABI 核對（已觀察，不是推測）

Stock generated smali、DSDS native disassembly／relocation 與 AOSP source 直接支持：

| Samsung 2.0 transaction | 呼叫／回傳 |
| --- | --- |
| Radio tx1，同步 | response、indication 兩個 non-null binder；任一 null 會清除兩者 |
| Indication tx21，oneway | modem capability 通知，**不是 setting** |
| Indication tx22，同步 | APN selection → 96-byte、六個 non-null HIDL strings |
| Indication tx23，同步 | key、table → int32 setting；已知設定預設為 0 |
| Indication tx25／26，同步 void | signal／registration 通知，仍需 success reply |
| Indication tx27，同步 | interface → int32 error + 16-byte blob，rx int64@0、tx int64@8 |

APN wire offsets：apn@0、protocol@16、roamingProtocol@32、user@48、password@64、auth@80。
Stock SemRIL.sendAck() 是空方法；SEH 通知不送 Android standard-radio ACK。
兩個 callback 均使用核對過的 base-2.0 descriptor／hash chain 與 IBase 契約。

DSDS LoadApnProfile 在 IMS type／RAT14 的實際 selection：

```text
carrier_enabled=1 and (bearer=14 or bearer=0) and bearer_bitmask!=131072 and type LIKE '%ims%'
```

該字串由 native 路徑直接確認；不依賴「當時 call profile 必為 2」這個未印在 log 的推論。
fallback 欄位來自 handler 端實際 DataProfile，不用觀察到的 `ims/IPV4V6/auth0` 值硬編碼。

## 產物與驗證

- LG3 unsigned IMS APK SHA256：`4aeb261ac3f43ac85a5f8825c2bfe3b7741b442f251d9bee8be1631e0538fb97`
- LG3 classes.dex：`8dd61436164931a648f49f88b41bb88e2ac71c5d9df7893cbdbbbf10a8924064`
- 原 BV1 classes2.dex 保留：`b9d57c1a1aab37fd88a5443bde177c710897b1603481350e8037cf332ce0d325`
- 5,451 個 primary classes 重解碼逐一比對：指定兩個類別外沒有 instruction／metadata 改動。
  其他 ZIP entries 與 bridge DEX 均保留，獨立 strict rebuild 的 APK／DEX pins 相同。
- Python regression：266 tests，PASS，4 個 optional private-fixture skips。
- JVM policy／transport：13 組 PASS；bridge／publisher：9 組 PASS。
- 四個新 Java source 以目前 framework、telephony-common、framework-connectivity-t classpath
  完成 JDK11 編譯；LG3 所需 SubscriptionManager／Cursor API 也核對存在。
- staging 的 rollback、idempotence、concurrent edit／create refusal、manifest／source pin drift
  與故障回復均有測試。無 ROM build、ADB 設定寫入、modem firmware 修改。

實機 signature、SELinux 載入、真實 callback 及通話延續仍待驗收。

## 你接下來只需一次 build／刷機批次

Source 已套用，不要再執行舊 LEG1 apply 或重新 stage BV1 APK。先照原本方式 build ROM。
**Build 完、刷機前**在 WSL 執行新的 gate（舊 LEG1 product gate 預期不再接受 LG3）：

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/legacy_seh_apn_trial.py verify-source \
  --android-root /home/user/android/crdroid \
  --state-dir /mnt/d/m11q/work/seh1-lg3-source-state-20261008
python3 tools/legacy_seh_apn_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
```

兩個都 PASS 再刷機、完整重開機。Product gate 檢查 boot flags、compiled carrier XML、
LG3/LG2 DEX、SS1 ABI 與 SEH1 的 defined entry points；不是 signature 或 runtime 成功證明。
`ro.m11q.ims_trial=legacy-r1` 保留，另有 `ro.m11q.ims_seh_apn_bridge=true`，不能只看舊 label。

同一個實機驗證批次：

1. 僅 slot 0 的台灣大哥大 SIM，Android WFC 開關開啟、Wi-Fi 有網路，先不打電話。
   收 first-boot 完整 log，確認 `Registered reviewed SEH callbacks`、APN provider／snapshot
   回報、IKE／IPsec 成功，以及 native IMS 的 ePDG-connected／on-WFC／IWLAN 狀態。
   **圖示或 aggregate data RAT 不能取代這些證據。**無真正 WFC 就停在 registration 診斷。
2. 確認真正 WFC 後，對另一支可交談的電話做 W2L／L2W；不中斷、不重撥、同一 session。
   先做一回，若失敗保留 log 並停止反覆切換／飛航／重開；若成功再各做三次，
   每次轉移後雙向交談至少 30 秒，記錄音訊間隔是否 ≤2 秒。
3. 通話中走離 Wi-Fi 覆蓋範圍做三次 W2L，最後再撥 LTE 電話檢查 487／5065。
   188 可以作接通 smoke test，不能驗證雙向音訊與 2 秒間隔。

既有 `D:/m11q/tools/capture_ims_wifi_cycle_termux.sh` 使用 handover 模式；連續 logcat 記錄
切換，snapshot 只在前後穩定階段。將新腳本版本放回手機後再用，分享紅除版為主。
我可在刷機後透過 ADB 做版本與真正 WFC 判定，不需要你猜圖示。

分流：callback 仍為 null → registration／service／SELinux；callback 成功但 APN empty →
selection／active SIM／snapshot；APN 已回且 IPsec 失敗 → native／IKE；真 WFC 後通話斷線 →
沿完整原通話時間線追 modem bearer、IMS session 與音訊，不以重新註冊當作成功。

## 回復與續接

私有原始／candidate 備份（含 proprietary APK，勿公開）位於
`D:/m11q/work/seh1-lg3-source-state-20261008`。

```sh
python3 tools/legacy_seh_apn_trial.py rollback \
  --android-root /home/user/android/crdroid \
  --state-dir /mnt/d/m11q/work/seh1-lg3-source-state-20261008
```

只還原本批次已核對的檔案，移除四個本批次新增 Java source；有未知 user edit 就拒絕。
APK artifact 在 `out/lg3-wfc-gate/imsservice.apk`，strict report 同資料夾 `strict.json`。
先前 DrvFS 慢速 discovery 已終止，未用其結果；成功 discovery／strict 重建改用獨立
Linux temporary work dirs，報告與輸出留在 workspace。下一個必需步驟是使用者 build／刷機，
不是再修改 RSSI、延長 Wi-Fi 等待或重做 10/05 的設定鏡射實驗。
