#!/usr/bin/env bash
# Host-only regression checks: never invoke device su, tcpdump or adb.
set -euo pipefail
probe_script="$(cd "$(dirname "$0")" && pwd)/capture_ims_media_probe_termux.sh"
bash -n "$probe_script"
test_root="$(mktemp -d)"
trap 'rm -f "$test_root/status" "$test_root/expected" "$test_root/.interface_discovery.tmp"; rmdir "$test_root/fresh/ims_media_probe_20000101_000000/PRIVATE_ALL" "$test_root/fresh/ims_media_probe_20000101_000000" "$test_root/fresh" "$test_root"' EXIT
PRIVATE_ROOT="$test_root"
COMMAND_LOG="$test_root/status"
ROOT_IP_AVAILABLE=true
MAX_INTERFACES=8
su() {
    [ "$1" = -c ] && [ "$2" = 'ip -o link show' ] || return 91
    local i
    for i in {0..7}; do
        printf '%s: epdg_data%s: <POINTOPOINT,NOARP> mtu 1500 state DOWN\n' "$((i+9))" "$i"
    done
    printf '%s\n' \
        '22: epdg1: <POINTOPOINT,UP,LOWER_UP> mtu 1500 state UP' \
        '23: epdg2: <NO-CARRIER,POINTOPOINT,UP> mtu 1500 state DOWN' \
        '25: rmnet_data0: <UP,LOWER_UP> mtu 1500 state UNKNOWN' \
        '26: rmnet_data1: <UP,LOWER_UP> mtu 1500 state UNKNOWN' \
        '27: rmnet_data2: <> mtu 1500 state DOWN'
}
# Load just the discovery function, without running the device workflow.
source <(sed -n '/^discover_interfaces() {$/,/^}$/p' "$probe_script")
discover_interfaces
expected_interfaces=$'epdg1\nrmnet_data0\nrmnet_data1'
[[ "$INTERFACES" = "$expected_interfaces" ]]
! grep -q 'status=TRUNCATED' "$COMMAND_LOG"
grep -q 'reason=not_lower_up' "$COMMAND_LOG"
MAX_INTERFACES=2
discover_interfaces
[[ "$INTERFACES" = $'epdg1\nrmnet_data0' ]]
grep -q 'status=TRUNCATED' "$COMMAND_LOG"
su() { printf '%s\n' '9: epdg_data0: <NOARP> state DOWN'; }
discover_interfaces
[[ -z "$INTERFACES" ]]
grep -q 'status=NO_ACTIVE_MATCHING_INTERFACES' "$COMMAND_LOG"

# Exercise the real directory setup with a frozen date and stubbed su.
date() { printf '20000101_000000\n'; }
setup_prefix="$(sed '/^printf '\''PRIVATE CAPTURE:/,$d' "$probe_script")"
( set -- "$test_root/fresh"; eval "$setup_prefix" )
[[ -d "$test_root/fresh/ims_media_probe_20000101_000000/PRIVATE_ALL" ]]
if ( set -- "$test_root/fresh"; eval "$setup_prefix" ) 2>/dev/null; then
    printf 'FAIL: collision was accepted\n' >&2
    exit 1
fi
[[ -d "$test_root/fresh/ims_media_probe_20000101_000000/PRIVATE_ALL" ]]
grep -q "parent 1:" "$probe_script"
grep -q "parent ffff:" "$probe_script"
source <(sed -n '/^prepare_audio_trial() {$/,/^}$/p' "$probe_script")
source <(sed -n '/^require_command() {$/,/^}$/p' "$probe_script")
source <(sed -n '/^probe_root_command() {$/,/^}$/p' "$probe_script")
AUDIO_TRIAL=false
AUDIO_TRIAL_COMMAND=""
prepare_audio_trial
[[ -z "$AUDIO_TRIAL_COMMAND" ]]
AUDIO_TRIAL=true
sha256sum() { printf '864faf7fad602b6265c5df0595844dfbc872f47569cb74753f319d93a4e3ce3b  dummy\n'; }
su() {
    case "$2" in
        'command -v timeout') printf '/system/bin/timeout\n' ;;
        "test -f '/system/system_ext/framework/imsmanager.jar'") return 0 ;;
        *'M11L2wAudioTrial '*' preflight') printf 'SAE_TRIAL_API_READY\n' ;;
        *) printf 'Unexpected root command in mock\n' >&2; return 91 ;;
    esac
}
prepare_audio_trial
[[ "$AUDIO_TRIAL_COMMAND" = 'timeout 5 env CLASSPATH='* ]]
grep -q 'audio_trial=ARMED' "$COMMAND_LOG"
sha256sum() { printf 'bad_hash  dummy\n'; }
if (prepare_audio_trial) >/dev/null 2>&1; then
    printf 'FAIL: untrusted helper hash accepted\n' >&2
    exit 1
fi
rm -f "$test_root/audio_trial_preflight.txt"
printf 'PASS: syntax, active interfaces, UNKNOWN rmnet, cap, no active links, first-run parent and collision\n'
printf 'PASS: explicit parents, audio disabled by default, read-only preflight, helper hash mismatch rejection\n'
grep -q '^HANDOVER_CHECK=false$' "$probe_script"
grep -q '不可混用手動 SAE 與自動切換驗證' "$probe_script"
grep -q 'W2L_user_wifi_off' "$probe_script"
grep -q 'W2L_observation_window_complete' "$probe_script"
! grep -q 'persist.sys.m11_ims_audio_port' "$probe_script"
grep -q 'sa2_gate=NOT_REQUIRED' "$probe_script"
printf 'PASS: handover mode is opt-in, mutually exclusive with manual SAE, and has explicit W2L observation markers\n'
printf 'PASS: integrated audio has no feature-switch prerequisite; collector remains read-only\n'
