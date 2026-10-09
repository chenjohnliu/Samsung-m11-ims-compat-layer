# LEG1 + SS1 第二包：尚未證明 VoWiFi 通話來源

2026-10-04。輸入 `SHARE_THIS (6).tar.gz`、`PRIVATE_FULL_CAPTURE (4).tar.gz`，
解至 `D:\m11q\work\leg1_w2l_20261004_230423`。private 不公開。
本次只做 log 與 ADB 唯讀核對，不改 source／手機設定，不 build 或刷機。

## 這次操作與資料品質

連續 capture 起訖 marker 皆存在、stderr 空。APK DEX 與前一包相同。
CarrierConfig 實驗開關 false，override 均 null。穩定階段 telephony debug dump
逾時，因此不把該 dump 的缺少欄位當作 runtime 機制不存在。

使用者確實在 TC@4 仍 ACTIVE 時關 Wi-Fi，原 callId4／native session7 保留到
使用者主動掛斷，未見重撥。這部分操作與連續紀錄有效。

以下行號對應本包 `private/logcat_all_private.txt`：

| 時間 | 證據 | 解讀 |
| --- | --- | --- |
| 23:01:42.593 | 762：isVowifiEnabled=false、cellular IMS enabled | 撥號前未證明 WFC |
| 23:01:42.674 | 850：callId4 networkType13/isWifiN | 原通話被框架標為 LTE |
| 23:01:45.896 | 2309：TC@4 ACTIVE | 此通接通 |
| 23:02:09.184 | 4948：IMS not registered over IWLAN | 關 Wi-Fi 前未有 IMS IWLAN 註冊 |
| 23:02:09.388–.451 | 5430、5451、5587：W2L request、EPDG NOT AVAILABLE、modem ACK | 請求／ACK，不是原通話 bearer 成功證據 |
| 23:02:09.534 | 5673：data RAT18→13 | 資料／服務 RAT 回 LTE，不能單獨驗收通話切換 |
| 23:02:16.415 | Wi-Fi re-enabled | 關閉約7秒後又開啟 |
| 23:02:24.652 | 8618：REQUEST_DISCONNECT | 關 Wi-Fi 至主動掛斷約15.4秒 |
| 23:02:24.763 | 8964：userInitiated=true | 最後是本機主動結束 |

W2L 附近 APN null，相關 IPsec SM 均 Inactive。通話開始／結束均為 framework
networkType13/isWifiN。這不能作為 VoWiFi→VoLTE 成功；也不僅憑 framework
欄位反向宣稱每一瞬間的底層媒體必定都在 LTE。
媒體 stats 與正常掛斷支持原通話存續，但不證明起始接入是 IWLAN，也不量測音訊空窗。

檢查後只讀 ADB：phone idle、Wi-Fi connected、legacy property；
secims mIsEpdgConnected=false／isWifiConnected=true。沒有清 log、切網路或重開機。

## 必須更正前一包的 L2W 成功宣告

前一包 `leg1_success_20261004_224812` 曾以 VoiceCallSessionStats／資料 RAT13→18
加上 L2W request/ACK 宣告通話內 L2W。複核其原始 log 後，該結論證據不足，撤回：

- 3907、4367：TC2 建立時 isVowifiEnabled=false、networkType13/isWifiN。
- 5331：RIL DATA_REGISTRATION_STATE rat18；5537–5544：IPsec SM 仍 Inactive。
- 5649、5654、5658：同段 IMS registration technology=0(LTE)、isOnWfc=false、
  isVowifiEnabled=false；5758/5763/5766 仍相同。
- 5912、6316/6322：掛斷時通話仍被 framework 標為 LTE/non-WiFi。

因此前一包確認的是原 call session 未被意外結束、資料 RAT 與控制通知變化、
之後仍能撥 LTE；未確認真正 IMS bearer／媒體的 L2W handover。
使用者回報「圖示切換／通話未斷」保留為使用者觀察，不能直接提升為 bearer 驗收。

## 下一個界線

先停止盲目重錄 handover 或刷機。優先定位 legacy VoWiFi 註冊／bearer 與
framework transport 回報為何未形成一致的 WFC 基線；資料 RAT或圖示本身不夠。
至少取得 IMS/ePDG 註冊及原通話來源的交叉證據，才開始 focused W2L。
基線成立後，只需測一通 188，在通話中關 Wi-Fi並保持關閉至少30秒後才掛斷；
成功再做三次與真人雙向音訊驗收。
