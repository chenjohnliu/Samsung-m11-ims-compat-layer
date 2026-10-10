# Stock 基準與 crDroid 驗證狀態 — 2026-10-10

後續更新：17:47 crDroid 熱點測試由使用者確認通話項目 PASS；剩餘圖示已完成純 SystemUI source 修正，但尚未 build／刷入。詳見 [本輪驗證與圖示修正](CRDROID_HOTSPOT_HANDOVER_PASS_20261010.md)。下列 ZIP 與來源檢查描述的是該測試版，不代表其中已含後續圖示修正。

## crDroid 來源與產品閘門

目前來源、產品及現有 OTA 的 IMS 相關內容檢查均已通過。沒有執行 ROM build；這些結果不等於實機通話已驗收，也不涵蓋 ZIP 簽章或整份 ROM 的所有元件。

- WSL 來源閘門：LG3＋SEH、global WFC、SA2 均 PASS。
- `out/target/product/m11q` 的三個產品閘門均 PASS。已驗證的 Telecom APK SHA-256 為 `ccb34dc82f53b5547e2f2c3133d272e43fb483197681bac9c247f4607f7055c8`；`telephony-common.jar` SHA-256 為 `69236ab75c2b8613d111acf5d2624d936bdb6f9938c7b55c7b1ef8fd1d464794`。
- WSL `test_build_imsservice.py` 的 16 項測試全數通過；timer/global/SEH/LG3/SA2 相關測試共 77 項通過（需設 `PYTHONPATH=tests`）。SIM slot checker 的 80、13、11 項檢查均通過，SA2 Android API 編譯檢查也通過。
- 現有 `crDroidAndroid-13.0-20261009-m11q-v9.20.zip` 的 9 個檔案與產品目錄逐一雜湊比對全部 PASS：imsservice、EpdgService、Telecom、telephony-common、framework、三份 build properties 與 vendor CarrierConfig overlay。確認既有 SA2 音訊修正沒有在這份 ZIP 遺漏。
- ZIP SHA-256：`7af3dd13323bb5e88051b849ed5b56b6456dd8687e2d925efb72c747e707ee14`。原檔位於 `/home/user/android/crdroid/out/target/product/m11q/`；完整比對紀錄位於 `D:\m11q\work\stock_exit_readiness_20261010\ota_verify_final\verification.json`。
- 已將相同 ZIP 複製至 `D:\m11q\verified_roms\20261010-handover-reference\crDroidAndroid-13.0-20261009-m11q-v9.20.zip`，複本 SHA-256 相同；此為既有 ROM，不是本輪重新 build。
- 新增的離線 OTA 比對工具 `tools/verify_ims_ota.py` 有 7 項測試通過；只解開並唯讀解析 OTA 內容，不 build、不掛載、不刷機。

本輪未新增 IMS 執行期 workaround，也未改 Android ROM source。實作限於歷史中間 APK 的不可直接部署標示、離線 OTA 比對工具與驗證文件；這些工具修改不需要重新 build 已核對的 ROM。

`tools/build_imsservice.py` 的 strict PASS 代表該歷史中間產物符合自己的 pin，不代表可直接部署。它保留 BU1 的 Timer F 實驗值，應使用完成 LG3 還原的最終 APK。BU1 轉換與歷史 pins 保留作為可重現鏈的一部分。最終產品需通過 SEH1/LG3、global WFC 與 SA2 三個產品閘門；來源或產品閘門通過不構成執行期媒體品質保證。

## Stock CWK3 的來電與 handover 基準

2026-10-10 這批 stock 測試建立了目前 crDroid IMS／來電 handover 的比較基準：

- 來電於 13:32:55 到達，13:32:59 建立通話。
- Wi-Fi 關閉後，13:33:07 完成 W2L；再次開啟 Wi-Fi 後，13:33:41 完成 L2W。通話維持至 13:33:56，使用者確認雙向音訊正常。
- 最後的 MO 通話在弱訊號 W2L 後啟動約 120 秒的 TEPDG timer。Wi-Fi 返回時仍須等待；timer 到期後，在通話結束通知之前即啟動 L2W，完成回報落在掛斷後。因此不是「必須掛斷才允許 L2W」。
- 最初解析結果缺少 MT INVITE/BYE；使用未修改的 reader 補查實際動態連接埠後找到資料。成功 MT 與先前失敗的 stock 通話，都呈現 UDP／Via UDP INVITE → TCP／Via TCP UE responses 型態；單憑這個相同型態不能解釋失敗原因。
- 8 個 stock 二進位檔均已保留，雜湊與原紀錄相同。

因此，目前 IMS／來電 handover 基準已有足夠 stock 證據，不需要為了這個基準再做一輪 stock 擷取。這不代表其他電信商、其他網路路徑或未來的 stock 測試都已驗證。

## 下一批 crDroid 實機驗證

接下來只需對目前已通過產品閘門的 crDroid build 做一批對照測試，使用與 stock 相同的行動網路熱點；維持原本自動 handover 行為，不更改「連上 Wi-Fi 後強制 LTE→Wi-Fi」之類的設定，也不要使用手動 SAE 啟動。依序完成：

1. 接聽一通 MT 來電，確認接通及雙向音訊；同一通電話中測 W2L、再測 L2W。每個階段保持至少 30 秒並記錄雙向音訊。
2. 以 LTE 撥出一通 MO 電話，確認接通及雙向音訊；同一通電話中測 L2W、再測 W2L。每個階段保持至少 30 秒並記錄雙向音訊。
3. 在適合且安全的環境用同一通 VoWiFi 電話走到較弱訊號處，再返回；記錄 handover 與音訊狀態。保持通話並等待現有 TEPDG timer 視窗（本次 stock 約 120 秒；其他電信不硬編碼此值），區分正常等待和切換後失聲。掛斷後關閉 Wi-Fi，再用 LTE 建立一通新電話並確認雙向音訊。

每次切換均要求原通話不斷線、不重撥，恢復後雙向交談至少 30 秒；請回報切換時的實際音訊停頓，目標不超過 2 秒。若同一熱點上 crDroid 失敗，依這份 stock 成功基準定位軟體差異；若熱點正常、只有家中 Wi-Fi 失敗，優先分析家中網路／ePDG 路徑，不新增猜測性的 IMS workaround。

使用上述已核對的 ZIP 即可進行這批測試。若重新 build 或換用另一份 ZIP，重新執行產品閘門與 OTA 比對；不要把本次 PASS 沿用到不同的刷機包。此輪目的是區分 crDroid 軟體差異與家中網路問題；失敗時優先收集 crDroid 紀錄，搭配已保存的 stock 成功紀錄及二進位檔離線比對，不預設要求再刷回 stock。
