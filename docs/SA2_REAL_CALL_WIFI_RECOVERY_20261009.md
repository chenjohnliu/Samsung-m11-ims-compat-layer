# SA2 real conversation and VoWiFi recovery — 13:06:09

## Result and limits

User started an ordinary LTE call to a family member, entered Wi-Fi,
then walked into weak Wi-Fi coverage. User confirms two-way conversation
retained sound without a call drop. This adds real conversational evidence
to the earlier 188 downlink-only test; no instrumented gap measurement or
three consecutive walking trials is available.

Input: `ims_media_probe_20261009_130609.zip`.
Private extraction: `D:/m11q/work/media-probe-20261009-130609/ims_media_probe_20261009_130609/PRIVATE_ALL`.
Read-only ADB snapshots: `D:/m11q/work/sa2-live-state-20261009-1316`.
Raw files contain private identifiers and must not be published.
No phone setting, network, service or source implementation was changed.

Collector: stock-audio-port-v6, handover-check read-only, manual SAE
intervention disabled, automatic SA2 gate stock1. Telecom APK SHA256
matches the earlier 07:51:20 capture:
`daafeef35128910235b94d1f4b432238726c19e1eb73af738518ee1de9923f2e`.

## Same-call handovers

Archive log lines:

- 3005: 13:06:22.284 L2W success; stock STOP/SAE/INFORM sequence completes
  at 13:06:23.228 (4860).
- 10815: 13:06:50.732 W2L success; stock CPVE/cellular-mode sequence
  completes at 13:06:51.167 (11605).
- 11997: 13:06:51.407 IMS icon update explicitly reports VoLTE registered,
  VoWiFi not registered. The missing VoWiFi icon reflects real transport
  state, not merely an icon refresh failure.

All seven Android IMS session updates keep the same session object and
call ID 6 ESTABLISHED across LTE/IWLAN/LTE. No RTP Timeout, SA2 abort,
fatal exception or call-session termination was found in this archive.
The short L2W PCAP has 101 downlink and 122 uplink RTP candidates with
contiguous sequences within each flow. User confirmation, not packets
alone, establishes two-way audibility.

The actual W2L precedes the manual `W2L_user_wifi_off` marker by about
10 s. Wi-Fi was still enabled; Android's default-network callback reported
Wi-Fi unavailable around 13:06:50.240, with RSSI around -81 dBm. A later
explicit weak-signal event at -86 dBm occurs at 13:07:16, after W2L.
Thus the observed weak-coverage scenario succeeded, but this trace does
not establish that the RSSI-threshold event itself initiated W2L.

## Missing icon and self-recovery

The user reported the icon missing after the test, then spontaneously
returning while analysis was underway. Live logcat corroborates recovery:

- 13:11:07.469 Wi-Fi validates; RSSI about -47 dBm.
- 13:11:07.566 ePDG reports `TEpdg timer running`.
- 13:12:30.486 ePDG explicitly waits for that timer to expire.
- 13:12:57.422 TEPDG finishes; LTE-to-Wi-Fi is recommended and requested.
- 13:12:58.608 L2W succeeds.
- 13:12:59.275 normal mmtel/smsip registration returns on RAT 18.
- 13:12:59.285 icon update reports VoWiFi registered.

There is about 112 s between this Wi-Fi validation and VoWiFi registration.
It is not appropriate to call that entire interval a handover or audio
gap. The ePDG waiting timer is the directly observed gate to recovery.
Its initial configured duration and complete intervening restart history
were not established from the retained live log buffer.
The same wait-for-TEpdg strings exist in the older Samsung ePDG decoded
source (`work/epdg_mapcon_dex_20260913a/.../EpdgSubScription.smali`, lines
4070/12203); SA2 does not introduce this timer.

At the live snapshot: Wi-Fi enabled and connected with strong signal,
normal IMS profile REGISTERED, ePDG connected, registration failure
counter zero, permanent-stop false, and no current Telecom call.
This is recovery, not a currently stuck or disabled VoWiFi state.

## Decision

Preserve the audio implementation and Samsung timer policy. The observed
temporary icon disappearance is explained by LTE transport plus an
existing ePDG re-entry wait, not evidence that the new audio handover broke
registration. Recovery latency is a separate follow-up if reproducibly
unacceptable; this result does not justify speculative timer removal.
Three repeated conversational trials and other previously excluded cases
remain outside this single-test result.
