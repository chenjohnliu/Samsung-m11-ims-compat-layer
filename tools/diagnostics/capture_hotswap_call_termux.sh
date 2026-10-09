#!/data/data/com.termux/files/usr/bin/bash
# Read-only SIM hot-swap -> failed VoLTE call capture for rooted SM-M115F.

set -u

if [ "$(id -u)" != "0" ]; then
    self="$(readlink -f "$0")"
    exec su -c "PATH='$PATH' HOME='$HOME' PREFIX='$PREFIX' '$PREFIX/bin/bash' '$self' --root"
fi

stamp="$(date +%Y%m%d_%H%M%S)"
base="${M11_CAPTURE_DIR:-$HOME/m11q-captures}"
out="$base/hotswap_call_$stamp"
mkdir -p "$out"

run_capture() {
    name="$1"
    shift
    {
        echo "captured_at=$(date -Ins)"
        echo "command=$*"
        "$@"
    } >"$out/$name.txt" 2>&1 || true
}

snapshot() {
    prefix="$1"
    run_capture "${prefix}_getprop" getprop
    run_capture "${prefix}_processes" ps -A
    run_capture "${prefix}_services" service list
    run_capture "${prefix}_telephony_registry" dumpsys telephony.registry
    run_capture "${prefix}_telecom" dumpsys telecom
    run_capture "${prefix}_phone" dumpsys phone
    run_capture "${prefix}_ims" dumpsys ims
    run_capture "${prefix}_carrier_config" dumpsys carrier_config
    run_capture "${prefix}_connectivity" dumpsys connectivity
}

cleanup() {
    if [ -n "${logcat_pid:-}" ]; then
        kill "$logcat_pid" 2>/dev/null || true
        wait "$logcat_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "Capture directory: $out"
echo "Clearing logcat and starting a fresh all-buffer recording..."
logcat -b all -c || true
logcat -b all -v threadtime >"$out/logcat_all.txt" 2>&1 &
logcat_pid=$!

snapshot before

echo
echo "Now remove SIM1, insert it again, and wait for the VoLTE icon."
echo "If that was already done, simply continue."
printf "Press Enter when ready to place the test call... "
read -r _
snapshot after_hotswap

echo
echo "Manually place the test call. Wait until it connects, fails, or gets stuck."
echo "Do not reboot before finishing this capture."
printf "Press Enter after the call attempt has ended or become stuck... "
read -r _
snapshot after_call

run_capture after_call_audio dumpsys audio
run_capture after_call_dmesg dmesg
run_capture after_call_dropbox dumpsys dropbox --print

cleanup
logcat_pid=""

{
    echo "capture=$out"
    echo "started=$stamp"
    echo "finished=$(date -Ins)"
    echo "selinux=$(getenforce 2>/dev/null || echo unknown)"
    echo "imsservice=$(pidof com.sec.imsservice 2>/dev/null || true)"
    echo "phone=$(pidof com.android.phone 2>/dev/null || true)"
} >"$out/SUMMARY.txt"

archive="$out.tar.gz"
if tar -czf "$archive" -C "$base" "$(basename "$out")" 2>/dev/null; then
    echo
    echo "Done: $archive"
else
    echo
    echo "Done: $out"
    echo "Archive creation failed; send the whole directory instead."
fi
