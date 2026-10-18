# Validated features and current project status

Updated **2026-10-16 (Asia/Taipei)**. The acceptance matrix below records the 2026-10-13 release tests. Later source revisions have the narrower validation scope described here; dated investigation records describe their original builds and experiments.

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

The earlier carrier-specific fresh-bearer/active-call-disconnect workaround is retired. It is preserved in historical records to explain the investigation, and is not the current integration recipe. The accepted handover behavior preserves the ongoing call and uses the modem-led legacy IWLAN path; the AP-assisted handover experiment remains disabled.
