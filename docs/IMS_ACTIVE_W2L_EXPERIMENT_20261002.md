# Active VoWiFi → VoLTE call continuity experiment

2026-10-03 follow-up: the user-tested controller-only candidate below still
dropped the call on Wi-Fi-off. The current implementation and build/test
handoff are [EC2_ACTIVE_W2L_TRIAL.md](EC2_ACTIVE_W2L_TRIAL.md). Treat the hashes
and apply helper below as historical; do not reapply them over the current
EC2 prerequisites. Call continuity is not yet runtime-validated.

Prepared 2026-10-02, Asia/Taipei. The requested outcome is the **same ongoing
ordinary VoWiFi voice call** automatically continuing on VoLTE after gradual
Wi-Fi coverage loss or Wi-Fi-off. Neither fresh registration nor a replacement
call passes. L2W continuity, rapid reversal and generalized recovery are out
of this iteration's scope. Taiwan Mobile (46697) is the first experimental
carrier; other Taiwan profiles remain unchanged, not claimed validated.

Current status (06:49): WSL access recovered. The agent applied the two source
changes with `apply_patch`, verified exact candidate/applied hashes, and ran
the host checks successfully. No ROM build, flash or device test was run.
The next required action is the user's manual build/flash/test, not another
source export or application command.

## Functional candidate

Artifacts: `D:\m11q\work\active_w2l_source_20261001`.

The user exported current `DataNetworkController.java` and device `vendor.xml`.
The candidate adds a device/carrier boolean
`m11q_active_call_w2l_handover_bool`, defaulting off when absent, enabled only
in the m11q 46697 overlay. The existing idle IWLAN→EUTRAN IMS disallow rule
remains in every profile.

In the controller, an exception to that exact IMS-only disallow rule requires:

- a connected IWLAN IMS network, LTE target and no EIMS capability;
- loaded carrier-specific config explicitly opting in for this phone's sub ID;
- actual WWAN PS registration in service and explicit VoPS support;
- an established foreground IMS call with nonempty, audio-only connections;
- no emergency call or ECM on either the base or IMS phone.

This permits the existing `DataNetwork.startHandover` pipeline instead of
`TEAR_DOWN_REASON_HANDOVER_NOT_ALLOWED`. It changes no setup/teardown reason,
retry dispatch, target eligibility check, or call session. Idle, dialing,
held-only, video and emergency cases do not receive the new exception.
Those excluded cases keep their pre-existing policy; this does not claim to
fix emergency or video handover. No emergency calls should be placed for testing.

The earlier attempt/callback patch and CC gate repair are not replaced. The
next manual build should include the current source tree with its existing
changes; do not create a separate CC-only build/flash milestone.

## Why reuse the native handover path

Observed in decoded ePDG: source START_HANDOVER reaches
`EpdgHandler.handleHandoverStart`, then message 1 enters `W2MInProgressState`
without forcing the rejected legacy trigger. LTE target success reaches the
native HANDOVER_SUCCESS path. The unchanged framework target dispatch still
uses HANDOVER and releases the source after target success.

Observed in decoded IMS: `NetworkEventController` marks `EPDG HO : W2L`,
requests registration update, and call-session handling updates the existing
session's access/radio technology. The eight audited class files from the
Sep24 decoded IMS artifact byte-match the BU1 candidate in
`out/bu1-trial/final-decoded2`. This verifies candidate-source freshness, not
today's installed APK independently. Do not enable
`allow_release_wfc_before_ho` or add a speculative TWM SIP re-INVITE.

An unresolved timing risk remains: network-change `tryDisconnect` can reach
`endcallByNwHandover`. A successful AP-assist sequence must be captured to
determine whether this happens before native continuity completes. Do not
blindly suppress all network-loss call termination.

## Non-build validation status

Passed locally on Windows:

- Full source-change envelope: only the three imports, opt-in key, matched-rule
  exception and helper differ from the exported controller baseline.
- Existing dispatch/teardown and enhanced eligibility ordering unchanged.
- XML semantic comparison: only 46697 gets the new opt-in; every existing
  carrier value and handover-rule order remains unchanged.
- Both patches apply cleanly to baseline copies, producing exact candidate
  SHA-256 hashes with LF line endings.
- Bash syntax check for the guarded application script.

Passed in WSL with the source tree's existing JDK17: 34-case host Java helper
truth matrix and full candidate Java syntax parser.
`validate_candidate.py` runs those checks using the actual helper text with
stub APIs. That is not an Android compile or integration test. The user-run
application script requires those host checks to pass **before** source edits.
Actual Android API resolution remains subject to the user's manual build.
The actual Phone/ImsPhone/Call/Connection source API declarations were also
checked. CarrierConfig's real XML reader restores arbitrary matching bundle
keys and merges the vendor bundle, so the new boolean is not a whitelist-only
key. The earlier DataNetwork and TelephonyShellCommand source hashes remain
`bbea62f0c6d03c8a21dfba0d5c2ca6a32657f69620fb61b874b317086af21181`
and `53ba39e969d5729d2ba62277929ace9387cdc7b392e0dbd35feb33e4fcade997`.
Pre-existing dirty source files were preserved.

Candidate hashes:

- Controller: `6b8bf4490598d642be784beb55551c0af5f71c47c213134b2a5504918ae6895b`
- Overlay: `8b21b2d5511586e938da2ca03d0c7e2004384f519edabac6a44519151dfda4dd`

Baseline hashes:

- Controller: `664b88ffd306f3bcc85c3531ec90aca3a4d1f7571c27eabb168067905362520c`
- Overlay: `cf70495f508d27f3df348118144fc6138739ad55c78ebd447e9d6f6987dcf9e4`

## Apply and build boundary

The candidate is now applied to the WSL tree. The following command is an
optional idempotent recheck/reapplication helper, **not a required next step**:

```powershell
wsl -d Ubuntu -- bash /mnt/d/m11q/work/active_w2l_source_20261001/apply_active_w2l.sh
```

It requires `python3`, a JDK, `git`, and `sha256sum`; when `javac` is absent
from PATH it uses the existing crDroid prebuilt JDK17. It runs only
host checks, verifies both source baselines (or already-applied candidates),
checks both pending patches, applies only the two named files and verifies
the final hashes. Unrecognized source hashes stop without overwriting files.
It records `host_validation.txt` and `applied_state.txt`. It can resume a
partially applied pair if both files still match their known states.

If checks fail, return their output; do not build or relax the guards. If they
pass, the user may perform the normal manual ROM build, flash and reboot.
Agents do not execute those operations. No device policy override is needed;
the experimental carrier flag is in the built overlay.

Authoritative records now exist at `host_validation.txt` and
`applied_state.txt` under the artifact directory. Both applied file hashes
match the candidates above; targeted `git diff --check` passed in both
repositories. This confirms source application only, not installed behavior.

## One device validation batch

Use a non-emergency ordinary number and reliable LTE coverage. Use the current
`D:\m11q\tools\capture_ims_wifi_cycle_termux.sh` in manual handover mode:

```sh
IMS_CAPTURE_MODE=handover bash capture_ims_wifi_cycle_termux.sh
```

The collector is read-only and continuously records logs. Its phase snapshots
are heavy: take `baseline` before calling; while testing an edge, enter no
snapshot command and do not run TelephonyDebugService dumps. After an edge,
confirm continued two-way audio for at least 30 seconds, end the call normally,
then collect the stable post-call phase and record the observation. Call IDs
and edge ordering must come from continuous native/framework logs, not solely
from post-call snapshots.

1. Establish a VoWiFi call on strong Wi-Fi. While speaking both directions,
   walk away until the phone automatically moves to LTE. Do not toggle Wi-Fi
   for this case. Record audio gaps and whether the original call survives.
2. Restore strong Wi-Fi while idle, establish a new VoWiFi call, then disable
   Wi-Fi once during that call. Check the same continuity and audio criteria.
3. If both pass, repeat each twice more. Do not perform rapid reverse toggles.
   After the last handover, make one ordinary LTE call as a regression check
   for the previously observed 487/5065 problem, not a generalized recovery test.
4. Type `stop` to finalize. Keep the private archive private unless explicitly
   sharing it for investigation; the shared archive is redacted.

Stop the batch after the first dropped/stuck call and retain that capture;
repeating a known failure adds little information. No forced airplane/reset
sequence is required as part of the continuity acceptance test.

Decision paths:

| Evidence | Next implementation action |
| --- | --- |
| No `Active-call W2L` marker while the established call is still on Wi-Fi | Check installed opt-in, real foreground call state and WWAN/VoPS eligibility; do not infer a native handover failure. |
| Marker and HANDOVER target setup, but target fails | Follow the target data-call failure/timeout contract, not NORMAL re-registration. |
| LTE target succeeds, but original call terminates | Correlate ePDG W2L notifications, IMS PDN/UA changes and `tryDisconnect`/`endcallByNwHandover`; fix the demonstrated native ordering gap. |
| Abrupt-off works but walk-out does not start until the call is already lost | Fix qualified-network/weak-signal timing using the measured trigger sequence. |
| Same call survives both edges with continued two-way audio | Repeat and check the known LTE-call regression; active-call success does not validate other carriers or reverse handover. |

The goal remains active and unverified until the requested call continuity is
demonstrated on device. This document is a build/test handoff, not completion.
