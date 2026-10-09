# SA2 first automatic bidirectional capture — 07:51:20

## Status

**First 188 bidirectional test passed**, combining the runtime trace with
the user's subsequent audible-result confirmation. The same call retained
audible downlink through both transitions, with estimated interruptions
of about 1 s LTE → IWLAN and 0.5 s IWLAN → LTE. A subsequent ordinary
VoLTE call after hanging up also worked. These are user estimates, not
instrumented audio-gap measurements.
Full acceptance remains pending: two-way conversational audio and repeated
successful trials, including walking out of Wi-Fi coverage, are not proven
by this single 188 test.
No additional source change, ROM build, install or flash was performed
while reviewing it.

Input: `ims_media_probe_20261009_075120.zip`.
Private extraction: `D:/m11q/work/media-probe-20261009-075120/ims_media_probe_20261009_075120/PRIVATE_ALL`.
Line references below are to `logcat_all_private.txt` unless stated otherwise.
Do not publish the raw archive or its SIM/network identifiers.

## Identity and intervention controls

`command_status.txt` lines 2/7: collector `stock-audio-port-v6`,
`handover_check=READ_ONLY`, manual `audio_trial=DISABLED`, SA2 gate `stock1`.
The disabled field refers to the collector's manual SAE intervention,
not the enabled automatic Telecom trial.
Live `/system/priv-app/Telecom/Telecom.apk` SHA256 (line 155):
`daafeef35128910235b94d1f4b432238726c19e1eb73af738518ee1de9923f2e`.
No local product-hash comparison was made in this review; runtime SA2
markers establish that its code executed, not that every ROM artifact
matches a previously verified product.

## Native timeline

| Event | Time | Log line |
| --- | --- | --- |
| ePDG L2W success | 07:51:37.513 | 4737 |
| SA2 STOP(2) | 07:51:37.841 | 5268 |
| CP OFF / MODE_NORMAL | 07:51:37.915 | 5444–5445 |
| Wi-Fi ON / MODE_IN_COMMUNICATION | 07:51:38.108 / .176 | 5968 / 6046 |
| SA2 SAE(0) | 07:51:38.185 | 6091 |
| SAE initialize / channel start | 07:51:38.354 / .398 | 6236 / 6293 |
| First logged SAE RTP processing | 07:51:38.422 | 6312 |
| WaveOut / WaveIn open | 07:51:38.689 / 07:51:39.013 | 6387 / 6544 |
| SA2 INFORM(7), L2W sequence returned | 07:51:39.032 / .033 | 6592–6593 |
| Wi-Fi disabling / native W2L start | 07:52:08.639 / .673 | 10131 / 10211 |
| ePDG W2L success | 07:52:09.065 | 10898–10899 |
| SA2 slot parameter / CPVE(1) | 07:52:09.183 / .190 | 11305 / 11335 |
| Wi-Fi OFF / MODE_NORMAL / CP ON | 07:52:09.192 / .193 / .197 | 11353–11368 |
| SA2 MODE_IN_CALL, W2L sequence returned | 07:52:09.685 / .686 | 11874–11875 |
| HAL cellular voice usecase starts / status 0 | 07:52:10.425 / .693 | 13338 / 13700 |
| Observation complete | 07:52:54.049 | 14731 |

The manual W2L marker at 07:52:13.903 is late relative to the native
Wi-Fi-disabling event. Do not use it as the handover start time.
Measured intervals here are software events, **not measured audible gaps**.
In particular, HAL voice startup occurs about 2.05 s after disabling;
neither that interval nor API completion proves compliance with the
two-second audio-gap requirement.

## Call identity and media evidence

Seven Android IMS updates retain the same session object and call ID 1
in ESTABLISHED state across network type 13 → 18 → 13 (lines 4911, 5804,
6109, 6600, 10981, 11365, 12548). All 15 Telecom call updates refer to
TC@1 ACTIVE. No session replacement or redial is visible.

SAE logs 1,561 RTP processing events from 07:51:38.422 through
07:52:09.668, spanning roughly 31 s before normal W2L engine shutdown.
The maximum adjacent log timestamp gap is 171 ms; seven sequence steps
are non-unit. This is processing evidence, not an end-to-end loss or
playout measurement.

Read-only packet parser results for the short L2W window:

- ePDG: 261 downlink RTP candidates, 38 uplink RTP candidates, 3 RTCP packets.
- Cellular clone interface: 260 downlink RTP candidates and 1 RTCP packet.
- Downlink sequences in each individual capture are contiguous; uplink
  sequences are contiguous, with variable timestamp steps consistent
  with lower-rate silence packets, not proof of conversational uplink.
- 257 captured IP prefixes match across interfaces; differing capture
  start/stop times prevent treating unmatched totals as packet loss.

No `SA2 aborted`, fatal exception, RTP Timeout, call-session termination,
call ENDED, or specific SIP 487 / error 5065 failure was found through
the capture end. This is absence of observed failure, not proof of
audibility throughout the W2L observation. W2L has no packet capture.
The later ePDG callback unregistration at 07:52:25.433 is part of
Wi-Fi service unload, not a recorded call termination.

## User confirmation and remaining acceptance

After the trace review, the user confirmed the destination was 188,
audible downlink was retained throughout apart from the brief transition
gaps, LTE → IWLAN paused about 1 s, IWLAN → LTE about 0.5 s, and the
subsequent ordinary VoLTE call worked after hanging up.
That later call is user-confirmed, not present in this archive; internal
final call-end parameter cleanup remains unobserved in this capture.

Keep the current stock-derived implementation and experiment scope.
Next validate two-way person-to-person conversation and three successful
trials per required scenario. Walking out of Wi-Fi coverage remains
untested here. Initial-IWLAN calls, rapid toggles, other carriers and
excluded call types are not covered by this result. Do not add speculative
recovery code to a positive trace.
