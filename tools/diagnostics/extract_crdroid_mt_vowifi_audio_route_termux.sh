#!/data/data/com.termux/files/usr/bin/bash

set -eu
umask 077

if [ -d "$HOME/storage/shared/m11q_logs" ]; then
    DEFAULT_ROOT="$HOME/storage/shared/m11q_logs"
else
    DEFAULT_ROOT="$HOME/m11q_logs"
fi

CAPTURE_ROOT="${1:-}"
if [ -z "$CAPTURE_ROOT" ]; then
    CAPTURE_ROOT="$(find "$DEFAULT_ROOT" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1)"
fi

if [ -z "$CAPTURE_ROOT" ] || [ ! -d "$CAPTURE_ROOT" ]; then
    printf '找不到擷取資料夾。請把路徑當作第一個參數傳入。\n' >&2
    exit 1
fi

PRIVATE_ROOT="$CAPTURE_ROOT/_PRIVATE_DO_NOT_SHARE"
RAW_LOG="$PRIVATE_ROOT/tagged_runtime_private.log"
SHARE_ROOT="$CAPTURE_ROOT/AUDIO_ROUTE_SHARE_THIS"
ARCHIVE_PATH="$CAPTURE_ROOT/AUDIO_ROUTE_SHARE_THIS.tar.gz"

if [ ! -f "$RAW_LOG" ]; then
    printf '找不到原始 tag log：%s\n' "$RAW_LOG" >&2
    exit 1
fi

mkdir -p "$SHARE_ROOT"

redact() {
    sed -E \
        -e 's#([sS][iI][pP]:|[tT][eE][lL]:)[^ >;]+#\1[redacted]#g' \
        -e 's#urn:gsma:imei:[^, ]+#urn:gsma:imei:[redacted]#g' \
        -e 's#(^|[^0-9A-Fa-f])\+?[0-9]{9,15}([^0-9A-Fa-f]|$)#\1[redacted-number]\2#g' \
        -e 's#(^|[^0-9])([0-9]{1,3}\.){3}[0-9]{1,3}([^0-9]|$)#\1[redacted-ipv4]\3#g' \
        -e 's#([0-9A-Fa-f]{0,4}:){4,}[0-9A-Fa-f:]{1,39}#[redacted-ipv6]#g'
}

# The original capture already restricted logcat to IMS/SVE/audio tags.  Keep
# only state transitions and media-engine events; do not export the raw file.
ROUTE_PATTERN='CODEX_MT_WFC|M11qMtMedia|CallAudioManager|Samsung MT VoWiFi audio path|secims|avc: denied|callstate: ESTABLISHED|Notify on Established|errorCode=|CallState Terminated|set to Audio F/W|bindToNetwork|answerCall|updateAudioInterface|onUpdateAudioInterfaceResponse|reqId 225|processResponse: handle .* result|saeInitialize|saeCreateChannel|saeStartChannel|M11qSveDiag|WaveOut|WaveIn|AudioSession|StartAllMedia|setPhoneState|setMode|phone state|IN_CALL|IN_COMMUNICATION|setForceUse|routing|route|startOutput|stopOutput|startInput|stopInput|createTrack|createRecord|AudioTrack|AudioRecord|createAudioPatch|releaseAudioPatch'

grep -Ei "$ROUTE_PATTERN" "$RAW_LOG" 2>/dev/null | redact \
    >"$SHARE_ROOT/audio_route_timeline_redacted.txt" || true

for phase in before after; do
    source_file="$PRIVATE_ROOT/audio_${phase}.txt"
    destination="$SHARE_ROOT/audio_${phase}_summary_redacted.txt"
    if [ -f "$source_file" ]; then
        grep -Ei 'mode|phone state|communication|active client|output device|input device|route|strategy|audio patch|record client|playback client' \
            "$source_file" 2>/dev/null | redact >"$destination" || true
    fi
done

{
    printf 'source_capture=%s\n' "$(basename "$CAPTURE_ROOT")"
    printf 'raw_log_exported=false\n'
    printf 'generated_at=%s\n' "$(date -Iseconds)"
} >"$SHARE_ROOT/README.txt"

tar -czf "$ARCHIVE_PATH" -C "$SHARE_ROOT" .

printf '已在手機本機產生脫敏摘要；腳本沒有上傳功能。\n'
printf '請只提供：%s\n' "$ARCHIVE_PATH"
printf '不要提供：%s\n' "$PRIVATE_ROOT"
