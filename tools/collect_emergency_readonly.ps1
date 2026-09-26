[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PWD ("emergency-readonly-{0}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))),
    [string]$Adb = "adb"
)

$ErrorActionPreference = "Stop"

Write-Host "READ-ONLY EMERGENCY ROUTING CAPTURE (NO DIALING)"
Write-Host "This script does not dial, place calls, clear logs, change settings, or restart the device."
Write-Warning "Captured files may contain phone numbers, subscriber data, network identifiers, and location-related state. Keep the raw directory private."

if (-not (Get-Command $Adb -ErrorAction SilentlyContinue)) {
    throw "adb was not found. Pass -Adb with the adb executable path."
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$resolvedOutput = (Resolve-Path -LiteralPath $OutputDirectory).Path

function Invoke-AdbCapture {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [string[]]$Arguments
    )

    $path = Join-Path $resolvedOutput $Name

    # Some Android builds do not publish every optional dumpsys service. In
    # Windows PowerShell, native stderr becomes a PowerShell error record and
    # would terminate this script while ErrorActionPreference is Stop. Capture
    # that output per command instead; a missing service is evidence, not a
    # reason to discard the rest of the snapshot.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $result = & $Adb @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } catch {
        $result = $_ | Out-String
        $exitCode = if ($null -eq $LASTEXITCODE) { -1 } else { $LASTEXITCODE }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    @(
        "# adb $($Arguments -join ' ')"
        "# exit_code=$exitCode"
        $result
    ) | Set-Content -LiteralPath $path -Encoding utf8
}

Invoke-AdbCapture "00_get_state.txt" @("get-state")
Invoke-AdbCapture "01_devices.txt" @("devices", "-l")

$properties = @(
    "ro.build.fingerprint",
    "ro.build.version.release",
    "ro.build.version.security_patch",
    "ro.product.device",
    "gsm.sim.state",
    "gsm.operator.numeric",
    "gsm.network.type",
    "ril.ecclist",
    "ro.telephony.iwlan_operation_mode",
    "ro.vendor.epdg.support"
)
foreach ($property in $properties) {
    Invoke-AdbCapture ("prop_{0}.txt" -f ($property -replace '[^A-Za-z0-9._-]', '_')) `
        @("shell", "getprop", $property)
}

Invoke-AdbCapture "10_dumpsys_phone.txt" @("shell", "dumpsys", "phone")
Invoke-AdbCapture "11_dumpsys_telephony_registry.txt" @("shell", "dumpsys", "telephony.registry")
Invoke-AdbCapture "12_dumpsys_carrier_config.txt" @("shell", "dumpsys", "carrier_config")
Invoke-AdbCapture "13_dumpsys_ims.txt" @("shell", "dumpsys", "ims")
Invoke-AdbCapture "14_dumpsys_telephony_ims.txt" @("shell", "dumpsys", "telephony_ims")
Invoke-AdbCapture "15_dumpsys_connectivity.txt" @("shell", "dumpsys", "connectivity")
Invoke-AdbCapture "16_package_imsservice.txt" @("shell", "dumpsys", "package", "com.sec.imsservice")
Invoke-AdbCapture "17_phone_list_sims.txt" @("shell", "cmd", "phone", "list-sims")
Invoke-AdbCapture "20_logcat_radio.txt" @("shell", "logcat", "-b", "radio", "-d", "-v", "threadtime")
Invoke-AdbCapture "21_logcat_system.txt" @("shell", "logcat", "-b", "main", "-b", "system", "-b", "crash", "-d", "-v", "threadtime")

$patterns = @(
    "emergency", "EIMS", "ECC", "e911", "112", "911",
    "MmTelFeature", "CAPABILITY_EMERGENCY_OVER_MMTEL",
    "EmergencyNumberTracker", "emergencyDial", "shouldProcessCall",
    "IMS.*registered", "registrationTech", "qualified.*network"
)
$summaryPath = Join-Path $resolvedOutput "30_emergency_summary.txt"
Get-ChildItem -LiteralPath $resolvedOutput -File |
    Where-Object { $_.Name -ne "30_emergency_summary.txt" } |
    Select-String -Pattern $patterns -CaseSensitive:$false |
    ForEach-Object { "{0}:{1}:{2}" -f $_.Path, $_.LineNumber, $_.Line } |
    Set-Content -LiteralPath $summaryPath -Encoding utf8

$readme = @"
Read-only emergency-routing evidence capture

No call was placed. The script did not clear logs, change settings/properties,
toggle radios, restart services, reboot, or invoke emergency-number test mode.

The raw files can contain sensitive identifiers and call/network history. Keep
this directory private and redact it before sharing. A successful capture does
not validate emergency calling.
"@
$readme | Set-Content -LiteralPath (Join-Path $resolvedOutput "README_PRIVATE.txt") -Encoding utf8

Get-ChildItem -LiteralPath $resolvedOutput -File |
    Get-FileHash -Algorithm SHA256 |
    Sort-Object Path |
    ForEach-Object { "{0}  {1}" -f $_.Hash.ToLowerInvariant(), (Split-Path $_.Path -Leaf) } |
    Set-Content -LiteralPath (Join-Path $resolvedOutput "SHA256SUMS.txt") -Encoding ascii

Write-Host "Capture complete: $resolvedOutput"
Write-Host "No emergency call was placed."
