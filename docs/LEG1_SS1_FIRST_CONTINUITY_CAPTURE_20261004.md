# LEG1 + SS1 首批通話延續紀錄

2026-10-04，M11／台灣大哥大 46697。使用者回報 VoWiFi↔VoLTE 都未斷話。
本文件分開記錄使用者觀察與 capture 可證實的範圍，不宣告完整驗收。

## 版本與完整性

輸入為 `SHARE_THIS (5).tar.gz` 與 `PRIVATE_FULL_CAPTURE (3).tar.gz`，
解至 `D:\m11q\work\leg1_success_20261004_224812`，private 不公開。
連續紀錄開始／結束 marker 皆存在，logger stderr 空。
`USER_OBSERVATIONS.tsv` 只有 `leg1_w2l1` 標籤，備註空白；標籤不是成功證據。

實機 snapshot 的 `telephony_debug.txt` 1066–1067 顯示 `isInLegacy=true`、
`IWLAN operation mode=legacy`。CarrierConfig slot 0 的 EC2/BV1 flag=false，
persistent/temporary override 均 null。APK DEX 為已知 EC2-r2／BV1／IMS bridge。
`rmnet_data1` 是 snapshot 的 IMS 介面；`epdg_data*` 皆 DOWN。

手機 collector 尚為舊版，runtime identity 沒有新增 mode／framework hash 欄位；
模式由 snapshot 證實。測試前後只讀 ADB 核對 mode/label 為 legacy/legacy-r1，
framework SHA-256 為 `3e9fe197c7e206435020c2d8af8f81213dba3696e6f1aebe2ae6563e8f6cff42`，
與已通過 SS1 packaged gate 的新輸出一致；ADB crash buffer 未見紀錄。
下次收集可換最新版 collector，不需為此重 build 或刷機。

## 實際時序

以下行號全部對應 private `logcat_all_private.txt`，不公開電話、位址或 raw SIP。

| 時間 | 事件 | 證據 |
| --- | --- | --- |
| 22:44:38.816 | 第一通 LTE 基線 ACTIVE | 2675；建立 2158，結束 2949，本機掛斷 2807 |
| 22:45:19.651 | 第二通 LTE 通話 ACTIVE | 4367，建立 3880；ALERTING 時 networkType13/isWifi N 為 4311 |
| 22:46:04.382–.439 | 第二通仍存續，RIL 資料 RAT 與 voice RAT 統計轉 IWLAN | 5331–5332、5361–5362 |
| 22:46:04.813–.826 | EPDG AVAILABLE 通知與 modem ACK；L2W trigger | 5506–5507、5556–5558；5548、5565 |
| 22:46:11.097 | 使用者主動掛斷第二通 | REQUEST_DISCONNECT 5899；後續 hangup 5903、5907–5912 |
| 22:46:11.273 | 第二通 DISCONNECTED | 6475；CODE_USER_TERMINATED/userInitiated=true 6322 |
| 22:46:22.820 | Wi-Fi disable，已無上述通話 | 8189 |
| 22:46:23.001 起 | idle W2L、EPDG NOT AVAILABLE、modem ACK、RAT18→13 | 8580、8599/8603、8779–8782、8896、8917 |
| 22:46:29.588 | 第三通 LTE ACTIVE | 建立 9801、ACTIVE11597，使用者掛斷12092、結束12680 |

共 3 通獨立電話，第二通包含通話內 L2W request與資料 RAT變化，但後續複核
未證明真正 IMS bearer切換。22:46:05.559 的再次 L2W trigger 沒有另一個
RAT 轉換或新通話，不能多算一次成功。

第二通 Android callId2／session object 保留，掛斷 native session8；
切換期間沒有新 createConnection 或另一次 INVITE。結束由本機 REQUEST_DISCONNECT
先發生，之後才送 BYE（5948），不是先前的 remote BEARER_RELEASED 斷話。
UA handle16917 為輔助證據，不能單靠它判定 session continuity。

CP media statistics（6021–6023）顯示掛斷前 TX/RX 有收發、timeout=0，
但不提供可直接驗收的音訊空窗，也不能取代雙向可聽的人工確認。
此通 L2W 後約 7 秒就自行掛斷，尚未完成轉換後至少 30 秒的驗收。

## 結論界線

**後續複核更正：撤回本文件先前「通話內 L2W 已確認」的宣告。**
同一時段 IMS technology=LTE、isOnWfc=false、isVowifiEnabled=false，
資料 RAT18與 L2W request/ACK 不能單獨證明 IMS bearer／媒體的 handover。
完整行號見 [第二包與前一包更正](LEG1_SS1_W2L_SAMPLE_NOT_ON_WFC_20261004.md)。

- **已確認**：legacy/SS1 部署；本 capture 內原通話保留到主動掛斷；最後
  idle W2L 後仍可建立 LTE 通話。未見此批的 487／5065 撥號失敗。
- **使用者回報**：兩個方向都未斷線。仍待補充切換時間／音訊觀察。
- **這包尚未證實**：通話內 VoWiFi→VoLTE；3 次獨立 W2L；音訊空窗 <=2 秒；
  切換後 30 秒雙向交談；走出 Wi-Fi 範圍與其他 carrier。
- **不能宣稱已重現全部 stock 時序**：本 capture 的可見 IPC 為 NET_REGIST
  EPDG AVAILABLE/NOT AVAILABLE 與 ACK，未見可獨立核對的 DATA_HANDOVER result，
  也沒有足夠 IKE DELETE/cleanup 時序。不能把 ACK 單獨當成 bearer handover 成功。

保留目前 source，不新增修補、不要求重 build。先釐清實際 WFC 註冊基線，成立後才補
「已註冊 VoWiFi 的原通話中關 Wi-Fi，切到 LTE 後雙向交談至少 30 秒」；
連續收集 logs，中途不 dump／重開機／切飛航。先一通確認，再按既有三次與
最後 LTE 回歸要求驗收，不必重做已確認的整套 L2W 分析。
