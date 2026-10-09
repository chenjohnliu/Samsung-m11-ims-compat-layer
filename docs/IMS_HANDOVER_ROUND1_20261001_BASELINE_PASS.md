# Round-1 stable-policy control: latest cycle run passed

Date: 2026-10-01 (Asia/Taipei). This supersedes the pending-capture next action,
not the earlier confirmed 487/AAA 5065 failure or the unfinished H1-H3 gates.

## Supplied evidence and identity

Shared archive: `C:\Users\user\Downloads\SHARE_THIS.tar.gz`.
SHA-256: `761f3ef435bccf393631a4630a431dacf7e7683775f2ff381725cb84ea675dc4`.
Extracted case: `D:\m11q\work\ims_wifi_cycle_pass_20261001_761f3ef4`.
The matching private archive was subsequently supplied. See
`IMS_5065_PASS_FAIL_COMPARISON_20261001.md`: final Telecom history corroborates
all seven calls, policy layers confirm the stable overlay, and local native
cleanup/proxy selection does not distinguish pass from fail. The earlier
shared-only coverage limitations below remain historical context.

The bundle identifies PLMN 46697, slot 0, capture mode `cycles`, build date
1790780995 and incremental 1790777382. Installed telephony jar SHA-256 is
`bf08f49f04497a8f3efb51711cce35a11caae9d2bfbae1e34c9388fa80e14504`, matching
the round-1 product jar already checked. Both native Samsung IMS settings and
Samsung Dialer package availability flags are false. PhoneFactory and
DataNetworkController dump coverage flags are true in all phase summaries.

## Observed results

- The user recorded seven connected outgoing calls: LTE baseline at 21:52:25,
  cycle 1 Wi-Fi/LTE at 21:53:31/21:54:35, cycle 2 at 21:55:53/21:56:51, and
  cycle 3 at 21:58:45/22:01:12. These are results entered by the user, not
  independent proof of two-way audio or incoming-call usability.
- The covered continuous timeline directly shows five `ESTABLISHED` calls:
  21:51:44.305, 21:53:05.146, 21:54:13.436, 21:55:35.614, 21:56:25.982.
  No actual 487/AAA 5065, Timer F timeout, or fatal exception is seen in this
  covered interval. A numeric SIP debug sequence containing `5065` is not an
  AAA error.
- W2L at 21:51:13.855, 21:53:52.883 and 21:56:03.087 matched the disallowed
  IWLAN-to-EUTRAN IMS rule. New NORMAL WWAN networks connected at
  21:51:17.305, 21:53:56.284 and 21:56:06.576 respectively.
- L2W evaluations at 21:52:38.384, 21:55:13.068 and 21:57:23.770 were rejected
  with `NOT_IN_SERVICE`, followed by teardown and fresh IWLAN networks.
  No round-1 `Begin HandoverAttempt` or target handover response is observed.
- Third-cycle snapshots show Wi-Fi registration at 21:57:36.358, then fresh
  LTE IMS network 113 after network 112 was lost at 21:59:44.708, and LTE
  registration at 21:59:49.143. The two corresponding calls are user-reported;
  their live call events are outside timeline coverage.

Thus this run passes the user-observed stable-policy cycle-call control. It
does not validate seamless transfer, rapid reversal, timeout recovery, or
the new per-attempt callback guards. The previous reproduced failure is now
intermittent/unreproduced in this run, not disproven or fixed.

## Capture limitations and diagnostic changes

The timeline starts at 21:50:01 and ends at 21:58:09.152, before third-cycle
calls and snapshots lasting through 22:01:57. Its start marker is present;
third-cycle snapshot/end markers are absent. The reason for the gap is not
known without the private logger stderr/raw capture.

Every shared policy query returned `cc: Permission denied.` Local Android 13
`TelephonyShellCommand.handleCcCommand` requires root Binder UID AND a
non-user runtime build. The reported root shell and stock Samsung fingerprint
do not establish which prerequisite failed: fingerprint `:user:` is not a
runtime Build.TYPE reading. Host system/build.prop says `ro.build.type=userdebug`;
this bundle does not record the phone's actual build-type property. The
effective W2L disallow rule is demonstrated by DNC decisions, not by the denied
shell query. Do not run mode-B mutations while this gate remains unresolved.

Updated `D:\m11q\tools\capture_ims_wifi_cycle_termux.sh`:

- Uses existing `dumpsys carrier_config` output for the handover key, retaining
  all phone IDs, config-layer headings and the no-SIM section. Explicitly marks
  this as **unmerged**, not an effective merged policy. No CC override is set.
- Records `ro.build.type` and root shell identity for future diagnosis; neither
  alone proves the cached value or Binder identity used by the phone service.
- Adds `capture_health.txt` with observed start/end markers and stderr status,
  redacted logger stderr, and a warning on missing markers. Both markers alone
  do not prove that no intermediate log events were dropped.

Host-only bash syntax, timestamp/IPv6 redaction and mocked capture tests passed,
including slot/layer context, diagnostic/package presence/absence, invalid slot,
and complete/missing-end marker fixtures. Android commands were mocked; the
new collector changes have not been device-tested. No ROM source change,
ROM build, flash, rollback or device setting change was made this round.

## Reduced hypotheses and next action

Default internet network DN-100-C (`twm`) stayed connected in this pass run.
The prior failed run instead repeatedly rejected default data with cause 33
(`SERVICE_OPTION_NOT_SUBSCRIBED`), with rmnet_data0 down. This is a useful
correlation, not proof that internet data caused the IMS rejection. The shared
bundle cannot isolate native bearer/address/security/user-agent state.

Earlier pending action (now completed): ask for the **matching** `PRIVATE_FULL_CAPTURE.tar.gz` from
this run, without another build, reboot, or reproduction. It contains sensitive
IMS identifiers and network/security information; keep it private, not in Git.
Compare DataNetwork history, native bearer cleanup and logger stderr with the
prior failure before selecting a source fix or another controlled test. Continue
to hold true-handover mode B. The private comparison supersedes archive delivery
as the next action; its remaining prerequisite is the read-only device CC gate
check, not a new ROM build or repeated cycle test.
