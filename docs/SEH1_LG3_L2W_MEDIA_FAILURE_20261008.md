# SEH1 + LG3 實機結果：W2L 正常，L2W 後失聲

2026-10-08，接續 [SEH1 + LG3 實作批次](SEH1_LG3_STOCK_APN_CALLBACK_TRIAL_20261008.md)。
使用者已 build／刷機／完成實驗；手機目前未連接。這輪只分析提供的 archive，沒有
ADB 操作、ROM build、再刷機或 handover source 修改。

## 已確認與尚未確認

使用者觀察：通話顯示 Wi-Fi Calling，W2L 正常；另一輪 VoLTE → VoWiFi 後失聲，
再切回 VoLTE 就自動掛斷。失聲為單向或雙向尚待使用者說明，log 不能代替聽覺量測。

兩個不同原通話 session 重現後者：

| Session | L2W／Wi-Fi | 再 W2L／LTE | 自動結束 |
| --- | --- | --- | --- |
| 6 | 09:02:14.827 | 09:02:30.386 | 09:02:36.095，RTP Timeout |
| 7 | 09:03:03.922，L2W success | 09:03:08.927，W2L success | 09:03:23，RTP Timeout |

時間來自 log；手動 snapshot 標籤是完成後記錄，不當作切換開始時間。
Session 7 的原 IMS session 保持 ESTABLISHED，並更新到 networkType 18／isWifi Y。
這證明 bearer／session 控制狀態進入 Wi-Fi，不代表音訊已正常。

- Native IPsec connect／disconnect 的 `mIkeError=0`。
- L2W 與 W2L 均有 CP 的 IMS bearer／signaling-mode 控制呼叫；不能據此證明媒體送達或
  音訊處理成功。
- Native `RTP Timeout` 先出現，之後才映射為 Android reason 1401
  `CODE_EPDG_TUNNEL_REKEY_FAILURE`，`userInitiated=false`。**不能把 reason 名稱當成
  IKE rekey 實際失敗的證據。**
- Runtime 有 `M11SehRadioBridge: APN callback phone 0: immutable IMS snapshot`，所以
  handler publisher／vendor APN callback 在實驗期間確實運作。
- Runtime identity 的 telephony JAR hash 與已驗證 product 相同；IMS APK／DEX hash、
  bridge property 欄位卻為空，不能宣稱所有安裝版本都由該檔案證實。

## 排除的未證實方向

Stock `SehRadioIndication.voiceRadioBearerHandoverStatusChanged(II)V` 本身就是空方法。
因此不補猜測性的通知 forwarding。`modifyEpdg` 的 FLAG_ONEWAY stack 是 Binder advisory，
不是單憑那段 stack 就能確認的 filter 安裝錯誤。

後段 tc snapshot 在 W2L／掛斷清理之後，不能用 filter 已消失回推 L2W 當下失敗。
原 collector 又漏掉實際 `epdg1` 與 cellular root filter。現有資料不足以支持再改 APN
callback、延長 timeout、改 RSSI 或換 handover 演算法。

另發現 LinkProperties 的 MTU 值異常大（LTE 85,853,470／IWLAN 98,305,500），但正常與
失敗那幾輪均有相同值，未找到對應 `setMtu`／`EINVAL`／`EMSGSIZE` 失敗。
它是待追的相容性異常，不足以單獨解釋此次失聲；下一個 probe 會保留 kernel link MTU，
本輪不憑該欄位任意改 MTU。

## 唯一下一步：失聲但仍在 VoWiFi 的媒體觀測

保留已正常的 source，不需要重新 build／刷機。需要在原通話切入 VoWiFi、已失聲但
**尚未切回 LTE** 時，觀察 actual ePDG／rmnet 介面的媒體封包及 root／ingress redirect
filter counters，配合連續 logcat。不可把 tcpdump 不存在、權限失敗或 interface 消失
解讀為沒有 RTP。AF_PACKET 或 tc 計數也不能單獨證明 CP 已成功解碼音訊。

分流目標：ePDG 沒有媒體封包 → 遠端媒體／tunnel 上游；ePDG 有、redirect 目標沒有 →
本地 routing／redirect；目標流量有但失聲 → 再查 modem／CP／音訊處理。
必須辨認真正通話 media flow，不能把任意 UDP／背景流量當作 RTP。

新的擷取工具由 Luna 實作，設計判斷由單一 Sol medium 限縮完成；後續例行實作／驗證
回到 Luna。詳細使用方式記錄在 `SEH1_L2W_MEDIA_PROBE_20261008.md`。

## 私有證據位置

Workspace extraction：`D:/m11q/work/seh1-lg3-user-results-20261008/`，勿公開 private archive。

- `share/USER_OBSERVATIONS.tsv`：使用者操作順序。
- `share/key_timeline_redacted.txt`：6516／6545 APN callbacks；8055 IKE success；8065–8066
  L2W；8372 IKE disconnect result；8469–8470 W2L；8884 RTP timeout；8902–8903 mapped reason。
- `private/logcat_all_private.txt`：43049／43130 L2W CP control；43697 original IMS session
  updated to Wi-Fi；45273／45355 W2L CP control。
- `first_boot_log/firstboot-logcat.txt`：7279 IPsec success，7283 registration stack。
- Stock decoded local reference：
  `work/stock_telephony_common_decoded_20260929/smali/com/android/internal/telephony/SehRadioIndication.smali:2691`。

Source／product gate PASS 不等於 audio acceptance PASS；目前 L2W 驗收仍是 FAIL。
