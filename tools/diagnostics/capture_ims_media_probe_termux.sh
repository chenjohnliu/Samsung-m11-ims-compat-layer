#!/data/data/com.termux/files/usr/bin/bash
# Bounded media-path probe; optional, explicit one-shot Samsung SAE trial.
set -eu
set -f
umask 077

PROBE_SECONDS=5
MAX_INTERFACES=8
MAX_WAIT_BEFORE_PROBE=30
MAX_WAIT_AFTER_PROBE=60
PROBE_VERSION=stock-audio-port-v7
AUDIO_TRIAL=false
HANDOVER_CHECK=false
if [ "${1:-}" = --start-sae ]; then AUDIO_TRIAL=true; shift; fi
if [ "${1:-}" = --handover-check ]; then HANDOVER_CHECK=true; shift; fi
if [ "$AUDIO_TRIAL" = true ] && [ "$HANDOVER_CHECK" = true ]; then printf '不可混用手動 SAE 與自動切換驗證\n' >&2; exit 1; fi
if [ "$#" -gt 1 ]; then printf '參數： [--start-sae 或 --handover-check] [輸出目錄]\n' >&2; exit 1; fi
AUDIO_TRIAL_COMMAND=""

DEFAULT_OUTPUT_ROOT="$HOME/m11q_logs"
OUTPUT_ROOT="${1:-$DEFAULT_OUTPUT_ROOT}"
case "$OUTPUT_ROOT" in
    /*) ;;
    *) printf '輸出路徑必須是絕對路徑\n' >&2; exit 1 ;;
esac
case "$OUTPUT_ROOT" in
    *[!A-Za-z0-9_./-]*) printf '輸出路徑僅允許英數字、斜線、底線、句點與連字號\n' >&2; exit 1 ;;
    /) printf '輸出路徑不可是根目錄\n' >&2; exit 1 ;;
esac

require_command() {
    command -v "$1" >/dev/null 2>&1 || { printf '缺少必要指令：%s\n' "$1" >&2; exit 1; }
}
require_command su
require_command date

STAMP="$(date +%Y%m%d_%H%M%S)"
CAPTURE_ROOT="$OUTPUT_ROOT/ims_media_probe_$STAMP"
PRIVATE_ROOT="$CAPTURE_ROOT/PRIVATE_ALL"
COMMAND_LOG="$PRIVATE_ROOT/command_status.txt"
TIMELINE="$PRIVATE_ROOT/MANUAL_MARKERS.txt"
ROOT_LOGCAT="$PRIVATE_ROOT/.root_logcat.tmp"
ROOT_LOGCAT_ERR="$PRIVATE_ROOT/.root_logcat.stderr.tmp"
ROOT_LOGCAT_PID=""
TCPDUMP_PIDS=""
INTERFACES=""
TCPDUMP_AVAILABLE=false

if ! mkdir -p "$OUTPUT_ROOT"; then
    printf '無法建立上層輸出目錄：%s\n' "$OUTPUT_ROOT" >&2
    exit 1
fi
if ! mkdir "$CAPTURE_ROOT"; then
    if [ -e "$CAPTURE_ROOT" ]; then
        printf '輸出目錄已存在；舊紀錄未修改，請稍後重新執行：%s\n' "$CAPTURE_ROOT" >&2
    else
        printf '無法建立輸出目錄，請檢查權限與可用空間：%s\n' "$CAPTURE_ROOT" >&2
    fi
    exit 1
fi
mkdir "$PRIVATE_ROOT"
printf 'PRIVATE CAPTURE: logcat, packet headers, IP addresses, and IMS metadata. Do not share.\n' >"$PRIVATE_ROOT/NOTICE.txt"
printf 'captured_at=%s\n' "$(date -Iseconds)" >"$COMMAND_LOG"
printf 'probe_version=%s\n' "$PROBE_VERSION" >>"$COMMAND_LOG"
printf 'timestamp\tmarker\n' >"$TIMELINE"

root_id="$(su -c id 2>&1 || true)"
case "$root_id" in
    *uid=0*) printf 'root_shell_identity=%s\n' "$root_id" >>"$COMMAND_LOG" ;;
    *) printf 'root_status=UNAVAILABLE\toutput=%s\n' "$root_id" >>"$COMMAND_LOG"; printf '無法取得 root shell：%s\n' "$root_id" >&2; exit 1 ;;
esac

probe_root_command() {
    command_name="$1"
    if command_output="$(su -c "command -v $command_name" 2>&1)"; then
        if [ -n "$command_output" ]; then
            printf 'root_command=%s\tstatus=AVAILABLE\tpath=%s\n' "$command_name" "$command_output" >>"$COMMAND_LOG"
            return 0
        fi
        printf 'root_command=%s\tstatus=UNAVAILABLE\treason=not_found\n' "$command_name" >>"$COMMAND_LOG"
        return 1
    else
        command_status=$?
        printf 'root_command=%s\tstatus=UNAVAILABLE\treason=probe_failed\texit=%s\toutput=%s\n' \
            "$command_name" "$command_status" "$command_output" >>"$COMMAND_LOG"
        return 1
    fi
}
if probe_root_command ip; then ROOT_IP_AVAILABLE=true; else ROOT_IP_AVAILABLE=false; fi
if probe_root_command tc; then ROOT_TC_AVAILABLE=true; else ROOT_TC_AVAILABLE=false; fi
if probe_root_command tcpdump; then TCPDUMP_AVAILABLE=true; else TCPDUMP_AVAILABLE=false; fi

prepare_audio_trial() {
    [ "$AUDIO_TRIAL" = true ] || return 0
    trial_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    trial_jar="$trial_dir/M11L2wAudioTrial.jar"
    case "$trial_jar" in *[!A-Za-z0-9_./-]*) printf '工具路徑含不支援的字元\n' >&2; exit 1 ;; esac
    require_command sha256sum
    expected_trial_hash=864faf7fad602b6265c5df0595844dfbc872f47569cb74753f319d93a4e3ce3b
    trial_hash="$(sha256sum "$trial_jar")"
    trial_hash="${trial_hash%% *}"
    if [ "$trial_hash" != "$expected_trial_hash" ]; then printf 'SAE 工具版本不符，未送音訊要求\n' >&2; exit 1; fi
    probe_root_command timeout || { printf '缺少 root timeout，未送音訊要求\n' >&2; exit 1; }
    manager_jar=""
    for candidate in /system/system_ext/framework/imsmanager.jar /system_ext/framework/imsmanager.jar /system/framework/imsmanager.jar; do
        if su -c "test -f '$candidate'"; then manager_jar="$candidate"; break; fi
    done
    [ -n "$manager_jar" ] || { printf '找不到手機上的 imsmanager.jar，未送音訊要求\n' >&2; exit 1; }
    AUDIO_TRIAL_COMMAND="timeout 5 env CLASSPATH='$trial_jar' /system/bin/app_process /system/bin M11L2wAudioTrial '$manager_jar'"
    if ! su -c "$AUDIO_TRIAL_COMMAND preflight" >"$PRIVATE_ROOT/audio_trial_preflight.txt" 2>&1; then
        printf 'SAE preflight 未通過，停止。請提供 PRIVATE_ALL，不必進行通話切換。\n' >&2
        exit 1
    fi
    printf 'audio_trial=ARMED\tmode=one_request_direction_0\n' >>"$COMMAND_LOG"
}
prepare_audio_trial
if [ "$HANDOVER_CHECK" = true ]; then
    # Integrated SA2 has no opt-in property. APK identity and runtime SA2 logs
    # establish which code actually ran; the collector never enables a feature.
    printf 'audio_trial=DISABLED\thandover_check=READ_ONLY\tsa2_gate=NOT_REQUIRED\n' >>"$COMMAND_LOG"
fi

root_capture() {
    capture_label="$1"
    root_command="$2"
    if capture_output="$(su -c "$root_command" 2>&1)"; then
        capture_status=OK
        capture_exit=0
    else
        capture_exit=$?
        capture_status=FAILED
    fi
    {
        printf '\n--- %s | status=%s | exit=%s | at=%s ---\n' "$capture_label" "$capture_status" "$capture_exit" "$(date -Iseconds)"
        printf 'command=%s\n' "$root_command"
        if [ -n "$capture_output" ]; then printf '%s\n' "$capture_output"; else printf '[no output]\n'; fi
    } >>"$COMMAND_LOG"
}

write_marker() {
    marker_name="$1"
    printf '%s\t%s\n' "$(date -Iseconds)" "$marker_name" >>"$TIMELINE"
    if ! su -c "log -t CODEX_IMS_MEDIA_PROBE '$marker_name'" >>"$COMMAND_LOG" 2>&1; then
        printf 'marker_log_status=FAILED\tmarker=%s\n' "$marker_name" >>"$COMMAND_LOG"
    fi
}

capture_state() {
    state_label="$1"
    printf '\nstate_snapshot=%s\n' "$state_label" >>"$COMMAND_LOG"
    if [ "$ROOT_IP_AVAILABLE" = true ]; then
        root_capture "$state_label ip rule" 'ip rule show'
        root_capture "$state_label ip route" 'ip route show table all; ip -6 route show table all'
        root_capture "$state_label ip link" 'ip -o link show'
    else
        printf 'state_snapshot=%s\tstatus=UNAVAILABLE\treason=ip_missing_or_inaccessible\n' "$state_label" >>"$COMMAND_LOG"
    fi
}

discover_interfaces() {
    interface_file="$PRIVATE_ROOT/.interface_discovery.tmp"
    if [ "$ROOT_IP_AVAILABLE" != true ]; then
        printf 'interface_discovery=status=UNAVAILABLE\treason=ip_missing_or_inaccessible\n' >>"$COMMAND_LOG"
        INTERFACES=""
        return
    fi
    if discovered_links="$(su -c 'ip -o link show' 2>&1)"; then
        printf '\n--- media interface discovery | status=OK | at=%s ---\n%s\n' "$(date -Iseconds)" "$discovered_links" >>"$COMMAND_LOG"
    else
        discovery_exit=$?
        printf 'interface_discovery=status=FAILED\texit=%s\toutput=%s\n' "$discovery_exit" "$discovered_links" >>"$COMMAND_LOG"
        INTERFACES=""
        return
    fi
    printf '%s\n' "$discovered_links" >"$interface_file"
    INTERFACES=""
    interface_count=0
    while IFS= read -r link_line; do
        [ -n "$link_line" ] || continue
        interface_name="${link_line#*: }"
        interface_name="${interface_name%%:*}"
        interface_name="${interface_name%%@*}"
        case "$interface_name" in epdg*|rmnet_data*) ;; *) continue ;; esac
        case "$interface_name" in *[!A-Za-z0-9_.-]*) printf 'interface_rejected=status=UNSAFE_NAME\tname=%s\n' "$interface_name" >>"$COMMAND_LOG"; continue ;; esac
        # Count only usable links, not the preallocated DOWN epdg_data devices.
        # rmnet links can have state UNKNOWN: use flags rather than state UP.
        interface_flags="${link_line#*<}"
        interface_flags="${interface_flags%%>*}"
        case ",$interface_flags," in
            *,UP,*) ;;
            *) printf 'interface_skipped=name=%s\treason=not_admin_up\n' "$interface_name" >>"$COMMAND_LOG"; continue ;;
        esac
        case ",$interface_flags," in
            *,LOWER_UP,*) ;;
            *) printf 'interface_skipped=name=%s\treason=not_lower_up\n' "$interface_name" >>"$COMMAND_LOG"; continue ;;
        esac
        if [ "$interface_count" -ge "$MAX_INTERFACES" ]; then
            printf 'interface_discovery=status=TRUNCATED\tlimit=%s\n' "$MAX_INTERFACES" >>"$COMMAND_LOG"
            break
        fi
        duplicate=false
        for existing_interface in $INTERFACES; do
            if [ "$existing_interface" = "$interface_name" ]; then duplicate=true; fi
        done
        [ "$duplicate" = false ] || continue
        if [ -n "$INTERFACES" ]; then INTERFACES="$INTERFACES
$interface_name"; else INTERFACES="$interface_name"; fi
        interface_count=$((interface_count + 1))
    done <"$interface_file"
    rm -f "$interface_file"
    if [ -n "$INTERFACES" ]; then
        printf 'interface_discovery=status=MATCHED\tcount=%s\tinterfaces=%s\n' "$interface_count" "$INTERFACES" >>"$COMMAND_LOG"
    else
        printf 'interface_discovery=status=NO_ACTIVE_MATCHING_INTERFACES\n' >>"$COMMAND_LOG"
    fi
}

start_logcat() {
    pid_output="$(su -c "logcat -b all -v threadtime -T 1 > '$ROOT_LOGCAT' 2> '$ROOT_LOGCAT_ERR' & echo \$!" 2>>"$COMMAND_LOG" || true)"
    case "$pid_output" in
        ''|*[!0-9]*) printf 'logcat_status=UNAVAILABLE\tpid_output=%s\n' "$pid_output" >>"$COMMAND_LOG" ;;
        *) ROOT_LOGCAT_PID="$pid_output"; printf 'logcat_status=STARTED\tpid=%s\n' "$ROOT_LOGCAT_PID" >>"$COMMAND_LOG" ;;
    esac
}

start_tcpdump_for_interface() {
    capture_interface="$1"
    capture_base="$PRIVATE_ROOT/.root_${capture_interface}.pcap"
    capture_error="$PRIVATE_ROOT/.root_${capture_interface}.tcpdump.stderr.tmp"
    pid_output="$(su -c "tcpdump -i '$capture_interface' -s 96 -U -C 1 -W 2 -w '$capture_base' udp >/dev/null 2> '$capture_error' & echo \$!" 2>>"$COMMAND_LOG" || true)"
    case "$pid_output" in
        ''|*[!0-9]*) printf 'tcpdump_interface=%s\tstatus=UNAVAILABLE\tpid_output=%s\n' "$capture_interface" "$pid_output" >>"$COMMAND_LOG" ;;
        *)
            if [ -n "$TCPDUMP_PIDS" ]; then TCPDUMP_PIDS="$TCPDUMP_PIDS
$pid_output"; else TCPDUMP_PIDS="$pid_output"; fi
            printf 'tcpdump_interface=%s\tstatus=STARTED\tpid=%s\tfilter=udp\tsnaplen=96\trotation_mib=1x2\n' "$capture_interface" "$pid_output" >>"$COMMAND_LOG"
            ;;
    esac
}

stop_owned_pid() {
    owned_pid="$1"
    case "$owned_pid" in ''|*[!0-9]*) return ;; esac
    if su -c "kill -INT '$owned_pid'" >>"$COMMAND_LOG" 2>&1; then
        printf 'owned_pid=%s\tstop_status=SIGINT_SENT\n' "$owned_pid" >>"$COMMAND_LOG"
    else
        printf 'owned_pid=%s\tstop_status=FAILED_OR_ALREADY_EXITED\n' "$owned_pid" >>"$COMMAND_LOG"
    fi
}

stop_tcpdump_captures() {
    if [ -n "$TCPDUMP_PIDS" ]; then
        for owned_pid in $TCPDUMP_PIDS; do stop_owned_pid "$owned_pid"; done
        TCPDUMP_PIDS=""
    fi
}

stop_logcat() {
    if [ -n "$ROOT_LOGCAT_PID" ]; then
        stop_owned_pid "$ROOT_LOGCAT_PID"
        ROOT_LOGCAT_PID=""
    fi
}

stop_captures() {
    stop_tcpdump_captures
    stop_logcat
}

copy_root_private_file() {
    root_file="$1"
    local_file="$2"
    if su -c "test -f '$root_file'" >/dev/null 2>&1; then
        if su -c "cat '$root_file'" >"$local_file" 2>>"$COMMAND_LOG"; then
            printf 'private_artifact=%s\tstatus=COPIED\n' "${local_file##*/}" >>"$COMMAND_LOG"
            su -c "rm -f '$root_file'" >>"$COMMAND_LOG" 2>&1 || true
        else
            printf 'private_artifact=%s\tstatus=UNAVAILABLE\treason=root_copy_failed\n' "${local_file##*/}" >>"$COMMAND_LOG"
        fi
    else
        printf 'private_artifact=%s\tstatus=UNAVAILABLE\treason=not_created\n' "${local_file##*/}" >>"$COMMAND_LOG"
    fi
}

collect_root_artifacts() {
    copy_root_private_file "$ROOT_LOGCAT" "$PRIVATE_ROOT/logcat_all_private.txt"
    copy_root_private_file "$ROOT_LOGCAT_ERR" "$PRIVATE_ROOT/logcat_all_private.stderr.txt"
    if [ "$TCPDUMP_AVAILABLE" = true ] && [ -n "$INTERFACES" ]; then
        for capture_interface in $INTERFACES; do
            capture_base="$PRIVATE_ROOT/.root_${capture_interface}.pcap"
            capture_error="$PRIVATE_ROOT/.root_${capture_interface}.tcpdump.stderr.tmp"
            for suffix in 0 1; do
                root_file="$capture_base$suffix"
                local_file="$PRIVATE_ROOT/${capture_interface}_${suffix}.pcap"
                copy_root_private_file "$root_file" "$local_file"
            done
            copy_root_private_file "$capture_base" "$PRIVATE_ROOT/${capture_interface}.pcap"
            copy_root_private_file "$capture_error" "$PRIVATE_ROOT/${capture_interface}.tcpdump.stderr.txt"
        done
    elif [ "$TCPDUMP_AVAILABLE" != true ]; then
        printf 'packet_capture=status=UNAVAILABLE\treason=tcpdump_missing_or_inaccessible\n' >>"$COMMAND_LOG"
    fi
}

cleanup() { stop_captures; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

capture_state baseline
if [ "$HANDOVER_CHECK" = true ]; then
    root_capture 'SA2 Telecom identity' 'pm path com.android.server.telecom; for f in /system/priv-app/Telecom/Telecom.apk /system_ext/priv-app/Telecom/Telecom.apk; do if [ -f "$f" ]; then sha256sum "$f"; fi; done'
fi
write_marker baseline
start_logcat
printf '\n請在既有通話仍連線、目前為 LTE 時啟動此 probe。\n'
printf '採集版本：%s\n' "$PROBE_VERSION"
if [ "$HANDOVER_CHECK" = true ]; then
    printf 'SA2 自動切換驗證：此腳本只錄紀錄，不送任何音訊要求。\n'
else
    printf '這次切到 VoWiFi 後不要再切回 VoLTE。\n'
fi
if [ "$AUDIO_TRIAL" = true ]; then
    printf 'SAE 實驗已啟用：先錄 5 秒，再對符合條件的當前通話送一次三星音訊接管要求。\n'
fi
if [ "$HANDOVER_CHECK" = true ]; then
    printf '開啟 Wi-Fi；同一通電話切到 VoWiFi 時按 Enter（即使聲音正常），開始短暫採樣。\n'
else
    printf '保持 prompt 等待，執行一次 L2W；Wi-Fi 已連線且音訊靜音時立即按 Enter，開始最多 5 秒採樣。\n'
fi
if ! read -r -t "$MAX_WAIT_BEFORE_PROBE" _unused; then
    printf 'probe_status=NOT_RUN\treason=l2w_silent_confirmation_timeout\n' >>"$COMMAND_LOG"
    stop_captures
    collect_root_artifacts
    printf '未執行 media probe。私人輸出：%s\n' "$PRIVATE_ROOT"
    exit 0
fi

if [ "$HANDOVER_CHECK" = true ]; then write_marker L2W_user_observed; else write_marker L2W_silent; fi
discover_interfaces
if [ "$TCPDUMP_AVAILABLE" = true ] && [ -n "$INTERFACES" ]; then
    for capture_interface in $INTERFACES; do start_tcpdump_for_interface "$capture_interface"; done
elif [ "$TCPDUMP_AVAILABLE" != true ]; then
    printf 'packet_capture=status=UNAVAILABLE\treason=tcpdump_missing_or_inaccessible\n' >>"$COMMAND_LOG"
fi

printf 'probe_status=RUNNING\tplanned_seconds=%s\n' "$PROBE_SECONDS" >>"$COMMAND_LOG"
probe_started_at="$SECONDS"
probe_deadline=$((probe_started_at + PROBE_SECONDS))
sample_number=1
while [ "$SECONDS" -lt "$probe_deadline" ]; do
    sample_elapsed=$((SECONDS - probe_started_at))
    printf '\n--- media sample %02d | elapsed_s=%s | at=%s ---\n' "$sample_number" "$sample_elapsed" "$(date -Iseconds)" >>"$COMMAND_LOG"
    if [ "$ROOT_IP_AVAILABLE" = true ]; then
        root_capture "sample $sample_number ip counters all links" 'ip -s link show'
    else
        printf 'sample=%s\tip_counters_status=UNAVAILABLE\treason=ip_missing_or_inaccessible\n' "$sample_number" >>"$COMMAND_LOG"
    fi
    if [ -n "$INTERFACES" ]; then
        for capture_interface in $INTERFACES; do
            if [ "$ROOT_TC_AVAILABLE" = true ]; then
                root_capture "sample $sample_number $capture_interface tc qdisc counters" "tc -s qdisc show dev '$capture_interface'"
                root_capture "sample $sample_number $capture_interface tc parent 1 filter counters" "tc -s filter show dev '$capture_interface' parent 1:"
                root_capture "sample $sample_number $capture_interface tc parent ffff filter counters" "tc -s filter show dev '$capture_interface' parent ffff:"
            else
                printf 'sample=%s\tinterface=%s\ttc_status=UNAVAILABLE\treason=tc_missing_or_inaccessible\n' "$sample_number" "$capture_interface" >>"$COMMAND_LOG"
            fi
        done
    else
        printf 'sample=%s\tcounters_status=UNAVAILABLE\treason=no_matching_interfaces\n' "$sample_number" >>"$COMMAND_LOG"
    fi
    next_sample_at=$((probe_started_at + sample_number))
    sleep_seconds=$((next_sample_at - SECONDS))
    if [ "$sleep_seconds" -gt 0 ]; then sleep "$sleep_seconds"; fi
    sample_number=$((sample_number + 1))
done
probe_elapsed=$((SECONDS - probe_started_at))
printf 'probe_status=COMPLETE\tplanned_seconds=%s\tactual_elapsed_s=%s\tsamples=%s\n' \
    "$PROBE_SECONDS" "$probe_elapsed" "$((sample_number - 1))" >>"$COMMAND_LOG"
if [ "$HANDOVER_CHECK" = true ]; then write_marker L2W_probe_end; else write_marker L2W_silent_probe_end; fi
if [ "$AUDIO_TRIAL" = true ]; then
    write_marker sae_trial_request_begin
    if su -c "$AUDIO_TRIAL_COMMAND start-sae" >"$PRIVATE_ROOT/audio_trial_result.txt" 2>&1; then
        write_marker sae_trial_request_returned
    else
        write_marker sae_trial_failed_or_timed_out_no_retry
    fi
    # Keep the bounded PCAPs running across the intervention. No forced mode,
    # STOP request, network mutation or repeat audio request is performed.
    post_deadline=$((SECONDS + 3))
    while [ "$SECONDS" -lt "$post_deadline" ]; do
        if [ "$ROOT_IP_AVAILABLE" = true ]; then root_capture 'post SAE ip counters' 'ip -s link show'; fi
        sleep 1
    done
    write_marker sae_trial_post_sample_end
    printf '請記住音訊是否恢復。保持原通話與 Wi-Fi 開啟。\n'
fi
stop_tcpdump_captures

if [ "$HANDOVER_CHECK" = true ]; then
    printf '\n先讓同一通 VoWiFi 通話滿 30 秒。關閉 Wi-Fi 時立即按 Enter，不要掛斷或重撥。\n'
    if read -r -t 45 _unused; then
        write_marker W2L_user_wifi_off
        printf '維持原通話。若自動掛斷，立即按 Enter；否則等待 40 秒採集結束。請記住雙向切換的聲音中斷時間。\n'
        if read -r -t 40 _unused; then write_marker user_observed_call_ended_after_W2L; else write_marker W2L_observation_window_complete; fi
    else
        write_marker W2L_not_marked_before_timeout
    fi
    capture_state after_handover_check
else
printf '\n短暫 media probe 已結束。保持 Wi-Fi 開啟，不重撥、不主動掛斷。\n'
printf '若電話自動掛斷，立即按 Enter；若仍連線，等待最多 %s 秒讓腳本自行結束。\n' "$MAX_WAIT_AFTER_PROBE"
if read -r -t "$MAX_WAIT_AFTER_PROBE" _unused; then
    write_marker user_observed_call_ended_while_wifi_on
else
    write_marker call_end_not_confirmed_before_timeout
fi
capture_state after_wait_wifi_unchanged
fi
stop_logcat
collect_root_artifacts
printf '\nMedia probe 完成。私人輸出（含 logcat 與封包資料）：%s\n' "$PRIVATE_ROOT"
printf '請勿分享 PRIVATE_ALL；它可能包含 IP、RTP/SIP 片段及 IMS 內部資訊。\n'
