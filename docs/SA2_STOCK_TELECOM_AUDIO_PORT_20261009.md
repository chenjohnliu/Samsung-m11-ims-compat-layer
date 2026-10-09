# SA2 — stock-derived Telecom audio handover trial

Current source scope, 2026-10-09: carrier-independent SA2 + SEH1 on M11,
single active SIM in slot 0. The user requested removal of carrier
allowlists; both the audio and APN boundary now accept any valid operator
identity. Device/mode/opt-in, ordinary-call and stale-identity guards remain.
Only TWM has runtime evidence; eligibility is not a claim of other carriers'
network provisioning or measured handover quality. See
[complete change and Git audit](CONVERSATION_CHANGE_AND_GIT_AUDIT_20261009.md).

First automatic runtime capture: [07:51:20 findings](SA2_FIRST_AUTOMATIC_CAPTURE_20261009.md).
Both stock audio sequences executed and L2W media processing is present.
The user confirmed the first 188 test passed: approximately 1 s L2W /
0.5 s W2L audible gaps and a successful subsequent VoLTE call. Two-way
conversation, repeated trials and walking out of coverage remain pending.

Follow-up: [13:06 real conversation and icon recovery](SA2_REAL_CALL_WIFI_RECOVERY_20261009.md).
The user confirmed two-way audio through a weak-coverage round trip without
a drop. The temporarily absent VoWiFi icon recovered after Samsung's
existing TEPDG wait; live IMS/ePDG state is healthy. Repeated trials and
instrumented gap measurement remain pending.

## Evidence and implementation basis

The positive 00:48:30 SAE experiment proves that one existing Samsung audio
selection request can restore the recorded failing L2W call. It does not
justify inventing new modem handover signaling or periodic media restarts.
This trial adapts the **stock Telecom control flow**, not just that one-shot
request, to Android 13's existing call/audio-focus events.

Private stock source references inspected:

- `SamsungCallAudioModeStateMachine.setAudioForModeInCommunication`: when
  the current audio mode is IN_CALL and engine control is requested, STOP,
  reset previous audio state/mode, select SEC_WIFI_CALL_ON, set communication
  mode, then startAudioEngineForLte2Wifi.
- `informAudioModeToSamsungEngineIfPossible` and SamsungAudioEngine:
  communication-mode INFORM is direction 7, mapped to DELAYED_MEDIA.
- `enterSimCallFocusState`: when leaving the Wi-Fi audio parameter and
  engine control is requested, wifi2lte selects direction 1 / CPVE before
  resetting the old mode and selecting the CP voice audio parameter.
- `setAudioParametersForVsid` / SamsungCallMultiSimAudioParam: slot-0 SIM
  focus uses `g_call_sim_slot=0x01`; setNone only resets internal bookkeeping.
- `resetAudioMode` / SamsungCallAudioParam: previous call audio OFF parameter
  precedes MODE_NORMAL, followed by the new call audio parameter/mode.

Successful stock log anchors: L2W at 16:00:15.404 starts
SAMSUNG_CHANGE_AUDIO_MODE_WITH_ENGINE, sees foreground IWLAN true, then STOP
at .410, SAE at .647, DELAYED_MEDIA at .651 and SAE initialization at .813.
W2L at 15:58:00.463 changes the **call** RAT 18→14; CPVE is selected at .480.
At .460/.486, IMS registration still reports IWLAN / ePDG true. Therefore
requiring completed LTE registration before CPVE would contradict stock
ordering. Registration is checked for a normal mmtel context on LTE/IWLAN;
the owned foreground call's transport drives engine selection.

| Transition | Scoped stock-derived operations |
| --- | --- |
| Established LTE → IWLAN | STOP(2) → g_call_state=1 → MODE_NORMAL → g_call_state=32 → MODE_IN_COMMUNICATION → SAE(0) → INFORM(7) |
| Same call IWLAN → LTE | g_call_sim_slot=0x01 → CPVE(1) → g_call_state=16 → MODE_NORMAL → g_call_state=2 → MODE_IN_CALL |
| Audio focus ends after an SA2 write | Corresponding g_call_state OFF → existing Telecom MODE_NORMAL |

This is a narrow, project-authored compatibility adapter, **not a wholesale
port of proprietary Samsung Telecom**. The Android audio-focus owner remains
Telecom, as in stock; IMS bridge/modem/ePDG/APN/MTU/timeouts are unchanged.

## Scope and gates

Default OFF. Requires `persist.sys.m11_ims_audio_port=stock1`, m11q, legacy
IWLAN, any valid slot-0 MCC/MNC and no second operator. Telecom additionally requires
one foreground ACTIVE ordinary audio-only call from the com.android.phone
slot-0 phone account, excluding emergency, conference, child, external,
self-managed and explicitly VoIP calls. Its LTE call-network extra must
have been observed before the trial can treat Wi-Fi as a transition.

The Call listener observes actual connection properties/extras; it does
not listen for Wi-Fi broadcasts or use registration alone as a handover
trigger. Android's existing foreground-mode-change event selects the
existing SIM/VOIP focus states. Initial IWLAN calls retain their previous
path, including existing MT/BT1 behavior. This first automatic trial starts
with an established LTE call and then tests both directions on that call.

Before writing, the adapter loads the installed imsmanager typed proxy and
checks the secims descriptor, normal non-emergency/non-CMC mmtel registration
and exact Samsung call counts [1,0,0,0] on slot 0 / [0,0,0,0] on slot 1.
RAT 13 or 18 is allowed for the normal registration during transition;
PDN 11 is never confused with RAT. Counts are rechecked before every native
audio selection. No guessed transaction ID or permission bypass is added.

Per-call identity/transport generations invalidate stale work on ownership
loss, termination, ineligibility or reversal. Duplicate property updates
do not retry an attempted generation. Operations check current ownership
before each step. No policy monitor/global Telecom lock is held across the
new Binder/audio operations. A live call spanning independent processes
cannot be made atomic by these checks; rapid toggles/hold/multiple-call
cases are deliberately outside acceptance for this trial.

Failures log `SA2 aborted at ...; no automatic retry`; subsequent operations
in that sequence stop. Telecom retains its normal mode-setting fallback.
Only parameters actually written by SA2 are cleaned at unfocused entry.
This does not guarantee recovery from a partial failed sequence: end that
test call normally and inspect logs rather than adding automatic retries.

## Source delivery and validation

Applied to `/home/user/android/crdroid/packages/services/Telecomm`:

- CallAudioManager.java — scoped call observer and audio adapter hooks;
- CallAudioModeStateMachine.java — existing focus-state entry/cleanup hooks;
- SamsungImsAudioHandover.java — typed stock audio adapter and fail-closed gates;
- SamsungImsAudioTransition.java — per-call transition policy and stock order.

Exact original two-file backup and applied hash manifest:
`D:/m11q/work/sa2-telecom-audio-port-20261009/active-source-backup`.
Prepared review snapshot:
`D:/m11q/work/sa2-telecom-audio-port-20261009/candidate-stock-order`.
The patcher rejects baseline drift, existing helpers and duplicate anchors.
Restore refuses subsequent edits and validates original backup hashes.

Validated: standalone JDK11 compilation of all four changed/new classes
against existing Android13 framework, libart, annotations and Telecom jars;
34 host transition/ownership/registration/stock-order assertions; six
isolated prepare/apply/verify/restore tests; collector syntax/mock tests;
live WSL source hash gate and git diff whitespace check. No Android ROM
build, APK install, flash, or phone experiment was performed by the agent.
Full Android packaging/R8 and runtime Binder/audio behavior remain to be
verified by the user's build and experiment.

## User build and experiment

1. Build the ROM using the normal workflow. This change requires **Telecom
   to be rebuilt and included**, not just reusing the prior IMS APK.
2. Before flashing, run from the repository in WSL:

   ```sh
   python3 tools/sa2_telecom_audio_trial.py verify-product \
     --product-root /home/user/android/crdroid/out/target/product/m11q
   ```

   This checks SA2 code markers, including the new carrier-neutral revision,
   in the built Telecom APK and reports its
   SHA256; it is not a full ROM/runtime acceptance gate. Keep the previous
   SEH1/LG3 product checks as well. Flash only after the relevant checks pass.
3. With no ongoing call, enable the gated trial in Termux:

   ```sh
   su -c 'setprop persist.sys.m11_ims_audio_port stock1'
   ```

4. Replace the phone Download copy of
   `D:/m11q/tools/capture_ims_media_probe_termux.sh` (stock-audio-port-v6).
   Connect a normal LTE 188 call, then:

   ```sh
   bash /sdcard/Download/capture_ims_media_probe_termux.sh --handover-check
   ```

   **Do not use --start-sae**: that manual intervention would confound the
   automatic port test. The handover-check mode makes no audio requests and
   does not change the trial gate or Wi-Fi state. No helper JAR is needed.
5. Enable Wi-Fi. Press Enter when the original call switches to VoWiFi,
   even if audio is normal. Keep the same call on VoWiFi for at least 30 s.
   When the script asks, turn Wi-Fi off and immediately press Enter. Keep
   the original call and let the 40-second observation window finish; if
   it disconnects, press Enter immediately and report where it failed.
   Do not redial, put on hold, add calls or rapidly toggle Wi-Fi.
6. Report both directions' audible gaps and continuity; send the resulting
   PRIVATE_ALL privately as ZIP. After collection, end the test call normally
   and make one ordinary LTE call to check post-call cleanup. Capture any
   subsequent 487/5065 failure separately. Initial 188 testing confirms
   audible downlink, not remote two-way conversational quality; a normal
   person-to-person test is still needed for final acceptance.

Disable with no ongoing call:

```sh
su -c 'setprop persist.sys.m11_ims_audio_port off'
```

The persist property survives reboot until explicitly disabled. Source
rollback, when requested, is available via the verified backup:

```sh
python3 tools/sa2_telecom_audio_trial.py restore \
  --source-root /home/user/android/crdroid/packages/services/Telecomm \
  --backup /mnt/d/m11q/work/sa2-telecom-audio-port-20261009/active-source-backup
```

Rollback restores the two original files and removes only the two unchanged
SA2 project-authored helpers (recoverable from platform/telecom/sa2). It does
not revert an already flashed ROM; the user must rebuild/reflash as needed.

The first automatic same-call 188 L2W/W2L test passed, with user-reported
gaps below 2 s and a successful subsequent VoLTE call. Full acceptance
still requires two-way conversational audio and repeated successful
trials, including walking out of coverage. A log marker, icon,
registration or successful API return alone is not audio-continuity
acceptance; preserve the distinction between trace evidence and the
user's audible observations.
