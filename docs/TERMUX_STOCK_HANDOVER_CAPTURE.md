# Termux：Stock IMS／Wi-Fi handover 擷取

這份唯讀擷取流程用於已取得 Magisk root 的 stock CWK3 Android 12 手機，記錄 VoWiFi 通話及雙向網路切換。封包使用完整 snaplen，包含可見的 SIP 訊號與 ESP；不錄製麥克風音訊，也不會寫入 IMS 設定、音訊旗標／屬性、路由或流量控制規則。

## 安裝與先決檢查

主腳本安裝在手機的 `/data/local/tmp/capture_ims_stock_handover_termux.sh`，權限設為 root 所有、`0700`。可在 `/sdcard/Download/` 留一份備份；Downloads 是共用儲存空間，不是私密目錄。主腳本已放到目前連線的手機。這支手機不必安裝額外 Termux 套件；其他手機請先執行 `doctor`，確認該機所需指令可用。

每個命令都透過 `su -c` 以 root 執行。先在 Termux 執行必要檢查：

```sh
su -c '/system/bin/sh /data/local/tmp/capture_ims_stock_handover_termux.sh doctor'
```

以下命令皆使用安裝在 `/data/local/tmp` 的 root 私密副本。若改用 Downloads 備份，將命令中的腳本路徑換成 `/sdcard/Download/capture_ims_stock_handover_termux.sh`。

## 一次測試流程

`start LABEL [SECONDS]` 的預設時間是 900 秒（15 分鐘），可設為 60–1800 秒。開始後必須看到 `Capture ready`，或用 `status` 確認 `readiness=READY`，才開始測試；若沒有 READY，不要假設擷取已運作。即使擷取逾時自行停止，仍須執行 `stop` 和 `export` 才能完成封存。一般流程如下：

```sh
su -c '/system/bin/sh /data/local/tmp/capture_ims_stock_handover_termux.sh start stock_hotspot'
su -c '/system/bin/sh /data/local/tmp/capture_ims_stock_handover_termux.sh status'
su -c '/system/bin/sh /data/local/tmp/capture_ims_stock_handover_termux.sh mark wifi_off'
su -c '/system/bin/sh /data/local/tmp/capture_ims_stock_handover_termux.sh stop'
su -c '/system/bin/sh /data/local/tmp/capture_ims_stock_handover_termux.sh export'
```

`status` 和 `mark TOKEN` 是選用指令；TOKEN 限英數字、底線、連字號，最多 48 字元。標記不是必要步驟，不必在通話中操作。請在測試通話都結束後執行 `stop`，接著執行 `export`。即使擷取自動逾時，也要執行這兩步，才能確認停止狀態並封裝資料。

建議受測手機連上以行動網路上網的手機熱點，熱點不要使用爸爸正在撥接電話的那支手機，並一次完成以下批次；所有電話都與同一位測試對象（爸爸）通話：

1. 等待手機確實顯示 VoWiFi 圖示；開始擷取後，接聽一通來電。保持 30 秒，確認雙向都有聲音。
2. 在同一通來電中關閉 Wi-Fi，觀察 Wi-Fi 轉 LTE（W2L）30 秒；再開啟 Wi-Fi，觀察 LTE 轉 Wi-Fi（L2W）30 秒。
3. 結束來電，再於 LTE 撥出一通電話。通話 30 秒後，在同一通電話中開啟 Wi-Fi、觀察 L2W 30 秒，再關閉 Wi-Fi、觀察 W2L 30 秒；確認雙向聲音。
4. 若環境安全，可拿著手機走到訊號較弱處觀察；不需要 USB。
5. 再以 LTE 撥一通新電話，至少通話 30 秒，確認雙向聲音。
6. 結束所有通話後執行 `stop`，再執行 `export`。

分別記下來電、去電、W2L、L2W 與最後 LTE 通話的雙向聲音結果。若某階段失敗，標記該階段並先完成擷取；不要用後續重撥覆蓋失敗當下的證據。若熱點路徑與另一 WAN 的結果不同，可支持網路路徑相關性，但仍不足以單獨確認路由器功能是原因。

不要在 handover 途中執行耗時的 dumpsys。若通話失敗，可選擇記下標記；先完成 `stop` 和 `export`，再重撥。

擷取程序會以 root 背景執行，Termux 移到背景後仍可繼續；Android 省電或休眠仍可能影響 Wi-Fi，情況允許時可接上充電器。封存檔會包含電話／IP 資訊、訊號紀錄及正在使用的 IPsec key，雖然檔名標示 PRIVATE，Downloads 仍是共用空間。腳本不會自動上傳；請勿公開分享或放到 GitHub。原始資料會保留在 root 私密目錄。

## 結果解讀

擷取器顯示正常只代表收集程序運作，不代表通話或 handover 成功。先前 5 秒 probe 不構成已完整記錄的 known-good baseline。不同 WAN 通過、家中網路失敗，支持路徑受網路環境影響，但單靠此結果不能證明是路由器某項功能造成；crDroid 上的相同熱點路徑也尚未驗證。這份流程只驗證 stock CWK3，請另外比較 crDroid 結果。

這批測試要建立可比較的 stock 來電與雙向 handover 基準。若全部通過，下一步分析這份成功紀錄，再用同一個熱點與同樣流程驗證 crDroid；若 stock 仍失敗，先分析失敗當下的 SIP／媒體及網路路徑，不因此修改 crDroid。請把封存檔和各階段的實際聲音結果一起提供。

## 工具驗證（2026-10-10）

已在目前的 CWK3 手機確認背景啟動、狀態查詢、事件標記、手動停止、自然逾時停止及匯出。兩種停止方式皆得到 `READY_CAPTURE_STOPPED`、`producer_stop=VERIFIED`，且沒有殘留的 tcpdump／logcat；手機版本與 repository 腳本 SHA256 相同。POSIX 主機測試 6 項通過。

這是閒置手機上的工具測試，沒有執行實際通話或 Wi-Fi 切換；封包過濾器已由手機核心接受，但完整通話封包與 handover 成功仍須上述實驗驗證。工具測試封存檔已移回 root 私密目錄保留，不需提供這些 smoke 檔。
