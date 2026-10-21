# Validated features and current project status

Updated **2026-10-21 (Asia/Taipei)**. The acceptance matrix below records the 2026-10-13 Taiwan Mobile release tests. Jio tester results are recorded separately and do not expand that carrier-specific matrix. Later source revisions and tester reports have the narrower validation scope described here; dated investigation records describe their original builds and experiments.

## 2026-10-21 crDroid SMS-over-IWLAN report

After rebuilding and flashing crDroid with the supplementary bridge-source fix,
the maintainer reported that the requested SMS send/receive tests passed along
with VoLTE and VoWiFi calls. SMS behavior is maintainer-reported; no fresh
successful-send trace was reviewed. A subsequent read-only inspection verified
the tested factory APK identity and hashes. The latest CherishOS release was
built and published on October 21, and its source/ZIP was validated; phone SMS
validation for that release has not been reported. This crDroid result does not establish
Jio SMS or general carrier support. See the [source change, host harness scope
and GSI module guidance](SMS_IWLAN_FIX_20261021.md).

## 2026-10-21 Jio handover tester follow-up

A Jio tester separately confirmed that an ongoing call stayed connected for
both Wi-Fi Calling → LTE and LTE → Wi-Fi Calling handovers. This is a
tester-reported result; the follow-up did not identify the ROM build or APK
hash. Do not associate it with the `20261019-1423` context from the October 20
report. The two reports do not establish Jio SMS, dual-SIM IMS, emergency or
video calling, or long-duration stability. See the dated [Jio case
follow-up](cases/JIO_M115F.md#jio-handover-followup).

## 2026-10-20 Jio tester report

A human-relayed tester report received on October 20 said that VoLTE and VoWiFi both worked on the previously supplied CherishOS `20261019-1423` build containing the `semGetDataServiceState` fix. Record those two results as **PASS (reported)** for that Jio scenario. The tester's installed artifact SHA-256 and fresh crash buffer were not provided, so exact installed-artifact identity and independent log verification remain unverified.

The October 20 report did not specify incoming/outgoing call details, SMS over IMS, reboot behavior, handover behavior, or long-duration stability. The separate October 21 follow-up above now records the two handover directions, but does not supply a build identity. These carrier-specific reports do not change the Taiwan Mobile acceptance matrix below, certify every IMS feature, or establish support for other carriers. See the [Jio M115F case record](cases/JIO_M115F.md).

At the time of the October 20 Jio report, the later preventive API/factory changes had host validation only and were not included in that tester's reported artifact. The October 21 crDroid results above record later ROM call/SMS testing; they do not individually validate every added API path. See the [2026-10-20 IMS API supplement](IMS_API_SUPPLEMENT_20261020.md) for source notes.

## 2026-10-16 source follow-up

Later home-network incoming-call failures led to separate initial Wi-Fi audio
and legacy IWLAN MTU corrections. The maintainer built and flashed both. Incoming
calls passed with two-way audio; a call near the AP also passed handset → speaker
→ handset checks for about 81 seconds. A remote-person outgoing call had normal
two-way speech. A subsequent service-announcement call lasted about 112 seconds,
retained the VoWiFi icon and sampled source MTU 1400, and verified audible
downlink only.

An outgoing-call status icon disappearance that recovered by itself remains
unresolved. The complete VoLTE, both-direction handover and both-slot regression
matrix has not been repeated on this source revision. See the
[patches, application order and evidence limits](CHERISH_VOWIFI_FIXES_20261016.md).

## Tested setup

| Item | Scope |
| --- | --- |
| Device | Samsung Galaxy M11, SM-M115F / m11q |
| Android | Android 13 |
| Accepted ROMs | CherishOS 4.12 Vanilla and crDroid 9.20 |
| Stock IMS inputs | M115FXXS5CWK3 |
| Carrier | Taiwan Mobile |
| SIM use | One active subscription, tested separately in SIM1 and SIM2 |
| Phone validation | Maintainer-run builds, flashing, calls, SMS and handover tests |

The ROM releases contain their own installation instructions:
[CherishOS](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261017-13-Cherish) and
[crDroid](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261018-13-CrDroid).

## Feature scope and validation

| Behavior | CherishOS | crDroid |
| --- | --- | --- |
| IMS registration with one active SIM in either slot | PASS | PASS |
| Outgoing/incoming VoLTE calls | PASS | PASS |
| Outgoing/incoming VoWiFi calls | PASS | PASS |
| Bidirectional speech and normal call teardown | PASS | PASS |
| SMS send/receive and Samsung-to-Android IMS SMS bridge | PASS | PASS |
| Ongoing call moves from Wi-Fi to LTE | PASS | PASS |
| Ongoing call moves from LTE to Wi-Fi | PASS | PASS |
| Weak-Wi-Fi departure preserves the ongoing call | PASS | PASS |
| ViLTE (IMS video calling) | Not supported | Not supported |
| Concurrent dual-SIM/DSDS IMS | Not supported | Not supported |
| Emergency calling over LTE or Wi-Fi | Not validated | Not validated |

The latest CherishOS acceptance followed application of the remaining companion changes and a successful manual ROM build. The maintainer reported successful boot after Format Data, the supported behaviors above, and microG Self-Check. On returning to Wi-Fi coverage, the tested call switched back to VoWiFi after approximately 120 seconds. This is an observed result, not a fixed deadline.

Incoming IMS SMS was also checked through a read-only device trace on 2026-10-13: Android's IMS SMS dispatcher received the segments, the inbound handler assembled the message, and it was saved to the messaging inbox. Private SMS contents and subscriber details are not published.

For crDroid, the [2026-10-10 hotspot handover record](CRDROID_HOTSPOT_HANDOVER_PASS_20261010.md) contains the call timeline and the distinction between log correlation and the maintainer's audio/call-continuity confirmation. The release note records the accepted single-active-SIM tests in both slots.

## Evidence and source records

- **Phone results:** maintainer-reported calls, audio, SMS and handovers, with the incoming IMS SMS trace separately reviewed read-only. Source or host-test success alone is not treated as phone validation.
- **CherishOS integration:** [source checkpoint](CHERISH_SOURCE_CHECKPOINT.md), [IMS supplement](CHERISH_LOCAL_IMS_PATCHES_20261012.md), and [current handoff inventory](../devices/m11q/cherish-android13-handoff.json).
- **crDroid handovers:** [hotspot acceptance record](CRDROID_HOTSPOT_HANDOVER_PASS_20261010.md).
- **Earlier stage records:** useful for the causes and fixes, but not the authority for current feature readiness.

## Remaining limits

- Two active IMS subscriptions / concurrent DSDS IMS are not supported. Success in each physical slot is single-active-SIM support.
- Actual emergency call completion has not been tested. The emergency capability regression test uses simulated masks; it does not call 110, 119 or any emergency number.
- ViLTE (IMS video calling) is not supported. Alternate audio accessories, other firmware/model variants and general carrier compatibility are outside the reported validation scope.
- VoWiFi depends on carrier provisioning and ePDG connectivity. Wi-Fi networks can produce different results; return timing and brief audio interruptions can vary.
- The accepted ROM contains the stock-derived ER1 dependencies. Their use does not separately establish every ERIS/IPsec execution path.

## Runtime success and rebuild status

The latest CherishOS build and stated runtime scope are accepted. The project publishes the source checkpoint, supplemental patches and stock-input provenance.

An independent strict rebuild of the **fresh IMS APK** under the historical producer profile remains open: the fresh candidate's whole-APK/DEX hashes differ from those historical contracts, which were not silently changed. This tooling issue must not be read as the accepted ROM still awaiting call/SMS/handover validation. See the [handoff](CHERISH_ANDROID13_IMS_HANDOFF.md) for the precise artifact boundary.

## Retired development policy

The earlier carrier-specific fresh-bearer/active-call-disconnect workaround is retired. It is preserved in historical records to explain the investigation, and is not the current integration recipe. In the Taiwan Mobile acceptance, handovers preserve the ongoing call and use the modem-led legacy IWLAN path; the separate Jio continuity report is tester-reported and has no identified build. The AP-assisted handover experiment remains disabled.
