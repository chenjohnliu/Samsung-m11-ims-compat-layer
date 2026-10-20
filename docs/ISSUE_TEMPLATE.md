# IMS issue report — Samsung M11 (m11q), Android 13

Use this template for CherishOS, crDroid, or related m11q IMS reports. Keep raw bugreports and unredacted logs private. Attach only small, redacted excerpts needed to support the report. Mark each causal claim **CONFIRMED**, **INFERRED**, or **UNVERIFIED**.

## Summary

- **Short title:**
- **ROM / branch:**
- **Issue type:** IMS crash / registration / VoLTE / VoWiFi or ePDG / SMS over IMS / carrier selection / APN / UI-only / other
- **Evidence status:** CONFIRMED / INFERRED / UNVERIFIED
- **User-visible impact:**
- **First observed (date, time, timezone):**

## Device, SIM, and network

- **Device/codename:** Samsung M11 / m11q
- **Android version:** 13
- **ROM build and source revision:**
- **Installed slot, if known:**
- **Build fingerprint / incremental:** (clues only; these do not prove artifact identity)
- **Baseband / modem version:**
- **SIM count, active slot, selected data SIM:**
- **Carrier, MCC/MNC, roaming state:** (redact subscriber identifiers)
- **Network condition:** cellular / Wi-Fi / Wi-Fi calling / transition; location generalized if relevant
- **APN name and type:** (redact credentials and private endpoints)
- **Known-good comparison:** device/build/SIM/network and result, if available

## Exact artifacts

- **OTA/package filename and SHA-256:**
- **Build/source commit:**
- **Installed framework/APK package names, versions, paths, and hashes:**
- **How installed artifact identity was verified:** pulled/hash matched / installation record only / fingerprint only / unknown
- **Was the issue reproduced on the exact artifact above?** yes / no / unknown

## Reproduction

1. Starting state (boot age, SIM/network state, relevant settings):
2. Exact action(s):
3. Expected result:
4. Actual result:
5. Reproduction rate and number of attempts:
6. Start/end timestamps with timezone:
7. Does it occur on a known-good build or comparison condition? Give the controlled differences:

## Earliest relevant failure and timeline

Include the first relevant fatal per process, relevant events from all captured log buffers, and DropBox evidence when available. Deduplicate repeated copies of the same exception. Preserve timestamps, process/PID, exception type, full method descriptor, and enough surrounding context. Redact identifiers while retaining event ordering.

| Time | Process / PID | Event or exception | Evidence source | Confidence |
| --- | --- | --- | --- | --- |
| | | | logcat / DropBox / dumpsys / tester observation | CONFIRMED / INFERRED / UNVERIFIED |

- **Earliest relevant Java fatal or native fatal:**
- **Was evidence complete from before reproduction through recovery?** yes / no; explain gaps:
- **Likely category:** API linkage / access denial / native / registration or configuration / modem or network / UI-only / unclear
- **Causal interpretation and evidence:**
- **Alternatives still plausible:**
- **ePDG or other later errors:** note their timing and whether causality is established:

## API linkage details (if applicable)

- **Declaring class and method:**
- **Full descriptor/parameter and return types:**
- **Static or instance invocation; receiver type:**
- **Caller package/JAR and exact version/hash:**
- **Provider class and target runtime hierarchy:**
- **Actual target framework/classpath artifact and hash:**
- **Subscription ID or phone ID semantics:**
- **Required permissions/privileges and observed grant/enforcement:**
- **Direct, reflective, JNI, feature-guarded, or other call path:**
- **Reachability established on this device/condition?** yes / no / unknown; evidence:
- **Binder interface involved?** If yes, describe client/service versions and transaction IDs/order:

## Carrier/APN/modem evidence (if applicable)

- **Active subscription and selected carrier ID/config package:**
- **Expected carrier/configuration and evidence for expectation:**
- **Effective carrier configuration observed:**
- **APN/data connectivity state at event time:**
- **Modem/network/ePDG event and exact timestamp/result code:**
- **What would distinguish a framework cause from carrier, APN, modem, or network causes?**

## Changes already made

- **Source revision/diff:**
- **Specific causal evidence supporting the change:**
- **Scope and fallback behavior:**
- **Permissions and subscription semantics reviewed:**
- **Binder transaction IDs/order checked, if relevant:**
- **Non-build validation performed:**
- **Not yet verified:**

## Validation matrix

Use **Pass**, **Fail**, **Not run**, or **Inconclusive**. For each result, identify the installed artifact and provide concise evidence. Add or remove rows to fit the reported feature; do not imply that an untested feature passed.

| Test | Baseline result | Candidate result | Artifact identity verified? | Evidence / notes |
| --- | --- | --- | --- | --- |
| Exact original reproduction sequence | | | yes / no / unknown | |
| IMS process remains stable; no replacement fatal | | | yes / no / unknown | |
| IMS registration and state transition | | | yes / no / unknown | |
| VoLTE call | | | yes / no / unknown / not applicable | |
| SMS over IMS | | | yes / no / unknown / not applicable | |
| VoWiFi / ePDG | | | yes / no / unknown / not applicable | |
| Relevant data, Wi-Fi, or radio transition | | | yes / no / unknown / not applicable | |
| Repeat attempts (count and outcome) | | | yes / no / unknown | |

## Proposed next experiment

- **Uncertainty this experiment resolves:**
- **Single variable being changed:**
- **Expected outcome A and next action:**
- **Expected outcome B and next action:**
- **Evidence to collect in the same test batch:**

## Missing information

List facts needed to reproduce or decide the cause. Do not state assumptions as facts.

- [ ] Exact installed artifact identity and hashes
- [ ] Full first-fatal context for each affected process
- [ ] Complete timeline including logcat buffers and relevant DropBox entries
- [ ] SIM/subscription, carrier selection, and APN context (redacted)
- [ ] Exact caller/provider class and method descriptor
- [ ] Permission and Binder identity evidence
- [ ] Controlled reproduction steps and attempt count
- [ ] Candidate build/device validation results
- [ ] Other:

## Privacy review before sharing

- [ ] Removed IMSI/ICCID, phone number, serial, account identifiers, credentials, and private endpoints
- [ ] Removed unrelated bugreport/log content and local machine paths
- [ ] Kept original evidence private and separate from redacted excerpts
- [ ] Redactions do not hide timestamps, process identity, exception type, descriptor, or relevant ordering
