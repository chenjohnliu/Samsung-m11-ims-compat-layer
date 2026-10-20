# Samsung Galaxy M11（m11q）IMS 除錯手冊

本手冊適用於 CherishOS、crDroid 與相關 Android 13 版本。這是一套可由工程師自行操作的人工流程，不需要 AI；判讀 log、核對 API 與判斷因果仍須由維護者完成。請依照每個案例的證據追查，不要假設某個電信業者專用的修正適用所有網路。

- [English IMS debugging runbook](IMS_DEBUGGING.md)：完整的收集、故障分類、API 核對、實驗與驗收步驟。
- [問題回報模板](ISSUE_TEMPLATE.md)：記錄重現步驟、artifact、第一個 fatal、可信度與驗證矩陣。
- [Jio M115F 案例](cases/JIO_M115F.md)：保留原始 missing-API 診斷與 2026-10-20 測試者回報結果。

## 快速開始

先記錄 ROM/來源版本、實際測試時間、SIM/電信業者、APN 與穩定的重現步驟。確認 ADB 選到正確手機後，從本 repository 的根目錄執行唯讀收集工具，保存目前可取得的狀態與 log：

```text
python tools/collect_ims_debug.py --serial SERIAL --output PRIVATE_DIRECTORY
```

只有在需要較完整資料且同意收集時才加上 `--bugreport`：

```text
python tools/collect_ims_debug.py --serial SERIAL --output PRIVATE_DIRECTORY --bugreport
```

輸出目錄必須尚不存在。工具不需要 root，不會清除 log、重啟手機或切換無線狀態；ADB 權限或系統版本可能限制可取得的資料。一般主機端測試共有 7 項，使用模擬 ADB 並已通過；**尚未在實際手機測試**。這不等於 collector 已通過裝置端驗證。也可以完全略過工具，依英文手冊的人工 `adb` 步驟收集資料。

先保存原始輸出在 repository 以外的私人目錄，再檢查並另外製作遮蔽版本。Windows 輸出會繼承父目錄的存取權限；工具不會另設 Windows ACL，請選擇只有你能存取的私人位置。log 與 bugreport 可能含 IMSI、IMEI、電話號碼、位置、Wi-Fi 資料、通話或簡訊內容及 APN 機密。請勿將未遮蔽的原始資料直接放入公開 issue 或 Git history；工具不會自動去識別化。

## 證據與案例狀態

Jio 測試者於 2026-10-20 回報，先前提供的 `20261019-1423` 修正版可使用 VoLTE 與 VoWiFi。這是已記錄的測試者功能回報，不是所有 IMS 功能或所有電信業者的認證。測試裝置的安裝 SHA-256、fresh crash buffer、簡訊、來電/去電細節、重開機、handover 與長時間穩定性均未提供。詳見[Jio 案例](cases/JIO_M115F.md)。

除錯時請分開標示 **CONFIRMED（已確認）**、**INFERRED（推論）**、**UNVERIFIED（未驗證）**。先找每個 process 最早相關 fatal，保留 logcat 與 DropBox 的時間順序，再依完整 owner、method descriptor、static/instance、權限、subId/phoneId 與目標 runtime classpath 判斷 API 問題。不要只依靜態掃描筆數、單一錯誤行或來源樹中的符號就認定根因。手冊包含可區分假設的實驗和人工建置/裝置驗證步驟；ROM build 由維護者手動執行。
