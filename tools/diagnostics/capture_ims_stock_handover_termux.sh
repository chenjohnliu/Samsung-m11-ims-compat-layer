#!/system/bin/sh
# Root-only, read-only IMS handover capture for stock Android 12 / Termux.
# Private artifacts can contain subscriber identities, IP addresses and IPsec keys.

set -u
umask 077

BASE=/data/local/tmp/m11q_ims_capture
DOWNLOAD=/sdcard/Download
FILTER='ip proto 50 or (ip6 and (ip6[6] = 50 or (ip6[6] = 44 and ip6[40] = 50))) or port 5060 or port 5061 or port 5067'
MAX_BYTES=134217728
PATH=/system/bin:/system/xbin:/vendor/bin:/data/data/com.termux/files/usr/bin
export PATH

usage() {
    cat <<'EOF'
Usage (run from a root shell):
  sh capture_ims_stock_handover_termux.sh start LABEL [seconds]
  sh capture_ims_stock_handover_termux.sh mark TOKEN
  sh capture_ims_stock_handover_termux.sh status
  sh capture_ims_stock_handover_termux.sh stop
  sh capture_ims_stock_handover_termux.sh export
  sh capture_ims_stock_handover_termux.sh doctor
  sh capture_ims_stock_handover_termux.sh help

Example from Termux:
  su -c 'sh /sdcard/Download/capture_ims_stock_handover_termux.sh start stock_hotspot'
  su -c 'sh /sdcard/Download/capture_ims_stock_handover_termux.sh mark wifi_off'
  su -c 'sh /sdcard/Download/capture_ims_stock_handover_termux.sh stop'
  su -c 'sh /sdcard/Download/capture_ims_stock_handover_termux.sh export'
Run doctor first. Capture is private under /data/local/tmp; export explicitly when ready.
EOF
}

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
is_root() { [ "$(id -u 2>/dev/null)" = 0 ]; }
need_root() {
    if ! is_root; then
        printf 'Root is required. In Termux run: su -c '\''sh /sdcard/Download/capture_ims_stock_handover_termux.sh %s'\''\n' "$*" >&2
        exit 1
    fi
}
valid_token() {
    case "$1" in ''|*[!A-Za-z0-9_-]*) return 1 ;; esac
    [ "${#1}" -le 48 ]
}
valid_label() {
    case "$1" in ''|*[!A-Za-z0-9_-]*) return 1 ;; esac
    [ "${#1}" -le 40 ]
}
now() { date '+%Y%m%d_%H%M%S'; }
active_file() { printf '%s/active' "$BASE"; }
read_active() {
    ACTIVE_INVALID=false
    af=$(active_file)
    if [ -L "$af" ]; then ACTIVE=; ACTIVE_INVALID=true; return; fi
    ACTIVE=$(cat "$af" 2>/dev/null) || ACTIVE=
    if [ -n "$ACTIVE" ] && ! safe_session "$ACTIVE"; then ACTIVE=; ACTIVE_INVALID=true; fi
}
safe_session() {
    case "$1" in "$BASE"/session_*) ;; *) return 1 ;; esac
    name=${1##*/}
    case "$name" in session_[A-Za-z0-9_-]*) ;; *) return 1 ;; esac
    case "$name" in *[!A-Za-z0-9_-]*) return 1 ;; esac
    [ "$1" = "$BASE/$name" ] && [ ! -L "$1" ] && [ -d "$1" ] || return 1
    [ "$(stat -c %u "$1" 2>/dev/null)" = 0 ] && [ "$(stat -c %a "$1" 2>/dev/null)" = 700 ]
}
atomic_write() {
    aw_path=$1; aw_value=$2
    printf '%s\n' "$aw_value" >"$aw_path.tmp.$$" && mv -f "$aw_path.tmp.$$" "$aw_path"
}
root_setup() {
    if [ -L "$BASE" ]; then fail 'Private root directory must not be a symlink'; fi
    [ -d "$BASE" ] || mkdir -m 700 "$BASE" || fail "Cannot create private root directory: $BASE"
    [ "$(stat -c %u "$BASE" 2>/dev/null)" = 0 ] || fail 'Private root directory is not owned by root'
    chmod 700 "$BASE" 2>/dev/null || fail 'Cannot secure private root directory'
    [ "$(stat -c %a "$BASE" 2>/dev/null)" = 700 ] || fail 'Private root directory is not mode 700'
}
require_tool() { command -v "$1" >/dev/null 2>&1 || fail "Required Android command unavailable: $1"; }

doctor() {
    need_root doctor
    missing=0
    printf 'uid=%s\n' "$(id -u)"
    for t in tcpdump logcat timeout tar gzip ip tc dumpsys getprop sha256sum stat awk df ps grep wc sed head du cp mv rm sleep date; do
        if command -v "$t" >/dev/null 2>&1; then printf '%s=available (%s)\n' "$t" "$(command -v "$t")"; else printf '%s=MISSING\n' "$t"; fi
    done
    [ -x /system/bin/nohup ] && printf 'android_nohup=available (/system/bin/nohup)\n' || printf 'android_nohup=MISSING\n'
    [ -x /system/bin/sh ] && printf 'android_sh=available\n' || printf 'android_sh=MISSING\n'
    [ -d /sdcard/Download ] && printf 'download_dir=available\n' || printf 'download_dir=missing\n'
    free_kb=$(df -k /data/local/tmp 2>/dev/null | awk 'END {print $4}')
    case "$free_kb" in ''|*[!0-9]*) printf 'free_space=UNKNOWN\n'; missing=1 ;; *) printf 'free_space_kib=%s\n' "$free_kb"; [ "$free_kb" -ge 262144 ] || missing=1 ;; esac
    printf 'notice=full ESP packets and xfrm state may contain sensitive IPsec keys; do not share archive\n'
    for t in tcpdump logcat timeout tar gzip ip tc dumpsys getprop sha256sum stat awk df ps grep wc sed head du cp mv rm sleep date; do command -v "$t" >/dev/null 2>&1 || missing=1; done
    [ -x /system/bin/nohup ] && [ -x /system/bin/sh ] || missing=1
    [ "$missing" -eq 0 ] || return 1
    tcpdump -D >/dev/null 2>&1 || { printf 'tcpdump_interfaces=FAILED\n'; return 1; }
    printf 'tcpdump_interfaces=readable\n'
}

start_capture() {
    need_root start
    label=$1; duration=${2:-900}
    valid_label "$label" || fail 'LABEL must be 1-40 characters from A-Z, a-z, 0-9, underscore or hyphen'
    case "$duration" in ''|*[!0-9]*|0[0-9]*) fail 'seconds must be a decimal integer without leading zeroes, from 60 through 1800' ;; esac
    [ "$duration" -ge 60 ] && [ "$duration" -le 1800 ] || fail 'seconds must be an integer from 60 through 1800'
    root_setup
    for t in tcpdump logcat timeout tar gzip ip tc dumpsys getprop sha256sum stat awk df ps grep wc sed head du cp mv rm sleep date; do require_tool "$t"; done
    [ -x /system/bin/nohup ] || fail 'Required Android command unavailable: /system/bin/nohup'
    free_kb=$(df -k "$BASE" | awk 'END {print $4}')
    case "$free_kb" in ''|*[!0-9]*) fail 'Could not verify free space before capture' ;; esac
    [ "$free_kb" -ge 262144 ] || fail 'At least 256 MiB free space is required before capture'
    tcpdump -D >/dev/null 2>&1 || fail 'tcpdump cannot enumerate interfaces; run doctor'
    LOCK=$BASE/active_lock
    mkdir "$LOCK" 2>/dev/null || fail 'Another capture command holds the active lock; run status and retry'
    trap 'rmdir "$LOCK" 2>/dev/null' 0
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    read_active
    [ "$ACTIVE_INVALID" = false ] || fail 'Active session pointer is unsafe or invalid; refusing to overwrite it'
    if [ -n "$ACTIVE" ]; then
        printf 'An active or unexported session already exists: %s\n' "$ACTIVE" >&2
        fail 'Use status, stop, or export before starting another session'
    fi
    stamp=$(now)
    session=$BASE/session_${stamp}_$$_${label}
    mkdir -m 700 "$session" || fail 'Could not create exclusive session directory'
    chmod 700 "$session" || fail 'Could not secure session directory'
    cp "$0" "$session/collector.sh" || fail 'Could not copy collector into private session'
    chmod 600 "$session/collector.sh" || fail 'Could not secure collector copy'
    printf 'created=%s\nlabel=%s\nplanned_seconds=%s\nfilter=%s\ncoverage_note=IPv6 extension-header chains beyond direct ESP and one fragment header are not covered\n' \
        "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$label" "$duration" "$FILTER" >"$session/session_info.txt"
    atomic_write "$(active_file)" "$session" || fail 'Could not set active session pointer'
    # Re-exec only the private, root-owned copy at the validated BASE path.
    supervisor_limit=$((duration + 120))
    /system/bin/nohup timeout --foreground -k 60 -s TERM "$supervisor_limit" /system/bin/sh "$session/collector.sh" __run "$session" "$duration" \
        </dev/null >>"$session/supervisor.console.txt" 2>&1 &
    pid=$!
    printf '%s\n' "$pid" >"$session/supervisor.pid"
    proc_starttime "$pid" >"$session/supervisor_start" || fail 'Could not record supervisor identity'
    supervisor_native=
    attempt=0
    while [ "$attempt" -lt 10 ] && [ -z "$supervisor_native" ]; do
        supervisor_native=$(find_native_child "$pid")
        case "$supervisor_native" in ''|*[!0-9]*) supervisor_native= ;; esac
        [ -n "$supervisor_native" ] || { sleep 1; attempt=$((attempt + 1)); }
    done
    [ -n "$supervisor_native" ] || fail 'Could not identify the owned supervisor process; use status and preserve the session'
    printf '%s\n' "$supervisor_native" >"$session/supervisor_native.pid"
    proc_starttime "$supervisor_native" >"$session/supervisor_native.start" || fail 'Could not record supervisor process identity'
    printf 'session=%s\nsupervisor_pid=%s\n' "$session" "$pid" >>"$session/session_info.txt"
    trap - 0 HUP INT TERM
    rmdir "$LOCK" 2>/dev/null || true
    # Readiness is written only by the supervisor after both critical collectors report alive.
    n=0
    while [ "$n" -lt 15 ]; do
        [ -f "$session/ready" ] && { printf 'Capture ready: %s\n' "$session"; return 0; }
        [ -f "$session/failed" ] && { cat "$session/failed" >&2; return 1; }
        sleep 1
        n=$((n + 1))
    done
    printf 'Startup has not reached ready state yet. Use status; do not assume capture is running.\n' >&2
    return 1
}

proc_starttime() {
    # /proc/PID/stat field 22; strip through the last ') ' because comm may contain spaces.
    psline=$(cat "/proc/$1/stat" 2>/dev/null) || return 1
    rest=${psline##*) }
    set -- $rest
    [ "$#" -ge 20 ] || return 1
    shift 19
    printf '%s' "$1"
}
proc_state() {
    psline=$(cat "/proc/$1/stat" 2>/dev/null) || return 1
    rest=${psline##*) }
    set -- $rest
    [ "$#" -ge 1 ] || return 1
    printf '%s' "$1"
}
owned_alive() {
    [ -r "$1/proc_token" ] || return 1
    opid=$(cat "$1/proc_token" 2>/dev/null) || return 1
    otick=$(cat "$1/proc_start" 2>/dev/null) || return 1
    case "$opid" in ''|*[!0-9]*) return 1 ;; esac
    [ "$(proc_starttime "$opid")" = "$otick" ] || return 1
    state=$(proc_state "$opid") || return 1
    [ -n "$state" ] && [ "$state" != Z ]
}
native_alive() {
    [ -r "$1/native_pid" ] && [ -r "$1/native_start" ] || return 1
    npid=$(cat "$1/native_pid" 2>/dev/null) || return 1
    ntick=$(cat "$1/native_start" 2>/dev/null) || return 1
    case "$npid" in ''|*[!0-9]*) return 1 ;; esac
    [ "$(proc_starttime "$npid")" = "$ntick" ] || return 1
    state=$(proc_state "$npid") || return 1
    [ -n "$state" ] && [ "$state" != Z ]
}
find_native_child() {
    parent=$1
    # Android ps provides a stable PID/PPID table. Accept only a direct child.
    ps -A -o PID,PPID 2>/dev/null | awk -v p="$parent" '$2 == p {print $1; exit}'
}
stop_child() {
    sd=$1
    if native_alive "$sd"; then
        npid=$(cat "$sd/native_pid"); kill -INT "$npid" 2>/dev/null || return 1
    fi
    if owned_alive "$sd"; then
        opid=$(cat "$sd/proc_token"); kill -INT "$opid" 2>/dev/null || return 1
    fi
    i=0
    while [ "$i" -lt 12 ]; do
        native_alive "$sd" || owned_alive "$sd" || return 0
        sleep 1; i=$((i + 1))
    done
    return 1
}
request_child_stop() {
    sd=$1
    if native_alive "$sd"; then npid=$(cat "$sd/native_pid"); kill -INT "$npid" 2>/dev/null || return 1; fi
    if owned_alive "$sd"; then opid=$(cat "$sd/proc_token"); kill -INT "$opid" 2>/dev/null || return 1; fi
    return 0
}
producer_alive() { owned_alive "$1" || native_alive "$1"; }
producer_running() { owned_alive "$1" && native_alive "$1"; }
monotonic_seconds() {
    ms=$(awk '{printf "%.0f", $1}' /proc/uptime 2>/dev/null) || return 1
    case "$ms" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s' "$ms"
}
launch_child() {
    name=$1; shift
    d=$SESSION/children/$name
    mkdir -m 700 "$d" || return 1
    # A per-collector timeout keeps capture bounded even if the supervisor disappears.
    child_limit=$((DURATION + 90))
    timeout --foreground -k 5 -s INT "$child_limit" "$@" >"$d/out" 2>"$d/stderr" &
    child=$!
    tick=$(proc_starttime "$child") || { kill -TERM "$child" 2>/dev/null; return 1; }
    printf '%s\n' "$child" >"$d/proc_token"
    printf '%s\n' "$tick" >"$d/proc_start"
    native=
    attempt=0
    while [ "$attempt" -lt 20 ] && [ -z "$native" ]; do
        native=$(find_native_child "$child")
        case "$native" in ''|*[!0-9]*) native= ;; esac
        [ -n "$native" ] || { sleep 1; attempt=$((attempt + 1)); }
    done
    [ -n "$native" ] || { kill -TERM "$child" 2>/dev/null; return 1; }
    native_tick=$(proc_starttime "$native") || { kill -TERM "$child" 2>/dev/null; return 1; }
    printf '%s\n' "$native" >"$d/native_pid"
    printf '%s\n' "$native_tick" >"$d/native_start"
    printf 'producer=%s timeout_pid=%s timeout_starttime=%s native_pid=%s native_starttime=%s started=%s command=%s\n' "$name" "$child" "$tick" "$native" "$native_tick" "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >>"$SESSION/producers.txt"
}
check_budget() {
    used=$(du -sk "$SESSION" 2>/dev/null | awk '{printf "%.0f", $1 * 1024}')
    case "$used" in ''|*[!0-9]*) return 1 ;; esac
    [ "$used" -le "$MAX_BYTES" ]
}
phone_idle() {
    phase=$1
    timeout 8 dumpsys telephony.registry >"$SESSION/idle_check_$phase.txt" 2>&1 || return 1
    # Require visible call-state fields and every reported value to be zero.
    grep -Eiq 'mCallState|CallState' "$SESSION/idle_check_$phase.txt" || return 1
    if grep -Ei 'mCallState|CallState' "$SESSION/idle_check_$phase.txt" | grep -Eiv '(mCallState|CallState)[^0-9]*0([^0-9]|$)' >/dev/null; then return 1; fi
    return 0
}
snapshot() {
    phase=$1
    if ! phone_idle "$phase"; then
        printf '%s=SKIPPED_PHONE_NOT_CONFIRMED_IDLE\n' "$phase" >>"$SESSION/snapshots.txt"
        return 0
    fi
    sd=$SESSION/$phase
    mkdir -m 700 "$sd" || return 1
    for pair in 'secims:dumpsys secims' 'audio:dumpsys audio' 'telecom:dumpsys telecom' 'connectivity:dumpsys connectivity' 'telephony_registry:dumpsys telephony.registry'; do
        name=${pair%%:*}; cmd=${pair#*:}
        timeout 10 sh -c "$cmd" >"$sd/$name.txt" 2>"$sd/$name.stderr" || printf '%s_exit=%s\n' "$name" "$?" >>"$sd/status.txt"
    done
    timeout 10 ip rule show >"$sd/ip_rule.txt" 2>&1 || true
    timeout 10 ip route show table all >"$sd/ip_route4.txt" 2>&1 || true
    timeout 10 ip -6 route show table all >"$sd/ip_route6.txt" 2>&1 || true
    printf '%s=CAPTURED_IDLE_CONFIRMED\n' "$phase" >>"$SESSION/snapshots.txt"
}
fingerprints() {
    {
        printf 'captured_at=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')"
        for prop in ro.build.fingerprint ro.build.version.incremental ro.build.version.release gsm.version.baseband; do
            printf '%s=%s\n' "$prop" "$(getprop "$prop" 2>/dev/null)"
        done
        for bin in /system/bin/tcpdump /system/bin/logcat /system/bin/ip /system/bin/tc /system/bin/dumpsys; do
            [ -f "$bin" ] && sha256sum "$bin" 2>/dev/null
        done
        for reference in /system/lib/libsec-ims.so /system/lib64/libsec-ims.so /vendor/lib/libsec-ims.so /vendor/lib64/libsec-ims.so /system/framework/framework.jar /system/framework/telephony-common.jar /system/framework/imsmanager.jar /system_ext/framework/imsmanager.jar; do
            [ -f "$reference" ] && sha256sum "$reference" 2>/dev/null
        done
        for pkg in com.sec.imsservice com.sec.epdg com.android.phone com.android.server.telecom; do
            printf '\n--- package %s ---\n' "$pkg"
            timeout 8 dumpsys package "$pkg" 2>&1 | grep -E -m 8 'versionName=|versionCode=|codePath=|firstInstallTime=|lastUpdateTime=' || true
            apk=$(pm path "$pkg" 2>/dev/null | sed -n '1s/^package://p')
            case "$apk" in /system/*|/system_ext/*|/product/*|/vendor/*|/apex/*) [ -f "$apk" ] && sha256sum "$apk" 2>/dev/null ;; esac
        done
    } >"$SESSION/fingerprints_private.txt" 2>&1
}
sample_state() {
    timeout 5 ip xfrm state >"$SESSION/xfrm_state.txt.tmp" 2>"$SESSION/xfrm_state.stderr"
    rc=$?; { printf '\n--- %s exit=%s ---\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$rc"; cat "$SESSION/xfrm_state.txt.tmp"; } >>"$SESSION/xfrm_state.txt"
    rm -f "$SESSION/xfrm_state.txt.tmp"
    printf '%s xfrm_state_exit=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$rc" >>"$SESSION/sampler_health.txt"
    timeout 5 ip -o link show >"$SESSION/links.txt.tmp" 2>"$SESSION/links.stderr"
    rc=$?; mv "$SESSION/links.txt.tmp" "$SESSION/links.txt"
    [ "$rc" -eq 0 ] || return
    while IFS= read -r line; do
        iface=${line#*: }; iface=${iface%%:*}; iface=${iface%%@*}
        case "$iface" in epdg*|rmnet_data*)
            case "$iface" in *[!A-Za-z0-9_.-]*) continue ;; esac
            flags=${line#*<}; flags=${flags%%>*}
            case ",$flags," in *,UP,*) ;; *) continue ;; esac
            link_state=$(printf '%s\n' "$line" | sed -n 's/.* state \([A-Z]*\).*/\1/p')
            case "$link_state" in UP|UNKNOWN) ;; *) continue ;; esac
            printf '\n--- %s interface=%s ---\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$iface" >>"$SESSION/link_counters.txt"
            timeout 5 ip -s link show dev "$iface" >>"$SESSION/link_counters.txt" 2>&1 || true
            if [ $((SAMPLE_COUNT % 3)) -eq 0 ]; then
                printf '\n--- %s interface=%s ---\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$iface" >>"$SESSION/tc_stats.txt"
                timeout 5 tc -s qdisc show dev "$iface" >>"$SESSION/tc_stats.txt" 2>&1 || true
                timeout 5 tc -s filter show dev "$iface" parent 1: >>"$SESSION/tc_stats.txt" 2>&1 || true
                timeout 5 tc -s filter show dev "$iface" parent ffff: >>"$SESSION/tc_stats.txt" 2>&1 || true
            fi
            ;; esac
    done <"$SESSION/links.txt"
}
stop_all_children() {
    stop_failed=0
    for d in "$SESSION"/children/*; do [ -d "$d" ] || continue; request_child_stop "$d" || stop_failed=1; done
    i=0
    while [ "$i" -lt 15 ]; do
        any_alive=0
        for d in "$SESSION"/children/*; do [ -d "$d" ] || continue; if producer_alive "$d"; then any_alive=1; fi; done
        [ "$any_alive" -eq 1 ] || break
        sleep 1; i=$((i + 1))
    done
    for d in "$SESSION"/children/*; do [ -d "$d" ] || continue; producer_alive "$d" && stop_failed=1; done
    printf '%s stop_children_failed=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$stop_failed" >>"$SESSION/producers.txt"
    return "$stop_failed"
}
supervisor() {
    SESSION=$1; DURATION=$2
    safe_session "$SESSION" || return 2
    mkdir -m 700 "$SESSION/children" || return 2
    trap 'finish_session stopped; exit 0' TERM INT
    fingerprints
    SAMPLE_COUNT=0
    snapshot pre
    # Both required streams use fixed paths and explicit rotation bounds.
    launch_child packet tcpdump -i any -s 0 -U -C 8 -W 4 -w "$SESSION/ims_private.pcap" "$FILTER" || { printf 'FAILED: tcpdump process launch failed\n' >"$SESSION/failed"; return 1; }
    launch_child logcat logcat -b all -v threadtime -f "$SESSION/logcat_private.txt" -r 8192 -n 3 || { printf 'FAILED: logcat process launch failed\n' >"$SESSION/failed"; stop_all_children || true; return 1; }
    sleep 2
    if ! producer_running "$SESSION/children/packet" || ! producer_running "$SESSION/children/logcat"; then
        printf 'FAILED: required tcpdump or logcat exited during startup\n' >"$SESSION/failed"; stop_all_children || true; return 1
    fi
    if ! grep -Eiq 'listening on|verbose output suppressed' "$SESSION/children/packet/stderr"; then
        printf 'FAILED: tcpdump did not confirm kernel capture startup; stderr: %s\n' "$SESSION/children/packet/stderr" >"$SESSION/failed"; stop_all_children || true; return 1
    fi
    if grep -Eiq 'kernel filter failed|falling back to userland|using userland' "$SESSION/children/packet/stderr"; then
        printf 'FAILED: tcpdump reported kernel filter failure; userspace fallback is not accepted\n' >"$SESSION/failed"; stop_all_children || true; return 1
    fi
    printf 'ready_at=%s\ntcpdump_alive=true\nlogcat_alive=true\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" >"$SESSION/ready"
    started=$(monotonic_seconds) || { printf 'FAILED: cannot read monotonic uptime\n' >"$SESSION/failed"; return 1; }
    deadline=$((started + DURATION)); SAMPLE_COUNT=0
    while :; do
        monotonic_now=$(monotonic_seconds) || { printf 'FAILED: cannot read monotonic uptime\n' >"$SESSION/failed"; return 1; }
        [ "$monotonic_now" -lt "$deadline" ] || break
        SAMPLE_COUNT=$((SAMPLE_COUNT + 1))
        printf '%s packet_alive=%s logcat_alive=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" \
            "$(producer_running "$SESSION/children/packet" && printf true || printf false)" \
            "$(producer_running "$SESSION/children/logcat" && printf true || printf false)" >>"$SESSION/producers.txt"
        sample_state
        if ! producer_running "$SESSION/children/packet" || ! producer_running "$SESSION/children/logcat"; then
            printf 'FAILED: critical producer exited unexpectedly at %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" >"$SESSION/failed"
            stop_all_children || true; return 1
        fi
        check_budget || { printf 'FAILED: session reached 128 MiB safety budget\n' >"$SESSION/failed"; stop_all_children || true; return 1; }
        sleep 5
    done
    printf 'duration_complete=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" >>"$SESSION/session_info.txt"
    finish_session timed || return 1
    snapshot post
    : >"$SESSION/post_snapshot_done"
}
finish_session() {
    reason=$1
    printf 'producer_end_requested=%s at=%s\n' "$reason" "$(date '+%Y-%m-%dT%H:%M:%S%z')" >>"$SESSION/producers.txt"
    stop_all_children || { printf 'FAILED: a producer did not stop; archive refused\n' >"$SESSION/failed"; return 1; }
    if [ -f "$SESSION/ready" ] && [ ! -f "$SESSION/failed" ]; then
        printf 'capture_result=READY_CAPTURE_STOPPED\n' >"$SESSION/capture_health.txt"
    else
        printf 'capture_result=FAILED_OR_INCOMPLETE\n' >"$SESSION/capture_health.txt"
    fi
    printf 'producer_stop=VERIFIED\nfinish=%s\n' "$reason" >>"$SESSION/capture_health.txt"
    for producer in packet logcat; do
        pdir=$SESSION/children/$producer
        bytes=$(wc -c <"$pdir/stderr" 2>/dev/null | tr -d ' ')
        printf '%s_stderr_bytes=%s\n' "$producer" "${bytes:-unknown}" >>"$SESSION/capture_health.txt"
        if [ "$producer" = packet ] && grep -Eiq 'dropped by kernel' "$pdir/stderr"; then
            grep -Ei 'dropped by kernel|captured|received by filter' "$pdir/stderr" >>"$SESSION/capture_health.txt"
        fi
    done
    return 0
}

status_cmd() {
    need_root status
    root_setup
    read_active
    [ "$ACTIVE_INVALID" = false ] || fail 'Active session pointer is unsafe or invalid; refusing to follow it'
    if [ -z "$ACTIVE" ]; then printf 'No active or unexported session.\n'; return 0; fi
    printf 'session=%s\n' "$ACTIVE"
    [ -f "$ACTIVE/ready" ] && printf 'readiness=READY\n' || printf 'readiness=NOT_READY\n'
    [ -f "$ACTIVE/failed" ] && { printf 'failure='; cat "$ACTIVE/failed"; }
    pid=$(cat "$ACTIVE/supervisor.pid" 2>/dev/null || true)
    native_pid=$(cat "$ACTIVE/supervisor_native.pid" 2>/dev/null || true)
    case "$native_pid" in ''|*[!0-9]*) printf 'supervisor_process=UNKNOWN_OR_LEGACY\n' ;; *) if pid_matches "$native_pid" "$ACTIVE/supervisor_native.start"; then printf 'supervisor_process=RUNNING pid=%s\n' "$native_pid"; else printf 'supervisor_process=EXITED pid=%s\n' "$native_pid"; fi ;; esac
    case "$pid" in ''|*[!0-9]*) printf 'timeout_guardian=UNKNOWN\n' ;; *) if pid_matches "$pid" "$ACTIVE/supervisor_start"; then printf 'timeout_guardian=RUNNING pid=%s\n' "$pid"; else printf 'timeout_guardian=EXITED pid=%s\n' "$pid"; fi ;; esac
    [ -f "$ACTIVE/producers.txt" ] && tail -n 8 "$ACTIVE/producers.txt"
}
pid_matches() {
    pm_pid=$1; pm_file=$2
    [ -r "$pm_file" ] || return 1
    pm_tick=$(cat "$pm_file" 2>/dev/null) || return 1
    [ "$(proc_starttime "$pm_pid" 2>/dev/null || true)" = "$pm_tick" ] || return 1
    pm_state=$(proc_state "$pm_pid" 2>/dev/null) || return 1
    [ -n "$pm_state" ] && [ "$pm_state" != Z ]
}
stop_cmd() {
    need_root stop
    root_setup
    LOCK=$BASE/active_lock; mkdir "$LOCK" 2>/dev/null || fail 'Another capture command is active'
    trap 'rmdir "$LOCK" 2>/dev/null' 0
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    read_active
    [ "$ACTIVE_INVALID" = false ] || fail 'Active session pointer is unsafe or invalid; refusing to follow it'
    [ -n "$ACTIVE" ] || { rmdir "$LOCK"; printf 'No capture session.\n'; return 0; }
    safe_session "$ACTIVE" || { rmdir "$LOCK"; fail 'Active pointer is invalid; refusing to act'; }
    SESSION=$ACTIVE
    pid=$(cat "$SESSION/supervisor.pid" 2>/dev/null || true)
    case "$pid" in ''|*[!0-9]*) pid= ;; esac
    native_pid=$(cat "$SESSION/supervisor_native.pid" 2>/dev/null || true)
    case "$native_pid" in ''|*[!0-9]*) native_pid= ;; esac
    if [ -n "$native_pid" ] && pid_matches "$native_pid" "$SESSION/supervisor_native.start"; then
        # Signal the actual __run shell first. The timeout guardian can exit too early
        # if signaled before the shell finishes its own collector shutdown trap.
        kill -TERM "$native_pid" 2>/dev/null || true
        n=0; while pid_matches "$native_pid" "$SESSION/supervisor_native.start" && [ "$n" -lt 20 ]; do sleep 1; n=$((n + 1)); done
        pid_matches "$native_pid" "$SESSION/supervisor_native.start" && fail 'Supervisor process has not exited; refusing archive'
    elif [ -z "$native_pid" ] && [ -n "$pid" ] && pid_matches "$pid" "$SESSION/supervisor_start"; then
        fail 'Legacy session has a live timeout guardian but no verified supervisor PID; refusing to signal an untracked process'
    fi
    # The actual supervisor has exited. It is now safe to ask its guardian to exit.
    if [ -n "$pid" ] && pid_matches "$pid" "$SESSION/supervisor_start"; then
        kill -TERM "$pid" 2>/dev/null || true
        n=0; while pid_matches "$pid" "$SESSION/supervisor_start" && [ "$n" -lt 10 ]; do sleep 1; n=$((n + 1)); done
        pid_matches "$pid" "$SESSION/supervisor_start" && fail 'Timeout guardian has not exited; refusing archive'
    fi
    # Recover a dead supervisor only by stopping its individually recorded child tokens.
    stop_all_children || { rmdir "$LOCK"; fail 'Producer stop could not be verified; archive refused'; }
    if [ ! -f "$SESSION/post_snapshot_done" ]; then
        snapshot post
        : >"$SESSION/post_snapshot_done"
    fi
    if [ ! -f "$SESSION/capture_health.txt" ]; then printf 'capture_result=FAILED_OR_INCOMPLETE\nproducer_stop=VERIFIED\nrecovered_after_supervisor_exit=true\n' >"$SESSION/capture_health.txt"; fi
    [ -f "$SESSION/ready" ] || printf 'readiness=NOT_READY; diagnostic bundle is incomplete\n' >>"$SESSION/capture_health.txt"
    printf 'stopped_at=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" >>"$SESSION/session_info.txt"
    rmdir "$LOCK" 2>/dev/null || true
    if [ -f "$SESSION/ready" ] && [ ! -f "$SESSION/failed" ]; then
        printf 'Capture stopped and verified. Use export to copy the private archive to Download.\n'
    else
        printf 'Collectors are stopped; this is an INCOMPLETE diagnostic capture. Use export to preserve the failure evidence.\n'
    fi
    trap - 0 HUP INT TERM
    rmdir "$LOCK" 2>/dev/null || true
}
export_cmd() {
    need_root export
    root_setup
    LOCK=$BASE/active_lock; mkdir "$LOCK" 2>/dev/null || fail 'Another capture command is active'
    trap 'rmdir "$LOCK" 2>/dev/null' 0
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    read_active
    [ "$ACTIVE_INVALID" = false ] || fail 'Active session pointer is unsafe or invalid; refusing to follow it'
    [ -n "$ACTIVE" ] || { rmdir "$LOCK"; fail 'No session is available to export'; }
    safe_session "$ACTIVE" || { rmdir "$LOCK"; fail 'Active pointer is invalid'; }
    SESSION=$ACTIVE
    [ -f "$SESSION/capture_health.txt" ] || { rmdir "$LOCK"; fail 'Session is not stopped and verified; run stop first'; }
    export_pid=$(cat "$SESSION/supervisor.pid" 2>/dev/null || true)
    case "$export_pid" in ''|*[!0-9]*) export_pid= ;; esac
    if [ -n "$export_pid" ] && pid_matches "$export_pid" "$SESSION/supervisor_start"; then
        fail 'Supervisor is still running; run stop before export'
    fi
    export_native_pid=$(cat "$SESSION/supervisor_native.pid" 2>/dev/null || true)
    case "$export_native_pid" in ''|*[!0-9]*) export_native_pid= ;; esac
    if [ -n "$export_native_pid" ] && pid_matches "$export_native_pid" "$SESSION/supervisor_native.start"; then
        fail 'Actual supervisor process is still running; run stop before export'
    fi
    for export_child in "$SESSION"/children/*; do
        [ -d "$export_child" ] || continue
        producer_alive "$export_child" && fail 'A collector is still running; run stop before export'
    done
    mkdir -p "$DOWNLOAD" || { rmdir "$LOCK"; fail 'Download directory unavailable; private root data is retained'; }
    label=$(sed -n 's/^label=//p' "$SESSION/session_info.txt" | head -n 1)
    valid_label "$label" || fail 'Stored session label is invalid; refusing export'
    basename=${SESSION##*/}; stamp=$(printf '%s\n' "$basename" | sed -E 's/^session_([0-9]{8}_[0-9]{6})_.*/\1/')
    target=$DOWNLOAD/ims_stock_handover_${stamp}_${label}_PRIVATE_ALL.tar.gz
    [ ! -e "$target" ] && [ ! -L "$target" ] || fail "Export target already exists: $target"
    tarfile=$BASE/.archive_$$.tar
    tmp=$target.tmp.$$
    printf 'archive_started=%s\ntarget=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$target" >>"$SESSION/archive_status.txt"
    (set -C; : >"$tarfile") 2>/dev/null || fail 'Cannot reserve private archive temporary path'
    tar -cf - -C "$BASE" "${SESSION##*/}" >"$tarfile" 2>>"$SESSION/archive_errors.txt" || { printf 'tar_status=FAILED\n' >>"$SESSION/archive_status.txt"; rm -f "$tarfile"; fail 'tar failed; private session retained'; }
    chmod 600 "$tarfile" 2>/dev/null || true
    (set -C; : >"$tmp") 2>/dev/null || { rm -f "$tarfile"; fail 'Cannot reserve export temporary path'; }
    gzip -c "$tarfile" >"$tmp" 2>>"$SESSION/archive_errors.txt" || { printf 'gzip_status=FAILED\n' >>"$SESSION/archive_status.txt"; rm -f "$tarfile" "$tmp"; fail 'gzip failed; private session retained'; }
    gzip -dc "$tmp" >/dev/null 2>>"$SESSION/archive_errors.txt" || { printf 'gzip_integrity_check=FAILED\n' >>"$SESSION/archive_status.txt"; rm -f "$tarfile" "$tmp"; fail 'gzip integrity verification failed; private session retained'; }
    [ -s "$tmp" ] || { rm -f "$tarfile" "$tmp"; fail 'Archive is empty; original data retained'; }
    (set -C; : >"$target") 2>/dev/null || { rm -f "$tarfile" "$tmp"; fail "Export target already exists or cannot be created: $target"; }
    if ! cat "$tmp" >"$target" || [ ! -s "$target" ]; then rm -f "$target" "$tarfile" "$tmp"; fail 'Could not publish verified archive; private session retained'; fi
    gzip -dc "$target" >/dev/null 2>>"$SESSION/archive_errors.txt" || { printf 'published_archive_integrity=FAILED\n' >>"$SESSION/archive_status.txt"; rm -f "$target" "$tarfile" "$tmp"; fail 'Published archive failed integrity verification; private session retained'; }
    rm -f "$tarfile" "$tmp"
    printf 'gzip_integrity_check=PASSED\npublished_archive_integrity=PASSED\npublished=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" >>"$SESSION/archive_status.txt"
    chmod 600 "$target" 2>/dev/null || true
    rm -f "$(active_file)"
    rmdir "$LOCK" 2>/dev/null || true
    trap - 0 HUP INT TERM
    printf 'PRIVATE archive exported: %s\nDo not share publicly: it contains identities, working IP addresses and IPsec state. Download permissions may not preserve root-only privacy. Original private data remains at %s\n' "$target" "$SESSION"
}
mark_cmd() {
    need_root mark
    token=$1; valid_token "$token" || fail 'TOKEN must be 1-48 characters from A-Z, a-z, 0-9, underscore or hyphen'
    root_setup; read_active; [ -n "$ACTIVE" ] && safe_session "$ACTIVE" || fail 'No valid active session'
    printf '%s\t%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$token" >>"$ACTIVE/markers.tsv"
    log -t M11Q_IMS_HANDOVER "$token" >/dev/null 2>&1 || printf 'Android log marker unavailable; local timestamp was recorded.\n' >&2
    printf 'Marker recorded: %s\n' "$token"
}

if [ "${1:-}" = __run ]; then
    need_root __run
    [ "$#" -eq 3 ] || exit 2
    SESSION=$2; DURATION=$3
    root_setup
    safe_session "$SESSION" || exit 2
    case "$DURATION" in ''|*[!0-9]*|0[0-9]*) exit 2 ;; esac
    [ "$DURATION" -ge 60 ] && [ "$DURATION" -le 1800 ] || exit 2
    supervisor "$SESSION" "$DURATION"
    run_rc=$?
    if [ "$run_rc" -ne 0 ]; then
        printf 'FAILED: supervisor ended with status=%s at %s\n' "$run_rc" "$(date '+%Y-%m-%dT%H:%M:%S%z')" >>"$SESSION/failed"
        stop_all_children || { printf 'FAILED: producer stop could not be verified\n' >>"$SESSION/failed"; exit 1; }
        if [ ! -f "$SESSION/capture_health.txt" ]; then
            printf 'capture_result=FAILED_OR_INCOMPLETE\nproducer_stop=VERIFIED\nreadiness=%s\n' \
                "$( [ -f "$SESSION/ready" ] && printf READY || printf NOT_READY )" >"$SESSION/capture_health.txt"
        fi
    fi
    exit "$run_rc"
fi
case "${1:-help}" in
    start) [ "$#" -ge 2 ] && [ "$#" -le 3 ] || { usage >&2; exit 2; }; start_capture "$2" "${3:-900}" ;;
    mark) [ "$#" -eq 2 ] || { usage >&2; exit 2; }; mark_cmd "$2" ;;
    status) [ "$#" -eq 1 ] || { usage >&2; exit 2; }; status_cmd ;;
    stop) [ "$#" -eq 1 ] || { usage >&2; exit 2; }; stop_cmd ;;
    export) [ "$#" -eq 1 ] || { usage >&2; exit 2; }; export_cmd ;;
    doctor) [ "$#" -eq 1 ] || { usage >&2; exit 2; }; doctor ;;
    help|-h|--help) usage ;;
    *) usage >&2; exit 2 ;;
esac
