# SIM1／SIM2 單有效 SIM：整合測試清單

範圍：同一張 SIM 單獨放在實體 SIM1 或 SIM2，都走對應插槽的 IMS、
APN callback 與通話音訊切換。**不包含兩張 SIM 同時啟用的支援**。
程式 phoneId 0＝實體 SIM1；phoneId 1＝實體 SIM2。

## 刷機前

- [ ] 自行 build 新 ROM；這次必須包含 Telecom、telephony-common 與 device 來源。
  目前手機舊 APK 還是第一槽限定，不能用它驗收 SIM2。
- [ ] 以下三項產物檢查都 PASS 才刷。SA2 gate 會拒絕舊版第一槽限定 APK；
  SEH gate 會拒絕舊版 callback；global gate 同時確認原廠 Timer F 資源。

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/sa2_telecom_audio_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
python3 tools/legacy_seh_apn_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
python3 tools/global_wfc_profile_policy.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
```

- [ ] 將新版 `D:/m11q/tools/capture_ims_media_probe_termux.sh`（v7）複製到
  手機 `/sdcard/Download/`。不要使用 `--start-sae`，也不用再設定 SA2 開關。
- [ ] 先用目前已有成功經驗的同一張台灣大哥大 SIM，避免同時更換電信與插槽。
  其他電信可在兩槽都通過之後補測，不以放行設定代替實測。

## 每個插槽各跑一輪

先完整測 SIM1；掛斷所有通話、關機，把同一張 SIM 移至 SIM2，再開機跑相同項目。
另一槽保持空；第一輪不要熱插拔、不要在通話中切 SIM，也不用為此清除資料。
更換插槽後確認目前那張 SIM 的 VoLTE／Wi-Fi Calling 開關、預設通話／行動數據選擇；
不要假設前一槽的設定會自動套用。

| 項目 | SIM1 | SIM2 | 通過條件 |
| --- | --- | --- | --- |
| 開機、LTE 註冊與數據 | ☐ | ☐ | 開機後能上網、無 ePDG／IMS crash |
| LTE 撥出／來電 | ☐ | ☐ | 各一通，雙向交談 ≥30 秒 |
| 開 Wi-Fi，確認 WFC | ☐ | ☐ | Wi-Fi Calling 可註冊，直接撥出／接聽 Wi-Fi 通話都有聲音 |
| LTE → Wi-Fi → LTE | ☐ ×3 | ☐ ×3 | 同一通電話不斷、不重撥；每次切換後雙向交談 ≥30 秒 |
| Wi-Fi 起始 → LTE → Wi-Fi | ☐ | ☐ | 從真正 Wi-Fi 通話開始，手動關 Wi-Fi後仍延續，再開回也有聲音 |
| 弱 Wi-Fi 自動切回 LTE | ☐ | ☐ | 與真人通話、走離訊號範圍，不手動關 Wi-Fi，雙向聲音持續 |
| 切換後掛斷、再撥 LTE | ☐ | ☐ | 新通話正常；無 487／5065、無卡住通話或持續靜音 |
| SMS、門號顯示與重開機 | ☐ | ☐ | LTE／Wi-Fi 連線下各收發一則簡訊；檢查門號；正常重開機後再測一輪基本通話 |

重點順序：兩槽的基本 LTE／WFC → LTE 起始的三次 round-trip → Wi-Fi 起始與弱訊號 → 其餘。
任何切換失敗，就保留那一通的紀錄，不要在同一通裡連續亂切或用手動 SAE 補救。

音訊目標：每方向停頓不超過 2 秒、無永久單向／雙向靜音。
記下實際聽到的停頓估計，不能以圖示改變或重新註冊成功當作通話延續的證據。
188 可以先確認接通與接收聲音；**至少一通真人通話**確認對方也聽得到你。
簡訊測試保持行動網路開啟；收到簡訊本身不代表它一定經由 IMS SMS。
門號來源若 SIM／電信／IMS 都未提供，仍可能顯示未知，請和音訊測試分開記錄。
不要為了本輪實撥緊急號碼。

## LTE 起始 round-trip 的採集方式

1. 先確認 Wi-Fi Calling 能正常註冊，再關 Wi-Fi，等 LTE 就緒並撥通電話。
2. 保持同一通 LTE 電話，在 Termux 執行：

   ```sh
   bash /sdcard/Download/capture_ims_media_probe_termux.sh --handover-check
   ```

3. 按畫面提示開 Wi-Fi，切到 Wi-Fi Calling 後按 Enter；等提示再關 Wi-Fi並按 Enter。
   保留原通話，等後續觀察完成再掛斷。腳本錄紀錄，不替你切換 Wi-Fi或送音訊要求。
4. 三次各跑一份，不重用已存在的輸出目錄。
   若腳本的等待時限內未完成 Wi-Fi 註冊，保留輸出並記為「尚未切換」，不要當作音訊 PASS。
5. 將每次 `PRIVATE_ALL` 私下壓縮傳回，另附插槽、撥出／來電、切換方向、停頓與雙向聲音結果。
   紀錄含門號、網路與通話資料，不要 push 到 GitHub。

此腳本的提示是 **LTE 起始**；不要拿它的步驟標記去描述 Wi-Fi 起始或自動弱訊號測試。
這兩項可另行連續錄 logcat（不清 log、不手動 SAE），註明開始及切換時間；
需要協助採集時先告訴我是哪個插槽與哪個案例。

VoWiFi 圖示在切回 LTE 後消失、稍後回來可能是既有 Samsung re-entry timer。
請記錄等了多久、是否仍能打電話；不要只因圖示暫時消失判定音訊失敗。
Timer F 已恢復原廠 128 秒，遇到 P-CSCF 無回應時註冊等待也可能比 16 秒版本久。

## 回報格式

```text
ROM／刷入日期：
插槽：SIM1 / SIM2（另一槽空）
電信：
測試：LTE起始第1/2/3次 / Wi-Fi起始 / 弱訊號 / 來電 / SMS
是否原通話、不重撥：
LTE→Wi-Fi 停頓：約___秒；我聽對方___；對方聽我___
Wi-Fi→LTE 停頓：約___秒；我聽對方___；對方聽我___
切換後持續交談：___秒
掛斷後新的LTE電話：
SMS、門號與圖示恢復情況：
紀錄壓縮檔／實驗時間：
```

雙 SIM 同時啟用不是本輪驗收。若要確認保護條件，只檢查不 crash／不取另一槽 APN，
不要期待本版雙 SIM Wi-Fi Calling／handover；不要以兩張都插著的結果驗收單 SIM 支援。
