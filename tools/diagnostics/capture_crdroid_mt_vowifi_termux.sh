#!/data/data/com.termux/files/usr/bin/bash

set -eu
umask 077

if [ -d "$HOME/storage/shared" ]; then
    DEFAULT_OUTPUT_ROOT="$HOME/storage/shared/m11q_logs"
else
    DEFAULT_OUTPUT_ROOT="$HOME/m11q_logs"
fi

OUTPUT_ROOT="${1:-$DEFAULT_OUTPUT_ROOT}"
STAMP="$(date +%Y%m%d_%H%M%S)"
CAPTURE_ROOT="$OUTPUT_ROOT/$STAMP"
SHARE_ROOT="$CAPTURE_ROOT/SHARE_THIS"
PRIVATE_ROOT="$CAPTURE_ROOT/_PRIVATE_DO_NOT_SHARE"
RAW_LOG="$PRIVATE_ROOT/tagged_runtime_private.log"
RAW_ERROR="$PRIVATE_ROOT/tagged_runtime_private.stderr.txt"
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
require_command sed
require_command grep

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
    su -c "log -t CODEX_MT_WFC '$marker'" >/dev/null 2>&1 || true
    printf '%s' "$marker"
}

save_registration_summary() {
    destination="$1"
    su -c "dumpsys secims | grep -E 'SIM slot:|onRegistered: RAT =|updateRegistration:.*rat=' | tail -n 40" \
        >"$destination" 2>&1 || true
}

BUILD_FINGERPRINT="$(getprop ro.build.fingerprint 2>/dev/null || true)"
BUILD_INCREMENTAL="$(getprop ro.build.version.incremental 2>/dev/null || true)"
SECURITY_PATCH="$(getprop ro.build.version.security_patch 2>/dev/null || true)"
IMS_PACKAGE_PATH="$(pm path com.sec.imsservice 2>/dev/null | head -n 1 | sed 's/^package://')"
IMS_APK_SHA256="unavailable"
if [ -n "$IMS_PACKAGE_PATH" ]; then
    IMS_HASH_LINE="$(su -c "sha256sum '$IMS_PACKAGE_PATH'" 2>/dev/null || true)"
    IMS_APK_SHA256="${IMS_HASH_LINE%% *}"
    [ -n "$IMS_APK_SHA256" ] || IMS_APK_SHA256="unavailable"
fi

{
    printf 'captured_at=%s\n' "$(date -Iseconds)"
    printf 'build_fingerprint=%s\n' "$BUILD_FINGERPRINT"
    printf 'build_incremental=%s\n' "$BUILD_INCREMENTAL"
    printf 'security_patch=%s\n' "$SECURITY_PATCH"
    printf 'imsservice_path=%s\n' "$IMS_PACKAGE_PATH"
    printf 'imsservice_signed_apk_sha256=%s\n' "$IMS_APK_SHA256"
    printf 'root_available=true\n'
} >"$SHARE_ROOT/runtime_identity.txt"

save_registration_summary "$SHARE_ROOT/registration_before.txt"
su -c "dumpsys audio" >"$PRIVATE_ROOT/audio_before.txt" 2>&1 || true

LOGCAT_COMMAND="logcat -v threadtime -T 1 \
CODEX_MT_WFC:V \
M11qMtMedia:V \
CallAudioManager:V \
ImsIncomingCall:V \
CallStateMachine:V \
ResipVolteHandler:V \
ResipMediaHandler:V \
StackIF:V \
UserAgent:V \
M11qSveDiag:V \
SecVideoEngineImpl:V \
AudioFWInterface:V \
AudioPolicyManager:V \
AudioFlinger:V \
SELinux:V \
auditd:V \
'*:S' \
>'$RAW_LOG' 2>'$RAW_ERROR' & echo \$!"

ROOT_LOGCAT_PID="$(su -c "$LOGCAT_COMMAND")"
case "$ROOT_LOGCAT_PID" in
    ''|*[!0-9]*)
        printf '無法啟動 root logcat，回傳值：%s\n' "$ROOT_LOGCAT_PID" >&2
        exit 1
        ;;
esac
if ! su -c "kill -0 '$ROOT_LOGCAT_PID'" >/dev/null 2>&1; then
    printf 'root logcat 啟動後立刻結束，請查看：%s\n' "$RAW_ERROR" >&2
    exit 1
fi

sleep 2
START_MARKER="$(add_marker MT_VOWIFI_CAPTURE_START)"

printf '\n擷取已開始。\n'
printf '1. 確認 VoWiFi 圖示仍在。\n'
printf '2. 用公司話機打到手機並接聽。\n'
printf '3. 若雙方無聲，請等待它自行結束，不要提早掛斷。\n'
printf '4. 測試期間不要切換 Wi-Fi、行動數據、SIM 或飛航模式。\n\n'
printf '通話完全結束後，回到 Termux 按 Enter：'
read -r _unused

END_MARKER="$(add_marker MT_VOWIFI_CALL_FINISHED)"
sleep 2
save_registration_summary "$SHARE_ROOT/registration_after.txt"
su -c "dumpsys audio" >"$PRIVATE_ROOT/audio_after.txt" 2>&1 || true

printf '手機端聽得到公司話機嗎？(y/n)：'
read -r LOCAL_AUDIO
printf '公司話機聽得到手機端嗎？(y/n)：'
read -r REMOTE_AUDIO
printf '通話是否自行斷線？(y/n)：'
read -r AUTO_ENDED
printf '接聽後大約幾秒結束？：'
read -r DURATION
printf '測試前／通話中／結束後的 VoWiFi 圖示狀態：'
read -r ICON_STATE
printf '其他備註（沒有可直接按 Enter）：'
read -r NOTES

{
    printf 'capture_start=%s\n' "$START_MARKER"
    printf 'call_finished=%s\n' "$END_MARKER"
    printf 'local_heard_remote=%s\n' "$LOCAL_AUDIO"
    printf 'remote_heard_local=%s\n' "$REMOTE_AUDIO"
    printf 'call_auto_ended=%s\n' "$AUTO_ENDED"
    printf 'seconds_after_answer=%s\n' "$DURATION"
    printf 'vowifi_icon=%s\n' "$ICON_STATE"
    printf 'notes=%s\n' "$NOTES"
} >"$SHARE_ROOT/USER_OBSERVATIONS.txt"

cleanup
trap - EXIT INT TERM

TIMELINE_PATTERN='CODEX_MT_WFC|M11qMtMedia|CallAudioManager|Samsung MT VoWiFi audio path|secims|avc: denied|bindToNetwork|answerCall|updateAudioInterface|onUpdateAudioInterfaceResponse|reqId 225|processResponse: handle .* result|saeInitialize|saeCreateChannel|saeStartChannel|M11qSveDiag|WaveOut|WaveIn|Notify on Established|callstate: ESTABLISHED|callstate: ENDED|AudioSession|StartAllMedia|set to Audio F/W|errorCode=|CallState Terminated|setPhoneState|setMode|phone state|mode.*(IN_CALL|IN_COMMUNICATION)|setForceUse|routing|route|startOutput|startInput|createTrack|createRecord|AudioTrack|AudioRecord'

if [ -f "$RAW_LOG" ]; then
    grep -E "$TIMELINE_PATTERN" "$RAW_LOG" 2>/dev/null | \
        sed -E \
            -e 's#([sS][iI][pP]:|[tT][eE][lL]:)[^ >;]+#\1[redacted]#g' \
            -e 's#urn:gsma:imei:[^, ]+#urn:gsma:imei:[redacted]#g' \
            -e 's#(^|[^0-9A-Fa-f])\+?[0-9]{9,15}([^0-9A-Fa-f]|$)#\1[redacted-number]\2#g' \
            -e 's#(^|[^0-9])([0-9]{1,3}\.){3}[0-9]{1,3}([^0-9]|$)#\1[redacted-ipv4]\3#g' \
        >"$SHARE_ROOT/key_timeline_redacted.txt" || true
fi

ARCHIVE_PATH="$CAPTURE_ROOT/SHARE_THIS.tar.gz"
tar -czf "$ARCHIVE_PATH" -C "$SHARE_ROOT" .

printf '\n擷取完成。資料只保存在手機，腳本沒有任何上傳功能。\n'
printf '離開公司後，請提供這個檔案：\n%s\n' "$ARCHIVE_PATH"
printf '\n完整且可能含敏感資料的紀錄先不要分享：\n%s\n' "$PRIVATE_ROOT"
