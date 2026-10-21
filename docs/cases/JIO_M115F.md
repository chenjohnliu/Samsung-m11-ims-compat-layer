# Jio IMS issue on M115F — tester-reported functional resolution

**Status: RESOLVED — tester-reported VoLTE, VoWiFi, and call continuity in both handover directions.** The October 20 voice/Wi-Fi-calling report and the separate October 21 handover follow-up are recorded below. The handover follow-up has no identified ROM build or artifact hash. These reports are not universal IMS certification or independently log-verified closure. No private bugreport is included.

This case follows the [IMS debugging procedure](../IMS_DEBUGGING.md). The decision table below remains as a reusable guide for interpreting possible results in other cases; it is not a request for this tester to repeat tests or provide more logs.

## Report and baseline

- Device: Samsung Galaxy M11, M115F / m11q.
- ROM: CherishOS 4.12, Android 13 / API 33.
- Carrier: Jio, India; the reviewed original report used SIM slot 0.
- Original symptom: repeated IMS service crashes and a missing VoLTE indicator.
- Original bugreport predates the fix. Its Samsung Android 11 fingerprint is spoofed and does not establish the running framework version.
- The tester report refers contextually to the previously supplied `20261019-1423` build containing the `semGetDataServiceState` fix. The tester's installed artifact SHA-256 was not provided; do not treat the build context as independent proof of installed contents.

## Original diagnosis

The original fatal Java exception identifies this missing method:

```text
java.lang.NoSuchMethodError
Landroid/telephony/TelephonyManager;->semGetDataServiceState(I)I
```

The relevant call chain includes:

```text
TelephonyManagerWrapper.getDataServiceState
PaniGenerator.isValidPani
PaniGenerator.setLkcForLastPani
PaniGenerator.updatePani
network/cell-change handling
```

The report records `RJIL_IN` as the selected carrier profile. While the Samsung components in the port came from Taiwanese stock firmware, this case does not support a Taiwan stock regional-incompatibility diagnosis: the observed selected profile was Jio, and no causal evidence tied the crash to the firmware's region. This finding is specific to the reviewed report and does not establish behavior for other carriers.

After duplicate logcat/DropBox records were reconciled, the reviewed report contained 56 IMS instances of the same missing-method crash and 39 ePDG null-framework crashes. Several ePDG failures followed the IMS fatal by approximately 0.54 seconds. The count describes that retained report and should not be treated as a universal signature.

**Diagnosis confidence — strongly supported:** the captured caller invokes a Samsung API absent from the target framework, and the linkage failure explains the observed IMS crash. The source fix implements the missing API contract using actual subscription data-registration state. The completed OTA's `framework.jar` was checked against the mapped OTA bytes. These observations support the diagnosis; tester-side installed-artifact identity was not independently verified.

**ePDG confidence — inferred:** the later `null IImsFramework` failures may have followed the IMS restart loop. Timing and initialization dependencies make this plausible but do not establish causality. The successful VoWiFi report below confirms functional Wi-Fi calling for the tester's reported conditions; it does not prove that no ePDG null-framework exception occurred.

## Bounded fix and artifact context

The framework fix adds both hidden overloads:

```java
public int semGetDataServiceState();
public int semGetDataServiceState(int subId);
```

The no-argument method delegates using the manager's subscription. The explicit-subscription method reads that subscription's real data registration state through the existing ServiceState backend. A missing ServiceState returns `STATE_OUT_OF_SERVICE`; phone-state permission checks remain in place. It does not return a constant registered state to suppress the crash.

In this source tree, the public one-argument `getServiceStateForSubscriber` wrapper ignores its argument. The fix therefore uses the existing explicit-subscription backend rather than assuming that wrapper honors `subId`. This is a reason to inspect the actual target implementation during a port.

The completed artifact recorded for the fix is:

```text
Cherish-OS-v4.12-20261019-1423-m11q-UNOFFICIAL-Vanilla.zip
SHA-256: 1fbf547c497b8d2af6a60af0e290deca44fdf723f170921f6f3abbfadd7ef3b5
```

The staged framework JAR was verified against the corresponding complete file bytes in the OTA payload using the same build's transfer list and system map. Its DEX defines the two required public overloads. Focused host checks and exact patch replay passed. These checks establish contents of the recorded OTA artifact; they do not independently establish the hash or exact framework installed on the tester's device.

Later preventive API/factory changes from the broader API audit were not included in the tested artifact. They remain host-validated only and are not runtime-tested by this report. Do not attribute this functional result to those later changes.

## Tester result record — 2026-10-20

Source: human-relayed tester report. Accept the functional report as provided; no additional logs are required to record these reported outcomes.

| Check | Result | Confidence / detail |
|---|---|---|
| VoLTE works | **PASS (reported)** | CONFIRMED as a tester-reported functional observation; exact call direction and test detail unreported |
| VoWiFi works | **PASS (reported)** | CONFIRMED as a tester-reported functional observation; conditions and call details unreported |
| Original `NoSuchMethodError` absent in fresh logs | Not reported | UNVERIFIED; no fresh crash buffer provided |
| Installed build SHA-256 | Not provided | UNVERIFIED; `20261019-1423` is contextual build information only |
| Incoming/outgoing call details | Not reported | UNREPORTED |
| SMS over IMS | Not reported | UNREPORTED |
| Reboot, handover, long-duration stability | Not reported in the October 20 report | The October 20 report did not state these results; see the separate October 21 handover follow-up below |
| ePDG null-framework exception absent | Not reported | UNVERIFIED; functional VoWiFi report does not establish this |

<a id="jio-handover-followup"></a>

## Tester follow-up — 2026-10-21 (handover report)

The same Jio tester separately confirmed that an ongoing call stayed connected when handed over in either direction: Wi-Fi Calling to LTE and LTE to Wi-Fi Calling. This is a tester-reported result. The follow-up did not identify the ROM name/version, build date, or artifact hash; do not assign it to the contextual `20261019-1423` build named in the October 20 report.

| Check | Result | Evidence boundary |
|---|---|---|
| Ongoing VoWiFi call hands over to LTE and remains connected | **PASS (reported)** | Human-relayed October 21 tester confirmation; build and artifact identity not provided |
| Ongoing VoLTE call hands over to Wi-Fi and remains connected | **PASS (reported)** | Human-relayed October 21 tester confirmation; build and artifact identity not provided |
| SMS, dual-SIM IMS, emergency/video calling, long-duration stability | Not reported | No result was supplied for these behaviors |

This follow-up does not change the October 20 artifact record and does not establish that the separate reports were run on the same build. It records the two handover outcomes without extending the Jio claim to SMS or other unreported features.

**Closure decision:** resolve the original Jio functional issue as **tester-reported VoLTE and VoWiFi success**, with the separate two-direction handover result recorded above. Retain the missing-API diagnosis as strongly supported by original log/source/artifact evidence. Do not describe the functional reports as independently log-verified, do not claim all IMS features were tested, and do not generalize them to all carriers.

## Reusable decision paths

Use these outcomes to choose the next step when investigating a similar case. They are generic decision paths, not outstanding tests for this resolved report.

| Observed result | Interpretation | Next action |
|---|---|---|
| Original missing-method crash disappears; IMS registers; calls and SMS work | Supports the original diagnosis and functional recovery for the tested scenario | Record artifact identity, duration, steps and feature results; state any untested conditions |
| Same missing-method crash remains | Artifact identity, loaded framework/classpath or access policy still needs verification | Check installed package/framework identity and any hidden-API denial before editing carrier configuration |
| A different first fatal appears | The first blocker may have been removed, exposing another failure | Follow the new earliest stack trace and inspect its exact caller and target symbol |
| No crash, but IMS registration fails | Registration is now the immediate problem | Correlate registration state, carrier selection, PDN/network events and explicit rejection/timeout evidence |
| IMS works, but ePDG fails when Wi-Fi calling is exercised | ePDG needs an independent investigation | Capture the first ePDG failure while IMS is alive; inspect entitlement/provider initialization and network prerequisites |
| Only the VoLTE icon remains absent | Icon state alone is inconclusive | Check actual voice capability, registration and an LTE call before changing UI or telephony behavior |
