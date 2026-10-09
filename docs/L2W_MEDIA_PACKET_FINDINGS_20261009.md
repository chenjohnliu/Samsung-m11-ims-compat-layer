# L2W silent-call packet findings — 2026-10-09

Latest follow-up: [one-shot SAE experiment](L2W_SAE_ONESHOT_EXPERIMENT_20261009.md).
The main CP control sequence matches, but a later wider comparison identified
stock Telecom STOP/SAE/DELAYED_MEDIA updates and SAE engine startup missing
from the failing capture. The earlier CP-only comparison below is not a full
audio-transition equivalence claim. No permanent ROM change has been made.

## Scope

Private input: `ims_media_probe_20261009_000516.zip`, validated and extracted
under `D:/m11q/work/media-probe-20261009-000516`. No device operations, ROM
builds or runtime source changes were performed. Do not publish the archive,
PCAP addresses, SIP identifiers or raw logcat.

## Confirmed timeline

- Collector version: `active-links-stay-wifi-v2`.
- 00:05:38.603: native ePDG L2W success; 00:05:38.828: handover result true.
- 00:05:38.817: IPsec connection result `mIkeError=0`.
- 00:05:39.410: user marker `L2W_silent`.
- 00:05:39–45: five counter samples, actual sample elapsed six seconds.
- 00:05:58.345: original native call session 7 ends with `RTP Timeout`.
- Android callId 10 ends with `networkType:18`, `isWifi:Y`,
  `userInitiated=false`. No W2L handover result/start was found in this capture.
- 00:05:59.664: user confirms ended while Wi-Fi remained on.

This capture now supports the user's observation that W2L is not required to
trigger the disconnection. Native RTP timeout precedes the framework reason
1401 mapping; the mapped rekey-failure name is not proof of an IKE rekey error.

## Packet evidence

Actual active interfaces were selected: `epdg1`, `rmnet_data0`, `rmnet_data1`.
All packet capture tools started successfully; tcpdump reported zero kernel
capture drops. The separate start/stop windows explain unequal packet counts;
they must not be reported as redirect packet loss.

- `epdg1`: 261 downlink RTP-header packets, payload type 116, one SSRC,
  sequence 778–1038 with every step 1 and timestamp steps 320.
- `rmnet_data1`: 260 packets of the same downlink flow, payload type 116,
  sequence 783–1042, every step 1 and timestamp steps 320. Linux cooked
  packet type is 0 (receive-side capture).
- Each also contains one packet on the adjacent RTCP flow.
- 257 captured IP prefixes match between the two captures, including the
  RTCP packet; thus 256 overlapping RTP packets match.
- No reverse-direction UDP flow is present in the selected capture window.
- `rmnet_data0` contains only a PCAP header (no captured UDP packets).

The read-only analyzer is `D:/m11q/tools/summarize_media_probe_pcap.py`.
It reports header candidates, not codec decoding or CP receipt. Snaplen 96
limits visibility; matching IP prefixes are not full-payload comparisons.

## Redirect evidence and limits

The `epdg1` ingress action redirects to `rmnet_data1`; its packet counter rises
throughout the silent interval. Packet-prefix matching also demonstrates
downlink receive-side visibility on the target. This rules out a complete
absence of tunnel downlink traffic or a completely absent downlink redirect
for these observed packets, not all possible media-path failures.

The earlier inference from flat rmnet link counters is superseded: target
packet capture does show downlink RTP despite flat link counters.
AF_PACKET visibility is not evidence that the modem/CP voice engine received
or decoded those packets. Uplink is not visible here; this does not by itself
prove that the remote endpoint received no audio or locate an uplink loss.

The old `tc` output is unreliable for parent selection: `root` on epdg1 prints
`parent ffff:` (the ingress action), and qdisc decoding emits `Deficit` warnings.
An empty rmnet `root` result must therefore not be called proof that its
`parent 1:` egress filter is absent. Any follow-up collection should explicitly
query `parent 1:` and `parent ffff:` and retain command outputs/errors.

## Next bounded investigation

Compare stock versus the current compatibility path at the modem/CP media
handover boundary and uplink redirect, using available stock artifacts first.
Existing CP bearer/signaling-mode calls occur but do not prove media receipt.
Do not patch timeouts, MTU, voice indication forwarding, redirect direction or
claim a specific CP root cause from this capture alone. No further flash or
repeat of the same probe is justified merely to reconfirm RTP timeout.

Evidence anchors: `command_status.txt` ingress action samples around
471–484 and 1547–1560; `logcat_all_private.txt` success 7805/7966,
CP control 8077/8155, timeout 9730, original session termination 9871/9875.

## Stock/source follow-up (2026-10-09)

Read-only inspection used active WSL source, not just the older exported netd
file. No ROM source was modified or build performed.

### Control-plane comparison

The successful stock L2W at 2026-10-04 16:00:15 has the same main CP sequence:
callStatus 3 / bearer 6 / needToSetSaMode 1; signaling mode 2, priority 255,
msgType 0; then callStatus 2 / callType 15 / bearer 6 and the same signaling
mode. Stock anchors 83960/84271/84709/84812 match current 8077/8155/8584/8635.
This does not prove all binary request bytes are equal, but supplies no basis
for inventing a missing voice-handover notification.

### Confirmed Samsung PRIO ABI mismatch, not yet a call-failure cause

Stock `stock_iwlan1/tc_state.txt` reports `prio 1:` on rmnet_data1 with
`flow enabled`. The active kernel agrees: its `tc_prio_qopt` adds an
`enable_flow` byte at offset 20 (padded size 24); Android 13 iproute2 has a
20-byte standard struct. Kernel `sch_prio.c` directly reads that extended
field and uses it to gate peek/dequeue. Modem flow control in
`net/rmnet_data/rmnet_data_vnd.c` calls `tc_qdisc_flow_control`.

However, iproute2 `addattr_nest_compat` appends an empty four-byte nested
attribute. With the default netd `prio` invocation, the option payload is
therefore 24 bytes, not 20. On this little-endian target its byte at offset
20 is the nested attribute length (4), which is nonzero. Thus kernel setup
need not reject the request or initialize a disabled flow. The ABI is wrong,
but that fact alone is **not** evidence that it causes this silent call.
Kernel dumps place the extended flow field where AOSP's print parser expects
nested attributes, explaining why displayed absence of `flow enabled` is
not equivalent to a disabled flow. Actual serialized/installed product
behavior still requires validation; do not blindly force flow enabled during
a modem-requested pause.

### Redirect counters are not a loss verdict

The active Samsung `net/sched/act_mirred.c` ingress-redirect branch calls
`netif_rx` but leaves `err` initialized to 1; it then increments overlimits
and returns `TC_ACT_SHOT` for the original packet. The clone can still arrive
on rmnet, as demonstrated by the PCAP. Consequently, ingress qdisc drops and
mirred overlimits cannot be treated as proof the redirected clone was lost.
This is an explanation of source behavior, not a proposal to alter kernel
redirect semantics.

### Corrected next collection query

The collector now queries explicit `parent 1:` (netd uplink filter) and
`parent ffff:` (legacy ingress filter), instead of interpreting `root`/modern
`ingress` aliases. It does not change any installed rules. No additional phone
test has been run; repeating RTP timeout alone remains unnecessary. The next
useful discriminator is the actual uplink filter/queue state, combined with
the modem media endpoint path, not another registration-success observation.

Source anchors under `/home/user/android/crdroid`:

- kernel/samsung/sdm450/include/uapi/linux/pkt_sched.h:130
- kernel/samsung/sdm450/net/sched/sch_prio.c:165
- kernel/samsung/sdm450/net/sched/act_mirred.c:153
- kernel/samsung/sdm450/net/sched/sch_api.c:1188
- external/iproute2/tc/q_prio.c:35
- external/iproute2/lib/libnetlink.c:910
- system/netd/server/OemNetdListener.cpp:188

## 00:38:28 follow-up capture

The v4 SAE intervention was rejected by the helper's incorrect PDN/RAT
registration guard before the audio write. It therefore does **not** test
the SAE hypothesis. See `L2W_SAE_ONESHOT_EXPERIMENT_20261009.md` for the v5
fix and validation; no ROM source was changed.

Explicit rmnet_data1 `parent 1:` output now confirms an installed egress
redirect to epdg1 with zero reported drops/overlimits. Between the two
samples its action counters increase from 8,740 bytes / 45 packets to
11,275 bytes / 60 packets. This is evidence of some uplink redirect activity,
not proof of uplink RTP or successful media delivery.

The bounded packet captures still contain only downlink media: epdg1 has
414 RTP candidates, rmnet_data1 418, with 410 matching RTP IP prefixes
plus one matching RTCP prefix. Different capture start/end boundaries
explain the non-identical counts; no reverse-direction UDP was observed.
The original session ends with RTP timeout at 00:39:08.953. These observations
remain consistent with a missing local media engine transition but do not
prove that cause; the requested discriminator has not yet been exercised.
