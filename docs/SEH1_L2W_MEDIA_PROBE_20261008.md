# SEH1 L2W media probe (2026-10-08)

This is a bounded, read-only capture aid for the next at-home call test. It does
not establish that the installed APK matches the staged build and does not fix
or diagnose the audio failure by itself.

## Capture the silent VoWiFi phase

Copy `D:/m11q/tools/capture_ims_media_probe_termux.sh` from Windows to the
phone's Download folder manually. With Termux shared-storage permission already
available, run `bash /sdcard/Download/capture_ims_media_probe_termux.sh`.
Keep the original call connected on LTE. The script records a baseline and
starts private continuous logcat, then waits up to 30 seconds. While it waits,
perform one L2W on the same call. When Wi-Fi is connected and audio has gone
silent, press Enter immediately to mark `L2W_silent` and begin the short media
sample. Do not redial or toggle airplane mode. Sampling is planned for five
seconds; it records actual elapsed time and sample count because command
latency can affect cadence. With the original `sae-once-v5` or current
`stock-audio-port-v6` in the original probe mode, keep Wi-Fi
on after sampling: do not perform W2L or hang up. If the original call ends by
itself, press Enter promptly to mark `user_observed_call_ended_while_wifi_on`.
Otherwise allow the script to finish after at most 60 seconds of waiting; this
is marked `call_end_not_confirmed_before_timeout`, not a successful call test.
The final network snapshot does not alter Wi-Fi or call state.

The script captures timestamped `ip -s link` output plus qdisc and explicit
`parent 1:` / `parent ffff:` filter counters for discovered `epdg*` and
`rmnet_data*` interfaces. These are the installed netd uplink and legacy ingress
parents; do not use an empty `root` alias result as proof of no uplink rule.
It also captures
baseline and post-wait `ip rule`/route state, private continuous logcat through
the follow-up marker, and optional UDP packet headers. Interface names are
discovered from `ip -o link show`, validated before use, and limited to eight
links carrying both `UP` and `LOWER_UP` flags. Preallocated inactive
`epdg_data*` links no longer consume the limit. `state UNKNOWN` does not exclude
an otherwise active rmnet link. Skipped links and limit truncation are logged;
selection is not proof that a selected link carries this call's RTP.
If tcpdump is available, each interface gets at most two rotating files of
approximately 1 MB each (up to approximately 16 MB total). Packet capture uses snaplen 96;
it can include IP addresses and the beginning of SIP/RTP payloads. Everything
is stored under a timestamped `PRIVATE_ALL` directory below Termux's private
`$HOME/m11q_logs` by default. This avoids shared-storage defaults that may not
honor restrictive permissions. Keep the output private; inspect and redact it
before attaching it privately. Do not publish it.

The parent output directory is now created automatically. Timestamped capture
directories are still created exclusively; an existing capture is never
overwritten. Replace the old phone Download copy before testing and check that
the startup banner says `stock-audio-port-v6` (the earlier test used
`sae-once-v5`). Collection is read-only by default. For the new automatic
Telecom port, use `--handover-check` and the instructions in
`SA2_STOCK_TELECOM_AUDIO_PORT_20261009.md`, not `--start-sae`.
The separate opt-in `--start-sae` experiment changes the active call's audio
path once; follow `L2W_SAE_ONESHOT_EXPERIMENT_20261009.md` for its conditions,
additional JAR, checks and limitations. It is not part of read-only collection.

`command_status.txt` records whether root `ip`, `tc`, and `tcpdump` were
available, each command's success/failure and output, interface discovery
status, actual sample elapsed time/count, and any unavailable packet artifacts.
“No matching interface”, missing
tools, command errors, and absent capture files are distinct outcomes. None of
them means “no RTP.” No `ip xfrm` state or keys are collected. The script does
not install packages, push files, change settings, run calls, modify routes,
filters, interfaces, or network state, and it only signals the specific
logcat/tcpdump child PIDs it started.

## Reading the result

Use the full original call timeline and device logs alongside this probe. Its
link, qdisc/filter counters and AF_PACKET packets are data-plane observations;
they can show changes during the silent phase but cannot prove control-plane
rule decoding or delivery. AF_PACKET capture visibility also does not prove
which side could hear audio.
The probe cannot by itself distinguish uplink from downlink audio loss, prove
RTP media delivery to the remote endpoint, establish a CP rule, or prove the
installed APK version. Preserve the private output for analysis and share a
redacted subset only after reviewing it.
