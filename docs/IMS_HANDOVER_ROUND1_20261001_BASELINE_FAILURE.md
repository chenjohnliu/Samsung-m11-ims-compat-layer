# Round 1 feedback: registered LTE calls fail after leaving Wi-Fi

Date: 2026-10-01 (Asia/Taipei). This is a failed regression control, not a
successful handover validation. No new ROM source or carrier-policy change
was made in response to this capture.

Latest version confirmation: the user supplied a phone screenshot showing
the installed `telephony-common.jar` SHA-256. Its full 64-character value
matches the checked round-1 product jar exactly. The installed jar contains
the new handover changes; an old telephony jar is no longer the explanation
for this result. Earlier installation-uncertain statements below describe
the evidence available before this screenshot, not the current status.

## Input and trace boundaries

- User report: VoLTE failed at the start of this test.
- Supplied archive: `1-SHARE_THIS.tar.gz`, SHA-256
  `902a8c2f819253ab7ddaf811c26711b5488cced77e92244b4f08d2f431aaed92`.
- Extracted evidence: `D:\m11q\work\ims_handover_round1_regression_20261001`.
- Capture starts at 12:34:58, after an earlier LTE-to-Wi-Fi transition.
- Build display ID/fingerprint do not identify whether the round-1
  DataNetwork changes were built and flashed. Installation is unverified.
- The script was run in the older fixed-cycle workflow, not manual handover
  mode. No mode-B allow-all policy is evidenced in the recorded transition.

## Confirmed observations

Times below are device local time. Line references are to
`key_timeline_redacted.txt`, unless a summary is named.

| Time | Observation | Evidence |
| --- | --- | --- |
| 12:33:08.745 | TWM registered on IWLAN before capture start. The test's initial LTE state was therefore not a clean boot-only LTE control. | `lte_baseline_before_call_summary.txt`:24 |
| 12:35:04.585 | IWLAN-to-EUTRAN IMS transfer matched the disallowed policy; controller selected teardown instead. | timeline:137-146 |
| 12:35:04.595 | Samsung IWLAN provider received `deactivateDataCall`, CID 1, reason 1. | timeline:148-149 |
| 12:35:05.630 | Native IPSec state entered DisconnectedState, before the subsequent LTE IMS setup. A provider acknowledgement alone is not the only teardown evidence here. | timeline:357-363 |
| 12:35:07.790 | WWAN IMS setup used `reason=NORMAL`, `linkProperties=null`, not framework handover setup. | timeline:667 |
| 12:35:07.895 | DN-109-C IMS setup succeeded, CID 2, `rmnet_data1`, IPv4/IPv6 and P-CSCF list. | timeline:694 |
| 12:35:09.186 | TWM registered on LTE, RAT 13, mmtel/smsip. | `lte_baseline_before_call_summary.txt`:28 |
| 12:35:41.440 | First call received 487 Request Terminated with private reason `SIP;cause=503`, `PO: AAA: result_code=0 exp_result_code=5065`. | timeline:967-974 |
| 12:38:44.398 | Retry after the 120-second wait received the same rejection on the same DN-109 bearer. | timeline:1313-1320; `USER_OBSERVATIONS.tsv`:3 |
| 12:39:51.929 | Airplane mode shut down WWAN IMS CID 2; this is a larger reset than normal IMS bearer recreation. | timeline:1513 |
| 12:40:14.053 | New DN-113-C LTE IMS bearer succeeded after radio recovery. | timeline:2151 |
| 12:40:14.927 | New user agent entered REGISTERED on LTE. | timeline:2264 |
| 12:41:06.661 | Recovery call reached ESTABLISHED. User reported connected. | timeline:2503; `USER_OBSERVATIONS.tsv`:4 |

The default internet APN `twm` separately received
`SERVICE_OPTION_NOT_SUBSCRIBED(0x21)` before airplane recovery, then succeeded
after it. This is not an IMS bearer setup failure, and its causal connection
to the call rejection has not been established.

No round-1 `HandoverAttempt`, obsolete callback, `onHandoverResponse`, or
HandoverState log is present in this capture. That does not prove the patch
is absent, nor exclude effects of activity before capture start.

## Conclusions and remaining uncertainty

Confirmed: LTE registration/icon is not sufficient evidence of working IMS
calling. The previously successful fresh-WWAN workaround did not prevent
5065 in this reproduction. Do not describe that workaround as a guaranteed
fix, or proceed to mode B / broad Taiwan rollout based on this result.

Not established: a regression caused by round-1 callback/timeout changes,
the carrier-internal meaning of private code 5065, or whether the remaining
problem is modem/session ownership, access binding, or another carrier state.
The recorded transition bypassed framework handover and completed native
tunnel disconnection before WWAN setup. Adding a speculative teardown delay
or reverting callback guards is not justified by this trace alone.

Read-only review of the round-1 baseline/candidate source confirms the new
attempt is allocated only by `EVENT_NOTIFY_HANDOVER_STARTED` (candidate
`DataNetwork.java`:1374), and the timeout cancellation is confined to
HandoverState (:1499). Normal setup (:2223) and normal teardown (:2594)
remain unchanged. This strongly disfavors these changes as the cause of
the captured disallowed-transfer path. An earlier, uncaptured timeout and
its vendor-side effects cannot be excluded. Also, airplane success does not
establish that a full radio reset is necessary: separate IMS-registration,
WWAN-IMS-PDN, and radio-attach resets have not been compared.

Address fingerprints change after airplane recovery, but they hash a whole
interface line. All raw IPs/P-CSCFs in the shared timeline become the same
redaction token. This cannot establish whether the important IPv6 address or
selected P-CSCF remained the same. Full REGISTER/INVITE/SDP exchanges are
also not retained by the shared timeline filter.

## Next evidence, without another ROM build

1. Confirm whether round-1 DataNetwork source was built and flashed.
2. Prefer examining the already-collected matching private capture rather
   than asking for another reproduction. Needed content: original logcat,
   and `secims.txt`, `connectivity.txt`, `ip_addr.txt`, `phone.txt` at initial
   LTE and post-airplane recovery snapshots. This can compare IMS address,
   selected P-CSCF, registration/contact/security state and call SDP across
   failure and success.
3. `PRIVATE_FULL_CAPTURE.tar.gz` contains phone numbers, IPs and IMS identity
   material; do not publish it. The user may instead supply a consistent
   pseudonymized subset that preserves equality between corresponding
   addresses and SIP identities.

ADB inventory was checked read-only: no device was connected. No phone
setting, call, reboot, build, source rollback, or push was performed.

Stop further source experiments pending this missing evidence. Mode A has
failed; H1-H3 and round-1 installed/runtime status remain unverified.

## 2026-10-01 private bundle and built-versus-installed identity

The user supplied the matching `PRIVATE_FULL_CAPTURE.tar.gz` (SHA-256
`[private archive checksum omitted]`)
and believes the new source was flashed. Private data remains in the local
case directory, outside this repository. Do not copy raw subscriber/SIP/IP
identities into public documentation.

Confirmed on the build host, without running a build:

- Current DataNetwork source SHA-256 still matches the round-1 candidate:
  `bbea62f0c6d03c8a21dfba0d5c2ca6a32657f69620fb61b874b317086af21181`.
- The existing javac output contains `DataNetwork$HandoverAttempt.class`.
- Product `system/framework/telephony-common.jar`, written 2026-09-30 23:17,
  contains the HandoverAttempt descriptor/fields and new diagnostic strings
  in its classes.dex. Thus the product jar is not the old unpatched code.
- Product jar SHA-256:
  `bf08f49f04497a8f3efb51711cce35a11caae9d2bfbae1e34c9388fa80e14504`.
- Existing `crDroidAndroid-13.0-20260930-m11q-v9.20.zip`, written 23:23,
  SHA-256 `c657e123db9c441d6406aa50cee06aaa8a6f0f9a082327785a72a61f33251e06`.
  Its metadata matches current product properties: incremental 1790777382,
  timestamp 1790780995 (2026-09-30 23:09:55 Asia/Taipei). The OTA image's
  embedded jar has not separately been unpacked/hashed.

No new attempt markers or build timestamps are present in the private
capture either. This is not evidence of an old installed jar: the captured
policy-disallowed W2L path does not enter the patched handover path. ADB
inventory is still empty.

Read-only phone check requested, no build/reflash needed:

```sh
sha256sum /system/framework/telephony-common.jar
```

An exact match proves the installed telephony jar is the checked new product
artifact. A different hash only proves a different artifact; it does not by
itself distinguish an old build from another new build. In that case inspect
the installed jar's dex for the new class/methods using ADB before prescribing
a reflash. A changed system file without a subsequent reboot would also need
running-process/boot-image verification; there is no evidence of such a
manual replacement in this report.

## Direct private-capture comparison (identities withheld)

Read-only comparison of the failure and recovery snapshots establishes:

- DN-109's IPv4, non-link-local IPv6 and link-local IPv6 on `rmnet_data1`
  remain unchanged across the initial/failure/wait/retry snapshots.
- After airplane recovery, DN-113 has different addresses in all three
  categories; they remain stable across the recovery call snapshots.
- The four-entry P-CSCF list is identical before and after recovery.
  Samsung governor P-CSCF index is 0 in both epochs, and the XFRM remote
  endpoint matches the same first entry in both. Endpoint selection is not
  the discriminator between these failed and successful calls.
- The failed-call snapshots retain the same XFRM/security-association
  identifiers and configuration. Recovery has new associations and a new
  registered user-agent instance. Do not publish raw keys or identities.
- No plaintext SIP Contact/Security/P-Access-Network-Info headers or SDP
  session/connection/audio lines are present in these captured private
  logcat/secims files. A SIP-header or SDP-address mismatch remains
  unverified, even with this fuller capture.

This narrows the investigation away from a mere P-CSCF failover difference.
Address, security association and user-agent replacement covary with working
calls, but airplane mode changes all of them and radio/network attach state
at once. It does not isolate a faulty component or justify a source fix.
The private analysis also does not identify the installed framework version;
the requested phone jar hash remains the smallest missing version check.

## Phone jar identity confirmed from user screenshot

The phone file-manager screenshot (`3445.jpg`, supplied 2026-10-01) shows:

`bf08f49f04497a8f3efb51711cce35a11caae9d2bfbae1e34c9388fa80e14504`

Joining the three wrapped SHA-256 lines and comparing case-insensitively
produces an exact 64-character match with the host product jar. This confirms
the on-device telephony jar is the new round-1 artifact, not the old jar.
It does not independently verify every other ROM component or loaded ART
boot-image state. The user reports flashing the build; there is no evidence
of a manual live jar replacement. No reflash is indicated just to resolve
the version question.

The VoLTE failure remains unresolved despite the correct installed jar.
Source reachability and the captured disallowed-transfer path still do not
establish that the round-1 handover patch caused the failure. Continue from
the same-P-CSCF / rotated-address-and-security-state findings, not from an
assumed wrong-version hypothesis.
