# 對話改動、全電信範圍與 Git 推送盤點 — 2026-10-09

> 後續更新：使用者已要求僅做本機 commit、不 push。7 個 WSL IMS repo
> 已提交；相容層與診斷原始碼亦納入本機 checkpoint。提交清單及 UI 查核見
> [LOCAL_IMS_COMMITS_AND_UI_FINDINGS_20261009.md](LOCAL_IMS_COMMITS_AND_UI_FINDINGS_20261009.md)。
> 下文保留提交前的盤點結果；「未提交」描述不代表最新 checkpoint 狀態。

## 結論

1. 依使用者最新要求，SA2 音訊切換與 SEH1 APN callback 已移除台灣大哥大
   46697 allowlist，套用到 WSL source；所有有效 MCC/MNC 可通過該兩層身分檢查。
2. 保留 M11、legacy IWLAN、原 opt-in 開關、單一有效 SIM／slot 0、一般
   已接通音訊通話、訂閱一致性及 stale-event 防護。沒有開放雙卡、slot 1、
   緊急／多方／視訊通話，沒有強制各電信提供 IMS 或繞過 provisioning。
3. 非 ROM 測試與 source gate 通過。**尚未為本次全電信改動 build／刷機。**
   目前手機仍是先前 TWM 測試版本；全電信可執行不等於各電信已實測。
4. **這段對話的改動沒有全部推送。** 相容層 repo 有大量未追蹤 source／工具／
   測試／文件，WSL 有 9 個 dirty repo。本輪僅修改 source 與盤點，沒有 commit／push。

## 本次實作與驗證

- `SamsungImsAudioHandover` 不再只接受 46697；`SamsungImsAudioTransition`
  只檢查 slot 0 存在有效 5／6 位 MCC/MNC，其他 slot 無有效 operator。
- `M11SehRadioBridge.currentIdentity` 與 `M11SehApnPolicy.fallback` 改為接受
  有效 operator；仍由同一 subId／operator 的實際 provider／唯一 IMS profile
  提供 APN，不硬編碼其他電信 APN、IP 或 credentials。
- 更新 SEH source pins、可重現 prepare／apply 流程與有 hash 驗證的升級功能。
  原始 rollback backup 保留；升級前 helper／manifest 另外保存。
- Telecom product gate 新增 `SA2 carrier-neutral slot0 scope` marker；SEH product
  gate 要求定義 `validOperator` 方法，避免舊 TWM-only 產物被当成新版。
- 54 個 SA2 host assertions、10 組 SEH bridge host scenarios、8 個 SA2 patcher
  tests、15 個 SEH staging／DEX tests 通過；四個 Telecom 類別以現有 Android13
  API 產物獨立編譯通過。不是 Android ROM build。
- SA2／SEH WSL source gate 均 PASS，保留現有 Wi-Fi 關閉暫緩、RSSI、TEPDG timer。

私有 revision backup：

- `D:/m11q/work/sa2-all-carrier-revision-20261009`
- `D:/m11q/work/sa2-all-carrier-product-marker-20261009`
- `D:/m11q/work/seh1-all-carrier-revision-20261009`

原始可還原 state 仍位於：
`work/sa2-telecom-audio-port-20261009/active-source-backup` 與
`work/seh1-lg3-source-state-20261008`。不要在 public Git 放這些私人工作目錄。

## 對話從最初到目前的改動分類

此表依對話內容、現有 source／Git 與 checkpoint 文件重建；它不是每次臨時
實驗的完整 Git commit 歷史，也不把後來還原或停用的試驗寫成目前啟用功能。

| 階段 | 改動／結果 | 目前狀態與推送證據 |
| --- | --- | --- |
| crDroid IMS restoration | Samsung API／permission／Binder、framework／netd／Telephony 相容接點與來源回放文件 | 多個 WSL repo 仍 dirty，沒有完整推到各自 GitHub fork |
| VoWiFi availability 與 carrier ID 1888 | 從臨時 carrier-ID 配置移至 Taiwan PLMN vendor overlay | 先前 device commit `d11cbe58` 在已驗證遠端歷史；目前 overlay 又有尚未提交的 legacy 調整 |
| 487／5065 與卡在撥號 | 失敗通話的狀態清理；idle fresh-bearer/disallow workaround 曾成功，但 active WFC 會中斷 | workaround 舊提交已推；後續 telephony 本機清理／handover hunks 仍未提交。舊 workaround 不是現在成功通話延續的機制 |
| AP-assisted active W2L 試驗 | Wi-Fi disabling qualified-network 通知、來源消失排序／保留、IMS IP continuity 與定位工具 | EC2／BV1 等試驗文件與轉換工具仍未追蹤；目前採 legacy，相關 opt-in 不代表啟用 |
| 對照 stock，改 modem-led legacy | LEG1 legacy mode、Samsung native handover；SS1 補 ServiceState API；LG2 修正 ePDG interface prefix | 對應工具／pins／文件未提交，WSL framework／device 調整尚未完整推送 |
| 首次開機 WFC 與 APN callback | LG3 讀 Android 有效 SIM WFC 設定；SEH1 重建 stock callback ABI、APN snapshot 與受限 SELinux | 已套用並實測，但 tools／Java／device source 仍有未提交內容 |
| 來電 VoWiFi 音訊 | 原 MT post-MODE_IN_CALL stock callback 與 device resource／SELinux | Telecom `66d3d91d`、device `29fc1533` 已在遠端；保留此既有功能 |
| L2W 無聲診斷 | 唯讀 RTP／tc capture；一次性 stock SAE request 證明可恢复音訊 | 成功手動實驗不是自動切換最終方案；工具在 D 槽，部分不在任何 Git repo |
| 自動 stock 音訊 port（SA2） | Telecom 驅動 STOP／SAE／INFORM 與 CPVE，保留同一通話 | source 編譯與 host tests 通過；188 約 1 s／0.5 s、真人雙向通話成功；新增四檔 Telecom 變更仍未提交／推送 |
| 弱 Wi-Fi 與圖示恢復 | 真實通話維持聲音；VoWiFi 自行恢復，TEPDG 等待有明確 log | 只記錄結果，沒有為圖示新增延遲或重試機制；新文件未提交 |
| 最新全電信範圍 | 同步移除 SA2／SEH1 的 46697 限制，新增回歸測試與新版 gate | 已套用 WSL、source gate PASS；尚未 build／刷機／commit／push |

## GitHub 實際遠端核對

以下使用 `git ls-remote` 讀取當下遠端，而不是只信本機 remote-tracking refs。

| Repo／分支 | GitHub branch HEAD | 核對結果 |
| --- | --- | --- |
| Samsung-m11-ims-compat-layer／main | `7f1a01a9de6a5b2dfd70b199ab7cbac8020f5dfc` | 與本機 HEAD 相同；working-tree 新改動不在該提交 |
| android_device_samsung_m11q／m11q-volte | `9ce7a0bac0e14bf820cb6deb68e9ebac061056ab` | 與本機該分支相同；5 檔本機修改仍未提交 |
| android_packages_services_Telecomm／m11q-vowifi-audio-path | `66d3d91d238436c9a04cd4b653f3db02db4f901e` | 先前 MT 修復已推；目前 SA2 尚未提交 |
| android_kernel_samsung_sdm450／lineage-20 | `9f3c4fedd9ef626303987cef1abfaf971efce694` | HEAD 已推；4 檔本機 build compatibility 修改未提交 |
| proprietary_vendor_samsung_m11q／13-64 | `6a8923918e90b734913cab84bc8ac7022a2dc143` | 本機 Git tracked tree 乾淨且分支一致；不保證其他目錄內被忽略的生成 APK 已發布 |

相容層盤點時已有 6 檔 tracked 修改與 114 個 untracked 檔案（本次報告與後續
文件整理前的數量）：8 contracts、28 docs、6 Java source、50 tests／test fixtures、
22 tools。不能用「branch 與 GitHub 相同」推論這些 working-tree 檔案已上傳。

## WSL 全部 repo 盤點

掃描 `repo list` 的 1,210 個專案，另外找到 device／vendor／kernel custom repo
及 manifest repo，共 **1,214 個 Git checkout**，無掃描錯誤。
逐一檢查 status、local branches／upstream、cached remote 覆蓋及 manifest pin。
正確 peel Android annotated release tags 後，沒有 HEAD 脫離 cached remote／
manifest baseline 的候選項，也沒有 local branch ahead／gone／無 upstream。
這是本機全量盤點；不是對 1,214 個 upstream 各自做 GitHub live 查詢。
個人 repo 的 live 查詢範圍見上表。

| 有未提交內容的 WSL repo | 主要內容 | 推送前必要處理 |
| --- | --- | --- |
| device/samsung/m11q | legacy／SEH flags、carrier overlay、受限 SELinux | 用現有個人 origin，先整理依賴與本機修改 |
| frameworks/base | Samsung API／permission／network-management、ServiceState 等 | detached HEAD，只有 crDroid upstream remote，需個人 fork／分支或可回放 patch |
| frameworks/opt/net/ims | MmTelFeatureConnection IMS bridge 接點 | detached HEAD，只有 upstream remote，需發布位置 |
| frameworks/opt/telephony | RIL／SEH Java、DataNetwork／controller、call-state 清理與 tests | detached HEAD，只有 upstream remote，需發布位置 |
| packages/services/Telecomm | SA2 的兩個 hooks＋兩個 helper | 已有個人 remote／分支，近期變更未提交 |
| packages/services/Telephony | WFC resource、CarrierConfigLoader／shell 診斷等 | detached HEAD，只有 LineageOS upstream remote，需發布位置 |
| system/netd | Samsung network-management Binder 接點 | detached HEAD，只有 upstream remote，需發布位置 |
| kernel/samsung/sdm450 | link／LLVM build compatibility 4 檔 | 與 IMS 不同範圍，另行 review，不混入音訊提交 |
| prebuilts/clang/host/linux-x86 | untracked clang-latest 工具鏈目錄 | 本機 compiler 安裝，不能當 IMS source 整包推送 |

完整私人 inventory：`D:/m11q/work/crdroid-git-audit-verified-20261009.json`。
可重跑的唯讀盤點工具：`D:/m11q/tools/audit_crdroid_repos.py`。
除上述 9 個以外，其他 1,205 個 checkout 在掃描時 status 乾淨。

## 不在 Git／刻意不發布的項目

`D:/m11q/tools` 不是此相容層 repo 的一部分，內有 collector、packet summarizer、
one-shot Java helper／tests 及這次盤點工具；目前不能宣稱它們已隨 repo 推送。
Private log ZIP／PCAP、stock decoded trees、Samsung 輸入 APK／JAR、生成 binary、
簽名材料與本機 backups 不應自動加入公開 Git；需要記錄可重現輸入版本而非
將所有本機資料直接上傳。

## 下一個交付界線

使用者手動正常 ROM build 後，在相容層 repo 執行：

```sh
python3 tools/legacy_seh_apn_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
python3 tools/sa2_telecom_audio_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
```

兩者 PASS 再依原流程刷機；沿用 `persist.sys.m11_ims_audio_port=stock1`。
agent 沒有執行 ROM build，也沒有改手機的 Wi-Fi／服務／persist gate。

Git 發布仍需將相關 source、工具和文件整理成提交；五個沒有個人 remote 的
framework／service repo 必須先決定 fork 或 patch-series 的發布方式。本輪
要求是擴大範圍並核對推送狀態，不把未知來源或其他任務的 dirty 內容直接
commit／push 到 upstream，也不在沒有指定的情況下建立新的 GitHub repositories。
