# Handover round 1: source changes and device validation

Date: 2026-09-30 (Asia/Taipei). This is an incomplete experimental round toward
the H1-H3 gates in `IMS_HANDOVER_ACCEPTANCE.md`.

2026-10-01 feedback: the initial LTE call failed after leaving an existing
IWLAN registration, despite the disallowed handover policy and successful
normal WWAN IMS setup/registration. Retry also received 487/AAA 5065; airplane
recovery restored calling. Stop mode B until this failed control is resolved.
See `IMS_HANDOVER_ROUND1_20261001_BASELINE_FAILURE.md`. Later installed-jar
verification confirms the round-1 product. A subsequent seven-call cycle run
passed, but did not enter true handover; its third-cycle live log is incomplete.
See `IMS_HANDOVER_ROUND1_20261001_BASELINE_PASS.md`. The earlier 5065 remains
unresolved. The matching private comparison is now complete:
`IMS_5065_PASS_FAIL_COMPARISON_20261001.md`. All seven calls are corroborated;
native cleanup/proxy selection do not discriminate failure. A separate source
repair of crDroid's spoof-sensitive CC debug gate is applied; see
`IMS_CC_DEBUG_BUILD_GATE_20261001.md` for userdebug build/read-only validation.
Mode B is still on hold; the repaired gate is not an IMS continuity fix.

## Source installed in the user's build tree

Repository: `/home/user/android/crdroid/frameworks/opt/telephony`

| File | Change and purpose |
| --- | --- |
| `src/java/com/android/internal/telephony/data/DataNetwork.java` | Attach an individual attempt object to source-start and target-setup callbacks. Reject replies from earlier attempts even while a later HandoverState is active. Clear attempt identity on state exit. On timeout, notify source cancelHandover, mark retry FAILED, and record handover failure. Log attempt ID, source/target transports and CID for correlation. |
| `tests/telephonytests/src/com/android/internal/telephony/data/DataNetworkTest.java` | Add tests for timeout source cancellation/retry termination, a late source-start reply during a new attempt, and a late target-success reply during a new attempt. |

Additional artifact: `D:\m11q\tools\capture_ims_wifi_cycle_termux.sh` now
preserves HH:MM:SS timestamps while redacting full and compressed IPv6. It also
provides a handover manual-capture mode with named snapshots, without the
older fixed-cycle workflow's airplane-recovery step.

No change was made to the device tree's `vendor.xml` handover policy or BU1
timer/resource in this round. Existing edits to PhoneSubInfoController and
ImsPhoneCallTracker were preserved.

## Verification already performed

- The patch applied cleanly to the current crDroid telephony checkout.
- `git diff --check` passed in that checkout.
- Java compiler parser accepted both changed Java files (syntax only).
- Capture script passed `bash -n` and timestamp/IPv6 redaction examples.
- Existing CarrierConfig overlay is unchanged from the device tree HEAD.
- Source review found timeout cancellation follows Samsung AP-assist W2L's
  existing HANDOVER_FAIL path.

Android unit tests have been added but not executed. There was no Android ROM
build, flash, device-setting mutation, or device call performed by the agent.

## Known unverified areas

- These changes do not yet prove carrier 487 / AAA 5065 is fixed under true
  continuity. The stable fresh-WWAN workaround remains the default.
- Samsung TelephonyAdapter/native callbacks are CID-correlated without a
  per-attempt generation. That layer can still confuse late status with a new
  request that reused the CID.
- A stale target-success reply is ignored and logged, not blindly deactivated.
  A reused CID may belong to a good bearer. Orphan cleanup therefore still
  needs ownership evidence from this device test.
- The upstream handover timeout defaults to 300000 ms (5 minutes). Timeout
  handling is automatic, but no shorter timeout was introduced in this round.

## One build/flash, two validation modes

Build the existing crDroid tree with the changed telephony source; flash using
the user's usual procedure. Keep BU1 in the IMS payload. If running Android
unit tests separately is practical, run the DataNetworkTest class, including
the three new tests above, and report its result.

Copy the updated capture script to Termux, start its handover mode, and keep
the capture running across both modes:

```sh
IMS_CAPTURE_MODE=handover bash capture_ims_wifi_cycle_termux.sh
```

Use a second Termux session for the commands below. In the capture session,
enter distinct labels (for example `a_baseline`, `a_w2l1`, `b_w2l1`,
`b_reverse1_failure`, `b_reverse1_recovery`) to take a snapshot after each
step. Include toggle times, call result, and two-way audio in the notes.
Enter `stop` after restoring mode A to produce the shareable archive.

The old script's timestamps were accidentally treated as IPv6; use the new
copy. Do not clear logs between modes.

### A: stable-policy regression control

1. Leave CarrierConfig at its default overlay policy.
2. Confirm LTE and VoWiFi outgoing calls and two-way audio.
3. Finish a VoWiFi call, turn Wi-Fi off, wait for LTE IMS, then dial 188.
   Repeat three times. This checks preservation of the existing 5065
   workaround; a successful fresh-bearer transition does not prove H1.

### B: temporary true-handover trial

Use only the TWM SIM in slot 0 (Android zero-based slot index). These commands
are for root Termux or a root shell. They alter a nonpersistent test override,
not the ROM overlay. If the test SIM is in slot 1, use `-s 1` consistently.

Prerequisite: this Android 13 `cc` implementation requires both root Binder UID
and a non-user runtime Build.TYPE. Root alone is insufficient. The latest phone
capture returned `cc: Permission denied.`; do not run the set/restore commands
below until access is confirmed and mode B is explicitly resumed. A stock
fingerprint containing `user` does not establish runtime build type. The host
product is userdebug; actual phone build type was not captured in that run.

Record the existing policy first:

```sh
su -c 'cmd phone cc get-value -s 0 iwlan_handover_policy_string_array'
```

Temporarily allow the previously blocked IWLAN-to-LTE IMS handover, retaining
the existing catch-all allow policy:

```sh
su -c 'cmd phone cc set-value -s 0 iwlan_handover_policy_string_array "source=GERAN|UTRAN|EUTRAN|NGRAN|IWLAN, target=GERAN|UTRAN|EUTRAN|NGRAN|IWLAN, type=allowed"'
```

Do not use `-p`. Verify the resulting value before testing. Wait for IMS to
stabilize after CarrierConfig changes.

Run this compact first-round batch before attempting the full acceptance run:

1. **Idle W2L and L2W:** three transitions each direction. After each transition,
   place an ordinary call and confirm two-way audio; include 188 after W2L.
   Include one incoming call on each final transport.
2. **Rapid reversal:** toggle back at approximately 1, 3, and 5 seconds after
   the initial toggle, one sequence per interval. Then leave the final state
   stable for 60 seconds and verify a call. Note the toggle times and final
   intended transport.
3. **Active W2L:** make an ordinary VoWiFi call, then turn Wi-Fi off. Record
   whether the call survives with two-way audio, drops, or stays stuck. If
   handover fails, wait for automatic IMS recovery and test a new LTE call.

If a call fails or hangs, capture the immediate state, wait without airplane
mode/reboot/further toggling, and try one later call after IMS recovery. For
an actual missing-callback timeout, allow up to the existing 5-minute timeout
plus recovery time before declaring the timeout path unobserved. Do not
repeat a broken state indefinitely.

Restore the exact policy recorded before mode B. For the current unmodified
TWM overlay it is:

```sh
su -c 'cmd phone cc set-value -s 0 iwlan_handover_policy_string_array "source=IWLAN, target=EUTRAN, type=disallowed, capabilities=IMS" "source=GERAN|UTRAN|EUTRAN|NGRAN|IWLAN, target=GERAN|UTRAN|EUTRAN|NGRAN|IWLAN, type=allowed"'
```

Use the saved value instead if it differs. Do not run `cc clear-values`, which
would also clear other carrier-config test overrides. Reboot also discards
the nonpersistent override, but capture failure evidence before any reboot.

## What to return and what it distinguishes

Return the updated script's SHARE_THIS bundle, notes with toggle times and
call/audio outcomes, and build or unit-test errors if any. Keep full private
captures on the device for targeted analysis if needed.

- Mode A fails: stop the handover trial and investigate the failed control,
  including whether the new lifecycle patch was installed and entered.
  Revert it only when evidence or a controlled comparison supports that
  decision; policy-based fresh setup is no longer a guaranteed 5065 remedy.
- Mode A passes, mode B data/registration succeeds but calls receive 487/5065:
  continuity binding remains unresolved; timeout protection alone did not fix
  carrier call usability.
- A late reply is logged as obsolete: compare its target CID with current
  data-call lists to determine whether target resources are orphaned/reused.
- Timeout calls cancelHandover and fresh normal setup restores registration
  and calling: evidence for H3, subject to rapid-reversal/native cleanup checks.
- Normal and reversed handovers pass: proceed to the complete H1-H3 matrix
  after reviewing this first batch. This compact batch is not the final gate.

Work pauses after this source/static-check round until the user returns the
build/flash/runtime results. Do not continue independent investigation during
that wait.
