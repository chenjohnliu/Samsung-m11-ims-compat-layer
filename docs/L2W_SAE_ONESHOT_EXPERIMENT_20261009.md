# L2W SAE one-shot experiment — 2026-10-09

## Evidence and objective

The earlier CP-only comparison was incomplete. During the successful stock
16:00:15 L2W, Telecom also sends audio-interface STOP, then SAE, then
DELAYED_MEDIA. The native stack subsequently runs `saeInitialize`, SVE
channel creation/start and RTP processing (stock log 84130/84855/84884/85570
onward). None of these audio-interface updates or SAE initialization appears
in the current failing L2W capture, although bearer/signaling-mode updates
do appear. The observed downlink RTP reaches Linux but does not prove a
running media engine exists to consume it.

Stock source route: SamsungCallAudioModeStateMachine → SamsungAudioEngine →
SecImsManager.changeAudioPath → GoogleImsService →
IVolteServiceModule.updateAudioInterface. The modern Android bridge does not
expose that stock Telecom extension. This is a concrete missing sequence,
not evidence for a speculative modem indication forwarding patch.

Before modifying Telecom/IMS/ROM, test whether one existing Samsung SAE
request starts the missing media engine and restores the same call. This
is a diagnostic intervention, **not a complete stock audio-state-machine
port**. It does not send STOP, force AudioManager mode, or send DELAYED_MEDIA.
A negative result cannot exclude those remaining stock stages.

## Files and operation

Copy both Windows files into the phone Download directory:

- `D:/m11q/tools/capture_ims_media_probe_termux.sh`
- `D:/m11q/tools/M11L2wAudioTrial.jar`

Run in Termux after an ordinary slot-0 TWM LTE 188 call is already connected:

```sh
bash /sdcard/Download/capture_ims_media_probe_termux.sh --start-sae
```

Startup banner: `sae-once-v5` for the original test, or the newer
`stock-audio-port-v6`, with SAE experiment enabled. Enable Wi-Fi on
the original call. As soon as it switches and audio becomes silent, press
Enter. The script records five seconds before the intervention, then issues
one SAE request and retains bounded packet capture for three more seconds.
Do not toggle Wi-Fi again, redial or hang up. On automatic disconnection,
press Enter; otherwise let the 60-second wait expire. Report whether the
188 announcement returned and whether the original call remained connected.
Keep the resulting PRIVATE_ALL private and attach it as a ZIP.

Without `--start-sae`, collection remains read-only. The new option explicitly
opts into one live-call audio request. Root preflight failure stops before
the transition; provide the preflight output rather than retrying the request.
Runtime can still fail due to Android permissions/class loading; do not bypass
permissions, disable SELinux, reinstall packages or retry automatically.

## Safety boundaries

The helper uses the installed imsmanager typed Binder proxy with the verified
`secims` descriptor, not hardcoded Binder transaction numbers. It checks:

- root, m11q, explicit legacy IWLAN;
- slot-0 operator 46697 and no second operator;
- exactly one non-video/non-downgraded/non-emergency slot-0 call, zero calls
  on slot 1 (stock getCallCount fields verified: total/video/downgraded/e911);
- normal IWLAN mmtel registration (`getCurrentRat() == 18` and ePDG active),
  phone 0, non-emergency/non-CMC profile;
- call counts again immediately before the request.

It calls `changeAudioPathForSlot(0, 0)` once, which the current Samsung service
forwards to `updateAudioInterface(0, 0)` (SAE). Checks are not an atomic call
transaction: use only this controlled single ordinary 188 call, with no other
call activity. The helper cannot establish audio recovery or exact session
identity merely from a successful Binder return; compare continuous logs and
the audible announcement. No call is created/terminated, no permanent setting
is written, and no network/filter/APN/timeout is changed. If the test worsens
audio, end this test call normally; do not apply it to another ongoing call.

The collector enforces a five-second helper timeout, does not retry after
failure/timeout, and logs the outcome as uncertain if the request may have
already been delivered. PCAP sizes remain capped per interface.

## Validation and identity

- Compiled against the actual Android13 framework jar with JDK11.
- 11 host call-count and 10 registration gate checks passed; no device APIs
  were invoked by them. Registration mocks exercise the actual reflective
  getter path, including IMS PDN 11 / IWLAN RAT 18 versus LTE RAT 13.
- D8 produced the standalone DEX; this was **not an Android ROM build**.
- Collector syntax/interface/directory tests and mocked opt-in/preflight/hash
  checks passed. The v5 correction has not yet run on a phone.
- JAR SHA256:
  `864faf7fad602b6265c5df0595844dfbc872f47569cb74753f319d93a4e3ce3b`.
- Source: `D:/m11q/tools/M11L2wAudioTrial.java`.

Positive: SAE engine initialization/channel startup, RTP consumption, audible
188 and same-session continuity support restoring the missing stock audio
transition in the compatibility layer. Negative: distinguish rejected request,
no engine startup, engine startup without packet consumption, and successful
packet consumption without audible output. Do not interpret a Binder return,
icon or re-registration as a pass. User builds/flashes remain untouched.

## 00:38:28 capture: rejected intervention, not an SAE negative

`ims_media_probe_20261009_003828.zip` contains a successful read-only
preflight, but `audio_trial_result.txt` says:

```text
SAE_TRIAL_FAILED: java.lang.IllegalStateException: No normal slot-0 IWLAN mmtel registration
```

There is no `SAE_TRIAL_REQUEST`; the audio write was never attempted. The
helper incorrectly compared Samsung `ImsRegistration.getNetworkType()` to
18. That getter returns PDN type (`mPdnType`, IMS=11), not RAT. The typed
registration has a separate `getCurrentRat()` getter, returning
`mCurrentRat`; it is also preserved in the Binder parcel. Logs at 00:38:49
show slot-0 mmtel, IMS PDN 11, ePDG active, and registration RAT 18.

v5 uses current RAT plus ePDG state and emits only non-identifying gate
fields (phone, PDN, RAT, ePDG/mmtel/emergency/CMC). It retains all previous
single-call/operator restrictions and performs no audio request on failed
checks. Replace **both** script and JAR; the pinned hash prevents mixed
versions. No ROM rebuild or reflash is needed for this correction.

The original call still ended with RTP timeout at 00:39:08.953. This confirms
the existing failure, but cannot tell whether SAE would restore sound:
the intended intervention did not occur.

## 00:48:30 capture: positive one-shot intervention

User result: the 188 announcement returned and the original call did not
disconnect. Archive: `ims_media_probe_20261009_004830.zip`, extracted privately
under `D:/m11q/work/media-probe-20261009-004830`.

The v5 helper accepts the actual registration (slot 0, IMS PDN 11, current
RAT 18, ePDG true, mmtel true, emergency false, CMC 0), prints exactly one
`SAE_TRIAL_REQUEST`, and returns. The native log corroborates delivery:

| Time (local) | Evidence |
| --- | --- |
| 00:48:42.510 / .740 | ePDG L2W success / successful result callback |
| 00:48:43.055 | Original Android callId 13, same session object, now IWLAN |
| 00:48:44 | User marks silent L2W |
| 00:48:50.609 | `VolteServiceModule.updateAudioInterface(0, 0)` |
| 00:48:50.644 | `ResipMediaHandler.saeInitialize`, SAE initialized |
| 00:48:50.645–.659 | Channel creation, AMR-WB/PT116 configuration, start |
| 00:48:50.660 | First SAE RTP processing on that channel |
| 00:48:50.677 / .734 | WaveOut / WaveIn opened through existing SVE ABI compatibility |
| 00:48:50.857 | First observed uplink RTP in epdg1 packet capture |
| 00:49:55.587 | SAE still processing RTP when collection ends |

The call-profile callback at 00:48:50.622 still identifies Android callId
13 and the same established session object as before the request. No
`callSessionTerminated`, native `ENDED`, or RTP timeout appears in this
capture. The script's final `call_end_not_confirmed_before_timeout` marker
is only a manual-observation boundary, not by itself a call-state proof.
Continuous media logs and the user's audible result supply the supporting
evidence. Recorded post-request media activity lasts approximately 65 s.

PCAP now adds the previously absent uplink: epdg1 observes 36 RTP candidates
and one RTCP packet from the phone, starting after the SAE request, while
downlink RTP exists before and after it. Downlink counts are epdg1 518 and
rmnet_data1 517; 513 RTP prefixes plus two RTCP prefixes match across those
interfaces. There is one sequence jump of four in each downlink capture;
this does not establish a new media failure. Uplink does not traverse the
same rmnet capture point as downlink, so its absence there is not a loss
verdict. No remote two-way speech quality is proven by an automated 188
announcement or local packet observations.

### Conclusion and next implementation boundary

For this controlled failing L2W, selecting Samsung's existing SAE path is
an effective intervention: it starts the missing application media engine,
restores audible downlink, adds observed uplink RTP, and prevents the prior
approximately 20-second RTP-timeout termination during the recorded window.
This is much stronger evidence than registration/icon changes. It supports
the missing Samsung Telecom audio-selection callback as the actionable
compatibility gap, not a need to invent new modem handover signaling.

It is **not** final seamless-handover acceptance: the request was delayed
manually until about eight seconds after L2W, exact audible recovery time
was not measured, and neither automatic invocation nor subsequent W2L after
SAE activation was tested. One successful call also does not validate every
carrier, incoming/held/multiple/emergency call, or fast-toggle case.

The next ROM trial should automatically select SAE on the established,
owned ordinary slot-0 TWM call's LTE-to-IWLAN transition, once per actual
transition. It must not use a global Wi-Fi toggle or registration-only event
as proof of a call handover, trigger on an initial IWLAN call, or repeat on
duplicate profile updates. Preserve backend epoch/session ownership and
invalidate pending work on termination/disposal/transport reversal. Native
target/profile/registration readiness and the callback ordering must be
checked before choosing the hook. Reuse the verified existing audio method;
do not add STOP/DELAYED_MEDIA, an arbitrary timer, polling-based audio
restarts, network-rule changes, or a longer RTP timeout without evidence.
Keep W2L CP cleanup/selection and initial MT BT1 behavior intact. Stage a
reproducible, explicitly limited trial and run host/ABI checks before asking
the user to build/flash. The user remains responsible for ROM builds.

Follow-up implementation: see `SA2_STOCK_TELECOM_AUDIO_PORT_20261009.md`.
After the user's request to follow stock, the automatic trial preserves the
stock STOP/reset/mode/SAE/INFORM and reverse CPVE sequence in Telecom itself.
Stock evidence, not the one-shot SAE success alone, justifies the other
stages. It also shows that IMS registration may still report IWLAN at the
stock CPVE request; completed target registration is not a prerequisite
invented by the port. The manual --start-sae experiment must not be combined
with the automatic --handover-check test.
