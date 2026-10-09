param(
    [int]$PostCallMinutes = 5
)

$ErrorActionPreference = 'Stop'

function Save-AdbOutput {
    param(
        [string]$Path,
        [string[]]$AdbArguments
    )

    & adb @AdbArguments 2>&1 | Out-File -LiteralPath $Path -Encoding utf8
}

function Add-DeviceMarker {
    param([string]$Name)

    $marker = "${Name}_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    & adb shell su -c "log -t CODEX_VOLTE $marker" | Out-Null
    return $marker
}

function Save-Snapshot {
    param(
        [string]$Directory,
        [string]$Prefix
    )

    Save-AdbOutput "$Directory\${Prefix}_carrier_config.txt" @('shell', 'dumpsys', 'carrier_config')
    Save-AdbOutput "$Directory\${Prefix}_telephony_registry.txt" @('shell', 'dumpsys', 'telephony.registry')
    Save-AdbOutput "$Directory\${Prefix}_telecom.txt" @('shell', 'dumpsys', 'telecom')
    Save-AdbOutput "$Directory\${Prefix}_phone.txt" @('shell', 'dumpsys', 'phone')
    Save-AdbOutput "$Directory\${Prefix}_processes.txt" @('shell', "ps -A | grep -E 'imsd|imsservice|rild|epdgd'")
}

$deviceState = (& adb get-state 2>&1 | Out-String).Trim()
if ($deviceState -ne 'device') {
    throw "ADB device is not ready (state: $deviceState). Unlock the phone and confirm USB debugging."
}

$rootCheck = (& adb shell su -c id 2>&1 | Out-String).Trim()
if ($rootCheck -notmatch 'uid=0') {
    throw "Root shell check failed: $rootCheck"
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$captureRoot = "D:\m11q\work\incoming_volte_runtime\$stamp"
New-Item -ItemType Directory -Force -Path $captureRoot | Out-Null

$stdoutPath = "$captureRoot\continuous.log"
$stderrPath = "$captureRoot\continuous.stderr.txt"
$logProcess = $null

try {
    $logProcess = Start-Process -FilePath 'adb' `
        -ArgumentList @('logcat', '-b', 'all', '-v', 'threadtime') `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru `
        -WindowStyle Hidden

    Start-Sleep -Seconds 2
    $startMarker = Add-DeviceMarker 'INCOMING_CAPTURE_START'
    Save-Snapshot $captureRoot 'baseline'
    Save-AdbOutput "$captureRoot\baseline_getprop.txt" @('shell', 'getprop')
    Save-AdbOutput "$captureRoot\baseline_services.txt" @('shell', 'service', 'list')

    Write-Host ''
    Write-Host '取證已開始。請讓朋友撥電話進來，正常接聽、雙向說話，再正常掛斷。'
    Write-Host '整段期間不要切飛航模式、換 SIM、重開機或關閉 USB debugging。'
    Read-Host '通話完全結束後，回到這個視窗按 Enter'

    $endMarker = Add-DeviceMarker 'INCOMING_CALL_ENDED'
    Save-Snapshot $captureRoot 'postcall_t0'

    $ringing = Read-Host '手機有正常響鈴嗎？(y/n)'
    $answered = Read-Host '能正常接聽嗎？(y/n)'
    $heardRemote = Read-Host '你聽得到朋友的聲音嗎？(y/n)'
    $remoteHeard = Read-Host '朋友聽得到你的聲音嗎？(y/n)'
    $iconStayed = Read-Host '通話中及掛斷後，VoLTE 圖示都還在嗎？(y/n/不確定)'
    $hangupSide = Read-Host '最後由哪一端掛斷？(本機/朋友/其他)'
    $extraNotes = Read-Host '其他異常或備註（沒有可直接按 Enter）'

    @(
        "capture_started=$startMarker"
        "call_ended=$endMarker"
        "ringing=$ringing"
        "answered=$answered"
        "local_heard_remote=$heardRemote"
        "remote_heard_local=$remoteHeard"
        "volte_icon_stayed=$iconStayed"
        "hangup_side=$hangupSide"
        "notes=$extraNotes"
    ) | Out-File -LiteralPath "$captureRoot\USER_OBSERVATIONS.txt" -Encoding utf8

    Write-Host ''
    Write-Host "接下來自動觀察 $PostCallMinutes 分鐘。可以熄屏，但請勿拔除 USB。"
    Write-Host '如果 VoLTE 圖示消失，請記下手機畫面顯示的時間；不要重開機。'

    Start-Sleep -Seconds 30
    Add-DeviceMarker 'INCOMING_POSTCALL_T30' | Out-Null
    Save-Snapshot $captureRoot 'postcall_t30'

    $remainingSeconds = [Math]::Max(0, ($PostCallMinutes * 60) - 30)
    if ($remainingSeconds -gt 0) {
        Start-Sleep -Seconds $remainingSeconds
    }

    Add-DeviceMarker "INCOMING_POSTCALL_T${PostCallMinutes}MIN" | Out-Null
    Save-Snapshot $captureRoot "postcall_t${PostCallMinutes}min"
}
finally {
    if ($null -ne $logProcess -and -not $logProcess.HasExited) {
        Stop-Process -Id $logProcess.Id -ErrorAction SilentlyContinue
        Wait-Process -Id $logProcess.Id -ErrorAction SilentlyContinue
    }
}

Write-Host ''
Write-Host '取證完成。請把下面這個資料夾路徑貼給 Codex：'
Write-Host $captureRoot
