# 5065 after fresh LTE setup: next diagnostic checkpoint

Date: 2026-10-01, Asia/Taipei. No Android ROM build or phone mutation was
performed in this round. The round-1 installed telephony jar is confirmed.

## Additional source-supported findings

### Why waiting did not recover these calls

Private logcat lines 6959 and 15014 show the governor receiving
`onSipError: service=mmtel error=487 - Request Terminated` for both failures.
The private Reason contains SIP 503 / AAA 5065, but the governor-visible
SipError is 487.

In the final BU1 decoded candidate, `RegistrationGovernorHkTw` extends
`RegistrationGovernorBase` and has no onSipError override. Base's onSipError
(`smali/com/sec/internal/ims/core/RegistrationGovernorBase.smali`:6313)
initiates recovery only for its SIP_INVITE_TIMEOUT / SIP_TIMEOUT constants,
and otherwise returns the received error unchanged. The initial 5065
rejection's cause remains unknown; this explains why this governor path
does not repair the reproduced registered-but-unusable state. Do not turn
all ordinary 487 responses into resets: legitimate call termination would
then cause unrelated IMS disruption.

### A shell IMS toggle is not a validated reset

Android 13 supports `cmd phone ims disable -s 0` / `enable -s 0`. Source
dispatch reaches the bound ImsService enable/disable callbacks. Samsung's
`GoogleModernImsService` overrides neither callback form; framework defaults
are empty. A successful shell return is therefore not proof of native
deregistration, PDN loss or new registration. Do not prescribe this command
as the experiment or infer anything from its lack of effect.

### A narrower native reset exists, but its UI is not in this build

Stock Samsung ImsSettings has a selected-profile Manual deregister/register
operation. It calls `deregisterProfile(..., disconnectPdn=true)` and then
manual register. Source routes this through the native registration manager,
with keepPdn=false, to stopPdnConnectivity and subsequent profile restart.
It is an IMS-UA plus IMS-PDN reset, **not** a UA-only reset. It does not switch
the radio off. Its Eternal variants modify persistent profile enable state
and are not appropriate for this test.

The current host product inventory contains the AOSP Dialer, not ImsSettings
or Samsung Dialer. Device-side manual installs are not known. No secret-code,
raw Binder transaction, force-stop, settings change, or app installation has
been attempted. An inaccessible UI is a missing prerequisite, not evidence
that native IMS-only recovery would fail.

## Corrected capture entry point

The old `dumpsys phone` capture is PhoneGlobals. It does not dump the actual
PhoneFactory/DataNetworkController state. Added:

```sh
dumpsys activity service com.android.phone/.TelephonyDebugService
```

Matching local Android 13 source confirms:

- Telephony's manifest exports this service behind android.permission.DUMP.
- PhoneGlobals.java:479 starts it after creating the default phone during
  normal boot. The collector does not start or reconfigure it.
- TelephonyDebugService delegates to DebugService, then PhoneFactory.dump.
- Phone.java:5040 dumps DataNetworkController.
- DataNetworkController.java:3630 dumps current, pending-teardown, and
  previously connected DataNetworks, including individual network logs.

The corrected collector is `D:\m11q\tools\capture_ims_wifi_cycle_termux.sh`.
It additionally records handover policy layers, build date/incremental,
telephony jar SHA-256, capture mode/slot, and whether the Samsung IMS settings
and dialer packages exist. Full telephony dump remains in the private archive;
only dump-coverage flags and selected non-sensitive policy layers enter the
shared summary. The latest cycle run exposed the root/non-user `cc` gate;
the collector now uses layered `dumpsys carrier_config` output and explicitly
does not label it an effective merged value. See the later pass report below.

Host-only checks passed: bash syntax; timestamp/IPv6 redaction; mocked manual
capture/archive generation; both SIM-slot values; invalid-slot rejection;
diagnostic-service/package present and missing branches. Android commands
were mocked. Device execution is not yet verified.

## One read-only device batch now; no build/reflash/reproduction yet

Avoid another Wi-Fi cycle, airplane reset or reboot before this capture if
practical: it may evict the earlier networks' bounded historical logs.
Use the newly updated collector, not the copy used in the prior capture:

```sh
IMS_CAPTURE_MODE=handover IMS_CAPTURE_SLOT=0 bash capture_ims_wifi_cycle_termux.sh
```

This is the already-identified TWM SIM slot 0. Enter `current_state` at the
snapshot-label prompt, note the current Wi-Fi/call condition (blank is OK),
then enter `stop`. There is no need to place a call or toggle anything. Return
both SHARE_THIS.tar.gz and the matching PRIVATE_FULL_CAPTURE.tar.gz. The
private archive contains identifiers and must not be published.

Expected decision:

- Historical LTE/IWLAN network logs are present: inspect the pre-capture L2W
  request, source disposal, native callback ownership and old/new address
  relation before deciding a source fix or controlled IMS-PDN reset test.
- Diagnostic dump flags are false: fix the device dump-access/service issue
  first; absence is not a clean-state result.
- An IMS settings package exists and its native UI can be safely reached:
  prepare the selected normal TWM profile's manual IMS-PDN reset experiment,
  with no active call and radio retained. Verify PDN loss/recreation rather
  than relying on the icon or menu acknowledgement.
- No effective reset entry exists on the device: prepare a narrowly scoped,
  reviewed diagnostic entry only if the historical logs are insufficient.
  Do not substitute a no-op framework toggle or speculate that full-radio
  resets are required.

Work pauses for this user-owned read-only batch. No new ROM revision is
requested. H1-H3 and the 5065 repair remain incomplete.

## Superseding feedback: latest cycle run passed

The user rebooted and supplied a new seven-call pass run. See
`IMS_HANDOVER_ROUND1_20261001_BASELINE_PASS.md` for identity, five directly
logged established calls, third-cycle timeline coverage gap, and the default
internet bearer difference versus the prior failed run. All new snapshots
confirm actual PhoneFactory/DataNetworkController dump coverage.

The next action is now delivery of that run's existing matching private archive,
not another `current_state` capture, test, build or reboot. The collector also
now records log boundary coverage/redacted stderr and build-type/root identity.
No 5065 recovery or seamless handover fix has been established by this pass.

The matching private archive was subsequently received and compared. See
`IMS_5065_PASS_FAIL_COMPARISON_20261001.md`; all seven calls have system ACTIVE
history, and pass/fail cleanup/proxy selection are materially alike. Archive
delivery is complete. The new actionable source issue is the independent CC
gate defeated by crDroid's global Java Build.TYPE spoof. Its narrow root-only,
real-debug-property repair is applied and statically validated; see
`IMS_CC_DEBUG_BUILD_GATE_20261001.md`. Pause for the user's manual userdebug
build/flash and read-only gate check, not another blind 5065 reproduction.
