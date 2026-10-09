param(
    [string]$OutputRoot = "D:\m11q\work\crdroid_mt_vowifi_runtime"
)

$ErrorActionPreference = "Stop"

function Save-AdbOutput {
    param(
        [string]$Path,
        [string[]]$AdbArguments
    )

    & $script:AdbPath @AdbArguments 2>&1 |
        Out-File -LiteralPath $Path -Encoding utf8
}

function Add-CaptureMarker {
    param([string]$Name)

    $marker = "${Name}_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    & $script:AdbPath shell log -t CODEX_MT_WFC $marker 2>$null | Out-Null
    return $marker
}

function Save-RegistrationSummary {
    param([string]$Path)

    Save-AdbOutput $Path @(
        'shell',
        "dumpsys secims | grep -E 'SIM slot:|onRegistered: RAT =|updateRegistration:.*rat=' | tail -n 40"
    )
}

function Redact-Line {
    param([string]$Line)

    $result = $Line
    $result = $result -replace '(?i)(sip:|tel:)[^ >;]+', '$1[redacted]'
    $result = $result -replace '(?i)urn:gsma:imei:[^, ]+', 'urn:gsma:imei:[redacted]'
    $result = $result -replace '(?<![0-9A-Fa-f])\+?\d{9,15}(?![0-9A-Fa-f])', '[redacted-number]'
    $result = $result -replace '(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)', '[redacted-ipv4]'
    return $result
}

$script:AdbPath = (Get-Command adb -ErrorAction Stop).Source
$deviceState = (& $script:AdbPath get-state 2>&1 | Out-String).Trim()
if ($deviceState -ne 'device') {
    throw "ADB device is not ready (state: $deviceState). Unlock the phone and confirm USB debugging."
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$captureRoot = Join-Path $OutputRoot $stamp
$shareRoot = Join-Path $captureRoot 'SHARE_THIS'
$privateRoot = Join-Path $captureRoot '_PRIVATE_DO_NOT_SHARE'
New-Item -ItemType Directory -Force -Path $shareRoot, $privateRoot | Out-Null

$rawLog = Join-Path $privateRoot 'tagged_runtime_private.log'
$rawError = Join-Path $privateRoot 'tagged_runtime_private.stderr.txt'
$logProcess = $null

try {
    $fingerprint = (& $script:AdbPath shell getprop ro.build.fingerprint 2>&1 | Out-String).Trim()
    $incremental = (& $script:AdbPath shell getprop ro.build.version.incremental 2>&1 | Out-String).Trim()
    $securityPatch = (& $script:AdbPath shell getprop ro.build.version.security_patch 2>&1 | Out-String).Trim()
    $packagePath = (& $script:AdbPath shell pm path com.sec.imsservice 2>&1 | Out-String).Trim()
    $rootState = (& $script:AdbPath shell su -c id 2>&1 | Out-String).Trim()

    @(
        "captured_at=$(Get-Date -Format o)"
        "build_fingerprint=$fingerprint"
        "build_incremental=$incremental"
        "security_patch=$securityPatch"
        "imsservice_path=$packagePath"
        "root_available=$($rootState -match 'uid=0')"
    ) | Out-File -LiteralPath (Join-Path $shareRoot 'runtime_identity.txt') -Encoding utf8

    Save-RegistrationSummary (Join-Path $shareRoot 'registration_before.txt')
    Save-AdbOutput (Join-Path $privateRoot 'audio_before.txt') @('shell', 'dumpsys', 'audio')

    $logArguments = @(
        'logcat', '-v', 'threadtime', '-T', '1',
        'CODEX_MT_WFC:V',
        'M11qMtMedia:V',
        'ImsIncomingCall:V',
        'CallStateMachine:V',
        'ResipVolteHandler:V',
        'ResipMediaHandler:V',
        'StackIF:V',
        'UserAgent:V',
        'M11qSveDiag:V',
        'SecVideoEngineImpl:V',
        'AudioFWInterface:V',
        'AudioPolicyManager:V',
        'AudioFlinger:V',
        '*:S'
    )

    $logProcess = Start-Process -FilePath $script:AdbPath `
        -ArgumentList $logArguments `
        -RedirectStandardOutput $rawLog `
        -RedirectStandardError $rawError `
        -WindowStyle Hidden `
        -PassThru

    Start-Sleep -Seconds 2
    $startMarker = Add-CaptureMarker 'MT_VOWIFI_CAPTURE_START'

    Write-Host ''
    Write-Host '擷取已開始。請先確認 VoWiFi 圖示仍在，再用公司話機打到手機。'
    Write-Host '接聽後正常說話；若無聲，請不要提早掛斷，等待它自行結束。'
    Write-Host '測試期間不要切換 Wi-Fi、行動數據、SIM 或飛航模式。'
    Read-Host '通話完全結束後，回到此視窗按 Enter'

    $endMarker = Add-CaptureMarker 'MT_VOWIFI_CALL_FINISHED'
    Start-Sleep -Seconds 2
    Save-RegistrationSummary (Join-Path $shareRoot 'registration_after.txt')
    Save-AdbOutput (Join-Path $privateRoot 'audio_after.txt') @('shell', 'dumpsys', 'audio')

    $localAudio = Read-Host '手機端聽得到公司話機嗎？(y/n)'
    $remoteAudio = Read-Host '公司話機聽得到手機端嗎？(y/n)'
    $autoEnded = Read-Host '通話是否自行斷線？(y/n)'
    $duration = Read-Host '接聽後大約幾秒結束？'
    $iconState = Read-Host '測試前／通話中／結束後的 VoWiFi 圖示狀態'
    $notes = Read-Host '其他備註（沒有可直接按 Enter）'

    @(
        "capture_start=$startMarker"
        "call_finished=$endMarker"
        "local_heard_remote=$localAudio"
        "remote_heard_local=$remoteAudio"
        "call_auto_ended=$autoEnded"
        "seconds_after_answer=$duration"
        "vowifi_icon=$iconState"
        "notes=$notes"
    ) | Out-File -LiteralPath (Join-Path $shareRoot 'USER_OBSERVATIONS.txt') -Encoding utf8
}
finally {
    if ($null -ne $logProcess -and -not $logProcess.HasExited) {
        Stop-Process -Id $logProcess.Id -ErrorAction SilentlyContinue
        Wait-Process -Id $logProcess.Id -ErrorAction SilentlyContinue
    }
}

$timelinePatterns = @(
    'CODEX_MT_WFC',
    'M11qMtMedia',
    'bindToNetwork',
    'answerCall',
    'updateAudioInterface',
    'onUpdateAudioInterfaceResponse',
    'reqId 225',
    'saeInitialize',
    'saeCreateChannel',
    'saeStartChannel',
    'M11qSveDiag',
    'WaveOut',
    'WaveIn',
    'Notify on Established',
    'callstate: ESTABLISHED',
    'callstate: ENDED',
    'AudioSession',
    'StartAllMedia',
    'set to Audio F/W',
    'errorCode=',
    'CallState Terminated'
)
$timelineRegex = ($timelinePatterns | ForEach-Object { [regex]::Escape($_) }) -join '|'
$timelinePath = Join-Path $shareRoot 'key_timeline_redacted.txt'

if (Test-Path -LiteralPath $rawLog) {
    Get-Content -LiteralPath $rawLog |
        Where-Object { $_ -match $timelineRegex } |
        ForEach-Object { Redact-Line $_ } |
        Out-File -LiteralPath $timelinePath -Encoding utf8
}

$zipPath = Join-Path $captureRoot 'SHARE_THIS.zip'
Compress-Archive -Path (Join-Path $shareRoot '*') -DestinationPath $zipPath -Force

Write-Host ''
Write-Host '擷取完成。先把這個檔案提供給 Codex：'
Write-Host $zipPath
Write-Host ''
Write-Host '完整 tag log 保留在本機，先不要分享：'
Write-Host $privateRoot
