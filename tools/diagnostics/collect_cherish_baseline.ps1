param(
    [ValidateSet('snapshot','registration','call','rootbackend')]
    [string]$Phase = 'snapshot',
    [string]$OutputRoot = 'cherish_runtime',
    [int]$DurationSeconds = 180
)

$ErrorActionPreference = 'Stop'

function Invoke-AdbCapture {
    param([string]$Name, [string[]]$Arguments)
    $target = Join-Path $script:RunDir $Name
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & adb @Arguments 2>&1 | Out-File -FilePath $target -Encoding utf8
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $savedPreference
    }
    if ($exitCode -ne 0) {
        "exit_code=$exitCode file=$Name" | Out-File (Join-Path $script:RunDir 'capture_warnings.txt') -Append -Encoding utf8
    }
}

function Invoke-ShellCapture {
    param([string]$Name, [string]$Command)
    Invoke-AdbCapture -Name $Name -Arguments @('shell', $Command)
}

function Invoke-RootShellCapture {
    param([string]$Name, [string]$Command)
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Command))
    Invoke-AdbCapture -Name $Name -Arguments @('shell', 'su', '-c', "echo $encoded | base64 -d | sh")
}

function Invoke-AdbTimedLogcat {
    param([string]$Name, [int]$Seconds)
    $target = Join-Path $script:RunDir $Name
    $errorTarget = Join-Path $script:RunDir ($Name + '.stderr.txt')
    $process = Start-Process -FilePath 'adb' -ArgumentList @('logcat','-b','all','-v','threadtime','*:V') -NoNewWindow -PassThru -RedirectStandardOutput $target -RedirectStandardError $errorTarget
    try {
        if (-not $process.WaitForExit($Seconds * 1000)) {
            $process.Kill()
            $process.WaitForExit()
        }
    }
    finally {
        $process.Dispose()
    }
}

if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
    throw 'adb is not available in PATH.'
}

$deviceState = (& adb get-state 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $deviceState -ne 'device') {
    throw "Exactly one authorized Android device must be online (state: $deviceState)."
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$script:RunDir = Join-Path $OutputRoot "${stamp}_${Phase}"
New-Item -ItemType Directory -Path $script:RunDir -Force | Out-Null

@(
    "phase=$Phase"
    "host_time=$(Get-Date -Format o)"
    "duration_seconds=$DurationSeconds"
    'scope=SIM1 WWAN VoLTE baseline; same SIM/slot/carrier as stock reference'
) | Out-File (Join-Path $script:RunDir 'manifest.txt') -Encoding utf8

Invoke-AdbCapture 'adb_devices.txt' @('devices','-l')
Invoke-ShellCapture 'device_identity.txt' 'printf "fingerprint="; getprop ro.build.fingerprint; printf "slot_count="; getprop ro.telephony.sim.count; printf "multisim="; getprop persist.radio.multisim.config; printf "radio_version="; getprop gsm.version.baseband; printf "uptime="; cat /proc/uptime'

if ($Phase -eq 'snapshot') {
    Invoke-ShellCapture 'getprop.txt' 'getprop'
    Invoke-ShellCapture 'processes.txt' 'ps -A -o USER,PID,PPID,NAME,ARGS'
    Invoke-ShellCapture 'service_list.txt' 'service list'
    Invoke-ShellCapture 'lshal.txt' 'lshal'
    Invoke-ShellCapture 'hwservicemanager.txt' 'lshal -i 2>/dev/null; echo ---; service list'
    Invoke-ShellCapture 'telephony_registry.txt' 'dumpsys telephony.registry'
    Invoke-ShellCapture 'carrier_config.txt' 'dumpsys carrier_config'
    Invoke-ShellCapture 'connectivity.txt' 'dumpsys connectivity'
    Invoke-ShellCapture 'ims.txt' 'dumpsys ims'
    Invoke-ShellCapture 'telephony_ims.txt' 'dumpsys telephony_ims'
    Invoke-ShellCapture 'phone.txt' 'dumpsys phone'
    Invoke-ShellCapture 'subscriptions.txt' 'dumpsys isub; echo ---; cmd phone list-sims 2>/dev/null'
    Invoke-ShellCapture 'packages_ims.txt' 'pm list packages -f | grep -Ei "ims|telephony|carrier|epdg"'
    Invoke-ShellCapture 'network.txt' 'ip address; echo ---ROUTES---; ip route show table all; echo ---RULES---; ip rule'
    Invoke-ShellCapture 'radio_backend_files.txt' 'for f in /vendor/lib/libsec-ril.so /vendor/lib/libril_sem.so /vendor/lib/vendor.samsung.hardware.radio.channel@2.0.so /vendor/lib/vendor.samsung.hardware.radio.bridge@2.0.so; do ls -lZ "$f" 2>&1; done'
    Invoke-ShellCapture 'init_services.txt' 'getprop | grep -E "\[init\.svc\.(imsd|epdgd|rild)"'
    Invoke-ShellCapture 'selinux.txt' 'getenforce; ps -AZ | grep -Ei "ims|epdg|rild"'
    Invoke-ShellCapture 'logcat_boot_current.txt' 'logcat -b all -d -v threadtime'
}
elseif ($Phase -eq 'registration') {
    & adb logcat -b all -c
    Invoke-ShellCapture 'registration_start_state.txt' 'date; dumpsys telephony.registry; echo ---IMS---; dumpsys ims; echo ---CONNECTIVITY---; dumpsys connectivity'
    Invoke-AdbTimedLogcat 'registration_logcat.txt' $DurationSeconds
    Invoke-ShellCapture 'registration_end_state.txt' 'date; dumpsys telephony.registry; echo ---IMS---; dumpsys ims; echo ---PHONE---; dumpsys phone; echo ---CONNECTIVITY---; dumpsys connectivity'
}
elseif ($Phase -eq 'call') {
    Write-Host "Start one outgoing SIM1 cellular voice call now; keep it connected, then hang up normally. Capturing for $DurationSeconds seconds."
    & adb logcat -b all -c
    Invoke-ShellCapture 'call_start_state.txt' 'date; dumpsys telephony.registry; echo ---IMS---; dumpsys ims; echo ---TELECOM---; dumpsys telecom'
    Invoke-AdbTimedLogcat 'volte_call_logcat.txt' $DurationSeconds
    Invoke-ShellCapture 'call_end_state.txt' 'date; dumpsys telephony.registry; echo ---IMS---; dumpsys ims; echo ---TELECOM---; dumpsys telecom; echo ---PHONE---; dumpsys phone'
}
elseif ($Phase -eq 'rootbackend') {
    Invoke-AdbCapture 'push_root_helper.txt' @('push', '.\tools\collect_rootbackend_android.sh', '/data/local/tmp/collect_rootbackend_android.sh')
    Invoke-AdbCapture 'rootbackend_full.txt' @('shell', 'su', '-c', '/system/bin/sh</data/local/tmp/collect_rootbackend_android.sh')
}

Write-Host "Capture complete: $script:RunDir"
Write-Host 'Review logs for phone numbers, IMSI, SIP URIs, IP addresses, and other subscriber identifiers before sharing.'
