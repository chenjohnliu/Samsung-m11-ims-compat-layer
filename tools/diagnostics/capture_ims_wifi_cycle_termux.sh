#!/data/data/com.termux/files/usr/bin/bash
# Read-only IMS/ePDG capture for repeated Wi-Fi <-> LTE transition testing.

set -eu
umask 077

CAPTURE_MODE="${IMS_CAPTURE_MODE:-cycles}"
case "$CAPTURE_MODE" in
    cycles|handover) ;;
    *) printf 'IMS_CAPTURE_MODE 必須是 cycles 或 handover\n' >&2; exit 1 ;;
esac

CAPTURE_SLOT="${IMS_CAPTURE_SLOT:-0}"
case "$CAPTURE_SLOT" in
    0|1) ;;
    *) printf 'IMS_CAPTURE_SLOT 必須是 0 或 1（Android SIM slot index）\n' >&2; exit 1 ;;
esac

DEBUG_DUMP_TIMEOUT="${IMS_CAPTURE_DUMP_TIMEOUT_SECONDS:-10}"
case "$DEBUG_DUMP_TIMEOUT" in
    10|30) ;;
    *) printf 'IMS_CAPTURE_DUMP_TIMEOUT_SECONDS 必須是 10 或 30\n' >&2; exit 1 ;;
esac

if [ -d "$HOME/storage/shared" ]; then
    DEFAULT_OUTPUT_ROOT="$HOME/storage/shared/m11q_logs"
else
    DEFAULT_OUTPUT_ROOT="$HOME/m11q_logs"
fi

OUTPUT_ROOT="${1:-$DEFAULT_OUTPUT_ROOT}"
STAMP="$(date +%Y%m%d_%H%M%S)"
CAPTURE_ROOT="$OUTPUT_ROOT/ims_wifi_cycle_$STAMP"
SHARE_ROOT="$CAPTURE_ROOT/SHARE_THIS"
PRIVATE_ROOT="$CAPTURE_ROOT/_PRIVATE_DO_NOT_SHARE"
RAW_LOG="$PRIVATE_ROOT/logcat_all_private.txt"
RAW_ERROR="$PRIVATE_ROOT/logcat_all_private.stderr.txt"
OBSERVATIONS="$SHARE_ROOT/USER_OBSERVATIONS.tsv"
ROOT_LOGCAT_PID=""
WAKE_LOCK_HELD="false"

mkdir -p "$SHARE_ROOT" "$PRIVATE_ROOT"

cleanup() {
    if [ -n "$ROOT_LOGCAT_PID" ]; then
        su -c "kill '$ROOT_LOGCAT_PID'" >/dev/null 2>&1 || true
        ROOT_LOGCAT_PID=""
    fi
    if [ "$WAKE_LOCK_HELD" = "true" ]; then
        termux-wake-unlock >/dev/null 2>&1 || true
        WAKE_LOCK_HELD="false"
    fi
}
trap cleanup EXIT INT TERM

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf '缺少必要指令：%s\n' "$1" >&2
        exit 1
    fi
}

require_command su
require_command tar
require_command grep
require_command sed
require_command sha256sum

if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock >/dev/null 2>&1 || true
    WAKE_LOCK_HELD="true"
fi

ROOT_ID="$(su -c id 2>&1 || true)"
case "$ROOT_ID" in
    *uid=0*) ;;
    *)
        printf '無法取得 root shell：%s\n' "$ROOT_ID" >&2
        exit 1
        ;;
esac

add_marker() {
    marker="$1_$(date +%Y%m%d_%H%M%S)"
    su -c "log -t CODEX_IMS_CYCLE '$marker'" >/dev/null 2>&1 || true
    printf '%s' "$marker"
}

capture_private() {
    destination="$1"
    command="$2"
    {
        printf 'captured_at=%s\n' "$(date -Iseconds)"
        printf 'command=%s\n' "$command"
        su -c "$command"
    } >"$destination" 2>&1 || true
}

redact_stream() {
    sed -E \
        -e 's#([sS][iI][pP]:|[tT][eE][lL]:)[^ >;]+#\1[redacted]#g' \
        -e 's#urn:gsma:imei:[^, ]+#urn:gsma:imei:[redacted]#g' \
        -e 's#(^|[^0-9A-Fa-f])\+?[0-9]{9,15}([^0-9A-Fa-f]|$)#\1[redacted-number]\2#g' \
        -e 's#(^|[^0-9])([0-9]{1,3}\.){3}[0-9]{1,3}([^0-9]|$)#\1[redacted-ipv4]\3#g' \
        -e 's#([0-9A-Fa-f]{1,4}:){3,}[0-9A-Fa-f:]*|[0-9A-Fa-f:]*::[0-9A-Fa-f:]*#[redacted-ipv6]#g'
}

write_capture_health() {
    start_observed=false
    end_observed=false
    if [ -f "$RAW_LOG" ]; then
        if grep -Fq "$CAPTURE_START_MARKER" "$RAW_LOG"; then start_observed=true; fi
        if grep -Fq "$CAPTURE_END_MARKER" "$RAW_LOG"; then end_observed=true; fi
    fi
    {
        printf 'start_marker=%s\nend_marker=%s\n' "$CAPTURE_START_MARKER" "$CAPTURE_END_MARKER"
        printf 'start_marker_observed=%s\nend_marker_observed=%s\n' "$start_observed" "$end_observed"
        if [ -s "$RAW_ERROR" ]; then
            printf 'logger_stderr_empty=false\n'
        elif [ -f "$RAW_ERROR" ]; then
            printf 'logger_stderr_empty=true\n'
        else
            printf 'logger_stderr_empty=unknown\n'
        fi
    } >"$SHARE_ROOT/capture_health.txt"
    if [ -f "$RAW_ERROR" ]; then
        redact_stream <"$RAW_ERROR" >"$SHARE_ROOT/logcat_stderr_redacted.txt"
    fi
    if [ "$start_observed" != true ] || [ "$end_observed" != true ]; then
        printf '\n警告：連續日誌缺少開始／結束標記，不能把所有階段都視為完整日誌覆蓋；snapshot 仍會封裝。\n' >&2
    fi
}

write_handover_policy_layers() {
    printf 'policy_read_method=layered_carrier_config_dump\n'
    printf 'policy_scope=unmerged_all_slots_and_no_sim\n'
    printf 'requested_ims_slot=%s\n' "$CAPTURE_SLOT"
    # Preserve layer/slot context. Defaults alone are NOT the effective policy.
    # CarrierConfigLoader prints string arrays on one line in this Android 13 tree.
    grep -E '^[[:space:]]*(Phone Id =|Default Values from CarrierConfigManager[[:space:]]*:|mConfigFromDefaultApp[[:space:]]*:|mConfigFromCarrierApp[[:space:]]*:|mPersistentOverrideConfigs[[:space:]]*:|mOverrideConfigs[[:space:]]*:|mNoSimConfig[[:space:]]*:|iwlan_handover_policy_string_array[[:space:]]*=|m11q_active_call_w2l_handover_bool[[:space:]]*=)|Permission Denial|Permission denied|Can.t find service' "$1" \
        | redact_stream || true
}

snapshot() {
    phase="$1"
    phase_dir="$PRIVATE_ROOT/$phase"
    mkdir -p "$phase_dir"
    marker="$(add_marker "SNAPSHOT_$phase")"

    capture_private "$phase_dir/secims.txt" "dumpsys secims"
    capture_private "$phase_dir/connectivity.txt" "dumpsys connectivity"
    capture_private "$phase_dir/carrier_config.txt" "dumpsys carrier_config"
    capture_private "$phase_dir/ims.txt" "dumpsys ims"
    capture_private "$phase_dir/telephony_ims.txt" "dumpsys telephony_ims"
    capture_private "$phase_dir/telephony_registry.txt" "dumpsys telephony.registry"
    capture_private "$phase_dir/phone.txt" "dumpsys phone"
    # PhoneGlobals' binder dump does not include PhoneFactory/DataNetworkController.
    # PhoneGlobals starts this DUMP-protected diagnostic service during normal boot.
    # This controls only outer dumpsys, NOT the client's inner deadline.
    # A broad phone dump can block its main thread; keep the 10s default for transition tests.
    capture_private "$phase_dir/telephony_debug.txt" \
        "dumpsys -t $DEBUG_DUMP_TIMEOUT activity service com.android.phone/.TelephonyDebugService"
    # cmd phone cc is root AND non-user-build gated. dumpsys does not share that gate.
    write_handover_policy_layers "$phase_dir/carrier_config.txt" \
        >"$phase_dir/handover_policy.txt"
    capture_private "$phase_dir/telecom.txt" "dumpsys telecom"
    capture_private "$phase_dir/ip_addr.txt" "ip -br addr"
    capture_private "$phase_dir/ip_rule.txt" "ip rule show"
    capture_private "$phase_dir/ip_route_all.txt" "ip route show table all; ip -6 route show table all"
    capture_private "$phase_dir/xfrm_state.txt" "ip xfrm state; ip xfrm policy; cat /proc/net/xfrm_stat"
    capture_private "$phase_dir/tc_state.txt" "tc qdisc show; for iface in epdg0 epdg_data0 rmnet_data0 rmnet_data1 rmnet_data2; do echo ===\$iface===; tc filter show dev \$iface ingress 2>/dev/null; done"
    capture_private "$phase_dir/epdg_properties.txt" "getprop | grep -i epdg"
    capture_private "$phase_dir/ims_processes.txt" "ps -AZ | grep -E 'epdg|ims|eris|rild'"

    {
        printf 'phase=%s\nmarker=%s\ncaptured_at=%s\n' "$phase" "$marker" "$(date -Iseconds)"
        printf '%s\n' '--- telephony debug capture coverage ---'
        if grep -Eq '^[[:space:]]*PhoneFactory:$' "$phase_dir/telephony_debug.txt"; then
            printf 'phone_factory_dump_present=true\n'
        else
            printf 'phone_factory_dump_present=false\n'
        fi
        if grep -Eq '^[[:space:]]*DataNetworkController-[0-9]+:$' "$phase_dir/telephony_debug.txt"; then
            printf 'data_network_controller_dump_present=true\n'
        else
            printf 'data_network_controller_dump_present=false\n'
        fi
        if grep -Eq 'DUMP TIMEOUT|Failure while dumping the service:.*Timeout' "$phase_dir/telephony_debug.txt"; then
            printf 'telephony_debug_dump_timeout=true\n'
        else
            printf 'telephony_debug_dump_timeout=false\n'
        fi
        # Header presence or absence of an explicit timeout does not prove a complete dump.
        printf '%s\n' '--- handover policy layers (not an effective merged value) ---'
        redact_stream <"$phase_dir/handover_policy.txt"
        printf '%s\n' '--- registration ---'
        su -c "dumpsys secims | grep -E 'SIM slot:|UserAgent.*State:|onRegistered: RAT =|updateRegistration:.*rat=|onPdnConnected:|onLost[0-9]+|mIsEpdgConnected|isWifiConnected' | tail -n 160" 2>/dev/null || true
        printf '%s\n' '--- IMS networks and requests ---'
        su -c "dumpsys connectivity | grep -Ei 'NetworkAgentInfo.*(IWLAN|LTE)|Capabilities:.*IMS|RequestorPkg: com.sec.(imsservice|epdg)|epdg_data|rmnet_data' | tail -n 180" 2>/dev/null | redact_stream || true
        printf '%s\n' '--- interface state and address fingerprints ---'
        grep -E '^(epdg_data|rmnet_data)' "$phase_dir/ip_addr.txt" 2>/dev/null | while IFS= read -r line; do
            name="${line%% *}"
            remainder="${line#* }"
            remainder="${remainder#${remainder%%[! ]*}}"
            state="${remainder%% *}"
            fingerprint="$(printf '%s' "$line" | sha256sum | sed 's/[[:space:]].*//')"
            printf '%s state=%s full_line_sha256=%s\n' "$name" "$state" "$fingerprint"
        done
    } >"$SHARE_ROOT/${phase}_summary.txt"
}

record_call_result() {
    phase="$1"
    printf '撥號結果 (connected/failed/stuck/skipped)：'
    read -r result
    printf '畫面顯示的網路圖示 (VoLTE/VoWiFi/none/other)：'
    read -r icon
    printf '備註（沒有可直接按 Enter）：'
    read -r notes
    printf '%s\t%s\t%s\t%s\t%s\n' "$(date -Iseconds)" "$phase" "$result" "$icon" "$notes" >>"$OBSERVATIONS"
    LAST_CALL_RESULT="$result"
}

capture_failure_recovery() {
    failed_phase="$1"
    case "$LAST_CALL_RESULT" in
        failed|stuck)
            # Preserve the failure edge in continuous logcat without running blocking dumpsys
            # commands while the Wi-Fi-to-LTE handover may still be active.
            add_marker "${failed_phase}_FAILURE_OBSERVED" >/dev/null
            printf '\n已捕捉到失敗。接下來 120 秒請不要切換 Wi-Fi、飛航模式或重開機。\n'
            sleep 120
            snapshot "${failed_phase}_after_120s_wait"
            printf '請在不改變網路狀態的情況下再撥一次 188。\n'
            record_call_result "${failed_phase}_retry_after_120s"
            snapshot "${failed_phase}_after_120s_retry"

            wait_for_user '最後進行恢復對照：開啟飛航模式，等 15 秒，關閉飛航模式，然後等 VoLTE 與訊號完全回來。'
            snapshot "${failed_phase}_after_airplane_recovery_before_call"
            printf '請在恢復後撥 188。\n'
            record_call_result "${failed_phase}_after_airplane_recovery"
            snapshot "${failed_phase}_after_airplane_recovery_after_call"
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

wait_for_user() {
    message="$1"
    printf '\n%s\n' "$message"
    printf '完成並穩定後按 Enter：'
    read -r _unused
}

BUILD_FINGERPRINT="$(getprop ro.build.fingerprint 2>/dev/null || true)"
BUILD_ID="$(getprop ro.build.display.id 2>/dev/null || true)"
BUILD_TYPE="$(getprop ro.build.type 2>/dev/null || true)"
CRDROID_VERSION="$(getprop ro.crdroid.version 2>/dev/null || true)"
OPERATOR_NUMERIC="$(getprop gsm.operator.numeric 2>/dev/null || true)"
BUILD_DATE_UTC="$(getprop ro.build.date.utc 2>/dev/null || true)"
BUILD_INCREMENTAL="$(getprop ro.build.version.incremental 2>/dev/null || true)"
IWLAN_MODE_PROPERTY="$(getprop ro.telephony.iwlan_operation_mode 2>/dev/null || true)"
IMS_TRIAL_LABEL="$(getprop ro.m11q.ims_trial 2>/dev/null || true)"
IMS_SEH_APN_BRIDGE="$(su -c 'getprop ro.m11q.ims_seh_apn_bridge' 2>/dev/null || true)"
BASEBAND_VERSION="$(getprop gsm.version.baseband 2>/dev/null || true)"
TELEPHONY_JAR_HASH="$(su -c 'sha256sum /system/framework/telephony-common.jar' 2>/dev/null \
    | sed 's/[[:space:]].*//' || true)"
# Resolve Android's package manager explicitly, not a Termux PATH command.
IMS_SETTINGS_PATH="$(su -c '/system/bin/pm path com.samsung.advp.imssettings' 2>/dev/null || true)"
SAMSUNG_DIALER_PATH="$(su -c '/system/bin/pm path com.samsung.android.dialer' 2>/dev/null || true)"
EPDG_APK_PATH="$(su -c '/system/bin/pm path com.sec.epdg' 2>/dev/null | sed -n 's/^package://p' | sed -n '1p' || true)"
IMS_APK_PATH="$(su -c '/system/bin/pm path com.sec.imsservice' 2>/dev/null | sed -n 's/^package://p' | sed -n '1p' || true)"
EPDG_APK_SHA256=""
IMS_APK_SHA256=""
EPDG_CLASSES_DEX_SHA256=""
IMS_CLASSES_DEX_SHA256=""
IMS_CLASSES2_DEX_SHA256=""
EPDG_VERSION=""
IMS_VERSION=""
apk_classes_dex_sha256() {
    dex_apk_path="$1"
    dex_entry="${2:-classes.dex}"
    case "$dex_entry" in classes.dex|classes2.dex) ;; *) return 0 ;; esac
    # pipefail makes unzip errors visible through sha256sum; reject the empty-stream hash too.
    dex_hash_output="$(su -c "set -o pipefail || exit 1; unzip -p '$dex_apk_path' '$dex_entry' 2>/dev/null | sha256sum" 2>/dev/null)" || return 0
    dex_hash="${dex_hash_output%% *}"
    if printf '%s\n' "$dex_hash" | grep -Eq '^[0-9a-fA-F]{64}$' \
        && [ "$dex_hash" != e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 ]; then
        printf '%s' "$dex_hash"
    fi
}
if [ -n "$EPDG_APK_PATH" ]; then
    EPDG_APK_SHA256="$(su -c "sha256sum '$EPDG_APK_PATH'" 2>/dev/null | sed 's/[[:space:]].*//' || true)"
    EPDG_CLASSES_DEX_SHA256="$(apk_classes_dex_sha256 "$EPDG_APK_PATH")"
    EPDG_VERSION="$(su -c 'dumpsys package com.sec.epdg' 2>/dev/null | grep -m 1 -E 'versionCode=|versionName=' || true)"
fi
if [ -n "$IMS_APK_PATH" ]; then
    IMS_APK_SHA256="$(su -c "sha256sum '$IMS_APK_PATH'" 2>/dev/null | sed 's/[[:space:]].*//' || true)"
    IMS_CLASSES_DEX_SHA256="$(apk_classes_dex_sha256 "$IMS_APK_PATH")"
    IMS_CLASSES2_DEX_SHA256="$(apk_classes_dex_sha256 "$IMS_APK_PATH" classes2.dex)"
    IMS_VERSION="$(su -c 'dumpsys package com.sec.imsservice' 2>/dev/null | grep -m 1 -E 'versionCode=|versionName=' || true)"
fi
IMS_SETTINGS_AVAILABLE=false
SAMSUNG_DIALER_AVAILABLE=false
case "$IMS_SETTINGS_PATH" in *package:*) IMS_SETTINGS_AVAILABLE=true ;; esac
case "$SAMSUNG_DIALER_PATH" in *package:*) SAMSUNG_DIALER_AVAILABLE=true ;; esac

{
    printf 'captured_at=%s\n' "$(date -Iseconds)"
    printf 'build_fingerprint=%s\n' "$BUILD_FINGERPRINT"
    printf 'build_display_id=%s\n' "$BUILD_ID"
    printf 'build_type_property=%s\n' "$BUILD_TYPE"
    printf 'crdroid_version=%s\n' "$CRDROID_VERSION"
    printf 'operator_numeric=%s\n' "$OPERATOR_NUMERIC"
    printf 'capture_mode=%s\nims_slot=%s\n' "$CAPTURE_MODE" "$CAPTURE_SLOT"
    printf 'telephony_debug_outer_timeout_seconds=%s\n' "$DEBUG_DUMP_TIMEOUT"
    printf 'build_date_utc=%s\nbuild_incremental=%s\n' "$BUILD_DATE_UTC" "$BUILD_INCREMENTAL"
    printf 'iwlan_mode_property=%s\nims_trial_label=%s\nbaseband_version=%s\n' \
        "$IWLAN_MODE_PROPERTY" "$IMS_TRIAL_LABEL" "$BASEBAND_VERSION"
    printf 'ims_seh_apn_bridge=%s\nims_seh_apn_bridge_read_method=su_getprop\n' "$IMS_SEH_APN_BRIDGE"
    printf 'telephony_jar_sha256=%s\n' "$TELEPHONY_JAR_HASH"
    printf 'epdg_package=com.sec.epdg\nepdg_apk_path=%s\nepdg_apk_sha256=%s\nepdg_classes_dex_sha256=%s\nepdg_version=%s\n' \
        "$EPDG_APK_PATH" "$EPDG_APK_SHA256" "$EPDG_CLASSES_DEX_SHA256" "$EPDG_VERSION"
    printf 'ims_package=com.sec.imsservice\nims_apk_path=%s\nims_apk_sha256=%s\nims_classes_dex_sha256=%s\nims_classes2_dex_sha256=%s\nims_version=%s\n' \
        "$IMS_APK_PATH" "$IMS_APK_SHA256" "$IMS_CLASSES_DEX_SHA256" "$IMS_CLASSES2_DEX_SHA256" "$IMS_VERSION"
    printf 'experiment_carrier_config_key=m11q_active_call_w2l_handover_bool\n'
    printf 'experiment_carrier_config_capture=layered_in_stable_phase_snapshots\n'
    printf 'samsung_ims_settings_available=%s\n' "$IMS_SETTINGS_AVAILABLE"
    printf 'samsung_dialer_available=%s\n' "$SAMSUNG_DIALER_AVAILABLE"
    printf 'root_available=true\n'
    printf 'root_shell_identity=%s\n' "$ROOT_ID" | redact_stream
} >"$SHARE_ROOT/runtime_identity.txt"

printf 'timestamp\tphase\tcall_result\ticon\tnotes\n' >"$OBSERVATIONS"
LAST_CALL_RESULT=""

LOGCAT_COMMAND="logcat -b all -v threadtime -T 1 >'$RAW_LOG' 2>'$RAW_ERROR' & echo \$!"
ROOT_LOGCAT_PID="$(su -c "$LOGCAT_COMMAND")"
case "$ROOT_LOGCAT_PID" in
    ''|*[!0-9]*)
        printf '無法啟動 root logcat，回傳值：%s\n' "$ROOT_LOGCAT_PID" >&2
        exit 1
        ;;
esac

sleep 2
CAPTURE_START_MARKER="$(add_marker IMS_WIFI_CYCLE_CAPTURE_START)"

if [ "$DEBUG_DUMP_TIMEOUT" = 30 ]; then
    printf '\n注意：30 秒 telephony dump 僅適合穩定狀態診斷，可能阻塞 phone 主執行緒；不要用於 handover／快速切換時序量測。\n' >&2
fi

if [ "$CAPTURE_MODE" = handover ]; then
    printf '\nHandover 手動擷取模式：不自動切換網路、撥號或要求飛航重置。\n'
    printf '在另一個 Termux 工作階段執行測試／CarrierConfig 指令。\n'
    printf '只在網路狀態穩定、轉換已完成後輸入標籤擷取 snapshot，例如 a_baseline、b_w2l1。\n'
    printf '轉換期間由連續 logcat 記錄時序；不要在 handover 途中執行 snapshot。輸入 stop 結束。\n'
    while true; do
        printf '\nSnapshot 標籤（英數、底線或連字號；stop 結束）：'
        read -r manual_phase || break
        [ "$manual_phase" != stop ] || break
        case "$manual_phase" in
            ''|*[!a-zA-Z0-9_-]*) printf '標籤無效。\n'; continue ;;
        esac
        if [ -e "$SHARE_ROOT/${manual_phase}_summary.txt" ]; then
            printf '標籤已存在，請使用新的標籤。\n'
            continue
        fi
        snapshot "$manual_phase"
        printf '備註（切換時間、通話結果、雙向語音、最後想要的網路）：'
        read -r manual_notes || manual_notes=''
        printf '%s\t%s\tmanual\tmanual\t%s\n' "$(date -Iseconds)" \
            "$manual_phase" "$manual_notes" >>"$OBSERVATIONS"
    done
else
printf '\n這個測試不會自動切換 Wi-Fi 或撥號。\n'
printf '每個階段都請等 VoLTE/VoWiFi 圖示與訊號狀態穩定再繼續。\n'
printf '如果某通電話失敗，仍繼續完成當下 snapshot，但不要重開機或切飛航模式。\n'

wait_for_user '0. 關閉 Wi-Fi，等 VoLTE 圖示出現。'
snapshot lte_baseline_before_call
printf '請撥 188，等待接通或確定失敗。\n'
record_call_result lte_baseline
snapshot lte_baseline_after_call
if capture_failure_recovery lte_baseline; then
    cycle=4
else
    cycle=1
fi

while [ "$cycle" -le 3 ]; do
    wait_for_user "$cycle-A. 開啟 Wi-Fi，等 VoWiFi 圖示出現（最長等約 90 秒，未出現也可繼續記錄）。"
    snapshot "cycle${cycle}_vowifi_before_call"
    printf '請在目前狀態撥 188，等待接通或確定失敗。\n'
    record_call_result "cycle${cycle}_vowifi"
    snapshot "cycle${cycle}_vowifi_after_call"
    if capture_failure_recovery "cycle${cycle}_vowifi"; then
        break
    fi

    wait_for_user "$cycle-B. 關閉 Wi-Fi，等 VoLTE 圖示出現（最長等約 90 秒，未出現也可繼續記錄）。"
    snapshot "cycle${cycle}_volte_before_call"
    printf '請在目前狀態撥 188，等待接通或確定失敗。\n'
    record_call_result "cycle${cycle}_volte"
    snapshot "cycle${cycle}_volte_after_call"
    if capture_failure_recovery "cycle${cycle}_volte"; then
        break
    fi

    cycle=$((cycle + 1))
done
fi

CAPTURE_END_MARKER="$(add_marker IMS_WIFI_CYCLE_CAPTURE_END)"
sleep 2
cleanup
trap - EXIT INT TERM

write_capture_health

TIMELINE_PATTERN='CODEX_IMS_CYCLE|M11Seh|RIL_LoadApnProfFromDB|SecLoadApnProfFromDB|APN_ATTACH_REQ|DNC-|DN-|DRM-|DSM-|DataNetwork|DataNetworkController|TelephonyNetworkFactory|QualifiedNetworks|TelephonyAdapter|IwlanDataService|responseSetupDataCall|updateApnConnStatus|setupDataCall|NETWORK_FAILURE|DATA_THROTTLED|retry=-|ThrottleController|ThrottleManager|Epdg|EPDG|ConcreteClientModeManager|Wifi.*(off|Off|OFF|defer|Defer)|WIFI_STATE_DISABLING|WIFI_STATE_CHANGED|M11W2L|EC2|W2L|L2W|handover|Handover|target.*setup|setup.*target|handover.*(result|timeout|cancel)|onPdnConnected|onLost[0-9]+|RegisterTask|RegistrationManager|UserAgent|ImsRegistration|CallStateMachine|ResipVolteHandler|session[Ii][Dd]|call[Ii][Dd]|CallId|SETUP_DATA_CALL|DEACTIVATE_DATA_CALL|IpSec|IPsec|ipsec|epdg_data|rmnet_data|487 Request Terminated|AAA:|5065|NullPointerException|FATAL EXCEPTION|errorCode=|callstate:'

if [ -f "$RAW_LOG" ]; then
    grep -E "$TIMELINE_PATTERN" "$RAW_LOG" 2>/dev/null | redact_stream \
        >"$SHARE_ROOT/key_timeline_redacted.txt" || true
fi

SHARE_ARCHIVE="$CAPTURE_ROOT/SHARE_THIS.tar.gz"
PRIVATE_ARCHIVE="$CAPTURE_ROOT/PRIVATE_FULL_CAPTURE.tar.gz"
tar -czf "$SHARE_ARCHIVE" -C "$SHARE_ROOT" .
tar -czf "$PRIVATE_ARCHIVE" -C "$PRIVATE_ROOT" .

printf '\n擷取完成。請先提供可分享的紅除版：\n%s\n' "$SHARE_ARCHIVE"
printf '\n完整版可能含電話號碼、IP 與 IMS 身分資料，請先保留在手機：\n%s\n' "$PRIVATE_ARCHIVE"
