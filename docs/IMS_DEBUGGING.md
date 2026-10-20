# IMS debugging runbook — Samsung M11 (m11q), Android 13

This runbook is intended for maintainers and testers of CherishOS, crDroid, and related Android 13 builds on the Samsung Galaxy M11 (`m11q`). It is carrier-neutral: record the carrier and SIM context for each case, and follow evidence rather than assuming a carrier-specific workaround. The Jio functional issue is resolved at the tester-report level described below, not as universal IMS certification or independently log-verified closure. The companion collector has passed host tests with simulated ADB, but has not been tested on the reporting device.

This is a manual engineering procedure. It can be followed without an AI assistant. Preserve the original logs and artifacts, make one interpretable change at a time, and keep personal diagnostic data private.

## Scope and working rules

Use this runbook for IMS registration, VoLTE, VoWiFi, SMS over IMS, ePDG/IWLAN, IMS crashes, and related carrier-selection or telephony compatibility problems. First identify whether the failure is an app/process crash, a framework/API incompatibility, an access-control failure, a registration/configuration failure, a modem or network failure, or a UI-only symptom. Do not infer the cause from one log line without establishing its process, time, call path, and relation to the observed failure.

Keep these rules throughout the investigation:

- Capture a baseline before changing source or device state. Do not clear logs, reboot, toggle radios, reset network settings, change carrier properties, or perform a clean flash as a diagnostic first step. Those actions can erase evidence or combine several variables.
- Use the first relevant fatal exception or native fatal per process as a starting point, then read the surrounding events from all relevant buffers and DropBox. A later crash may be a consequence of an earlier failure.
- Verify the exact method owner, full descriptor, static/instance shape, permissions, subscription/phone identifier semantics, and the actual target class hierarchy before deciding that an API is missing or mismatched.
- Separate observed facts from inferences and unverified hypotheses. Record alternatives and the experiment that would distinguish them.
- Prefer the narrowest fix that matches the evidence. Preserve Binder transaction IDs and ordering when modifying Binder interfaces. Do not add blanket stubs or catch-and-ignore behavior to make a crash disappear.
- Build manually using the target branch's documented procedure after the source change is ready. Prepare one consolidated build/flash/test batch; diagnostic collection must not trigger a ROM build.

## 1. Establish a reproducible baseline

Record these details in the case report before the test:

- Device model and codename (`m11q`), Android version, ROM name/build, installed slot if known, bootloader/baseband/modem version, and whether the device was upgraded or clean-installed.
- Build artifact identity: filename, size, SHA-256, and source revision/commit. For split packages, record each installed split. Hash the exact OTA/package the tester will flash, not a similarly named copy.
- Device-reported build properties such as fingerprint and incremental version. Treat these as clues only: properties can be overridden and do not prove which artifact is installed.
- SIM count and slot, carrier as displayed by the device, MCC/MNC where available, roaming state, selected data SIM, APN name/type and relevant APN settings, preferred network mode, and whether the symptom occurs on cellular, Wi-Fi calling, or both. Redact phone numbers, IMSI/ICCID, account identifiers, and secret APN credentials.
- Exact symptom, user-visible time, test action, expected behavior, actual behavior, and whether it reproduces. Include timestamps and timezone. Record whether the failure is consistent, intermittent, or only occurs after a specific transition (for example, boot, SIM insertion, data handover, Wi-Fi connection, or a call attempt).
- Recent changes and the comparison baseline: ROM/source revision, framework or IMS APK changes, configuration/overlay changes, modem/firmware changes, and any known-good build on the same device/SIM.

Distinguish the SIM tray label, zero-based slot index, phone ID, subscription ID, and any boot-image slot. They are different identifiers. Record their observed mapping; do not assume `subId == phoneId == slot` or that an identifier stays unchanged after a SIM change.

Use a stable reproduction sequence and include its start/end times. When practical, repeat the same sequence once without modifying the device; do not vary several conditions at once. If a comparison device or build is used, document differences that could affect the result.

## 2. Collect evidence without disturbing the device

Use a current platform-tools `adb` binary. Confirm the selected device before collecting data:

```text
adb devices -l
adb -s SERIAL shell date
adb -s SERIAL shell getprop ro.product.device
adb -s SERIAL shell getprop ro.build.version.release
adb -s SERIAL shell getprop ro.build.fingerprint
adb -s SERIAL shell getprop ro.build.version.incremental
adb -s SERIAL shell getprop gsm.version.baseband
```

Replace `SERIAL` with the device serial. Save the raw output in a private case directory. Device clock and host clock can differ; record both and note the offset. A fingerprint or version string alone is not proof of the installed image.

### Collector option

The companion collector captures common diagnostics without root, log clearing or a device reset. Run this from the directory containing `tools/`. Use a new output directory outside the repository. On Windows, output inherits its parent directory's access permissions; the collector does not set Windows ACLs, so choose a private location:

```text
python tools/collect_ims_debug.py --serial SERIAL --output PRIVATE_DIR
```

Use `--bugreport` only when a fuller diagnostic bundle is needed and the tester has agreed to collect it:

```text
python tools/collect_ims_debug.py --serial SERIAL --output PRIVATE_DIR --bugreport
```

The collector is optional; follow the manual procedure below if it is unavailable or unsuitable. If `adb` is not in PATH, supply `--adb PATH_TO_ADB`. Review `manifest.json` and the command outputs: a zero exit code from ADB does not establish that a service returned useful data, and successful collection does not mean IMS passed a functional test. Some missing packages/services produce empty output or a textual error even when the command exits normally. A bugreport can contain personal and network identifiers. Keep an untouched original and create a separately redacted copy for sharing.

### Manual collection

Capture logs after the reproduction while the relevant buffers remain available. This reads existing buffers and does not clear them:

```text
adb -s SERIAL logcat -b all -v threadtime -d
```

Redirect output to a file on the host, for example `logcat-all.txt`. If a failure is actively reproducing and a live capture is needed, start this before the controlled reproduction and stop it from the host after the sequence:

```text
adb -s SERIAL logcat -b all -v threadtime
```

Collect a bugreport when needed for DropBox entries, package/build context, and system state. Bugreports are large and sensitive; do not upload them to a public issue as-is:

```text
adb -s SERIAL bugreport PRIVATE_DIR/bugreport.zip
```

Capture available service names first because names vary by Android build:

```text
adb -s SERIAL shell dumpsys -l
```

Then collect the relevant services that exist on the device, commonly `telephony.registry`, `phone`, `isub`, and `ims` (the IMS service name is build-dependent):

```text
adb -s SERIAL shell dumpsys telephony.registry
adb -s SERIAL shell dumpsys phone
adb -s SERIAL shell dumpsys isub
```

For an available IMS service, use the exact name shown by `dumpsys -l`. Capture carrier configuration and package state as useful:

```text
adb -s SERIAL shell dumpsys carrier_config
adb -s SERIAL shell pm list packages -f
```

Save full command output and note commands that fail or services that are absent. Do not repeatedly poll dumpsys during a short event if that would alter timing or create excessive output.

### Identify installed packages and framework artifacts

List candidate telephony/IMS packages and resolve the actual installed APK paths:

```text
adb -s SERIAL shell pm list packages -f
adb -s SERIAL shell pm path PACKAGE.NAME
adb -s SERIAL shell dumpsys package PACKAGE.NAME
```

Record package name, version/version code, enabled state, and each path (base and splits). If you need to inspect bytecode, pull the exact installed APKs to the private case directory and hash them there. Where the package path is readable to `adb pull`:

```text
adb -s SERIAL pull DEVICE_APK_PATH PRIVATE_DIR/
```

If the framework artifact is relevant, identify the actual files and build/slot context available on that device or in the flashed package. Do not assume a local source tree, OTA filename, build fingerprint, or a different slot proves the running framework contents. Record hashes for pulled files and for the exact OTA artifact. Hash on a host using its standard SHA-256 utility (for example, `sha256sum FILE` on Linux, `shasum -a 256 FILE` on macOS, or `Get-FileHash -Algorithm SHA256 FILE` in PowerShell).

## 3. Find and classify the earliest relevant failure

Build a short event timeline from the reproduction start through recovery or test end. Search all log buffers and DropBox for the process and package names involved, `FATAL EXCEPTION`, `AndroidRuntime`, `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError`, `SecurityException`, `UnsatisfiedLinkError`, native tombstones, `ImsService`, `ImsManager`, `ImsResolver`, `ImsPhone`, `ePDG`, `IWLAN`, registration, and carrier-config events. Search broadly first, then retain the relevant context before and after each event. Keep timestamps, PID/TID, process name, exception type, complete method descriptors, and causal ordering.

Deduplicate copies of the same crash event across logcat and DropBox using the timestamp, process/PID and stack. Keep distinct restarts or later crash events even when their exception text is identical. Record the earliest relevant fatal per process and keep later fatals in the timeline. “First” means first in the evidence for that reproduction, not the first line in an arbitrary truncated log. If the buffer starts after the failure or timestamps cannot be aligned, mark the event order **UNVERIFIED**.

Classify the observed failure, allowing more than one category when evidence supports it:

| Category | Evidence to establish | Next line of investigation |
| --- | --- | --- |
| Missing or mismatched Java API | `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError`, `IncompatibleClassChangeError`, `NoClassDefFoundError` or `ClassNotFoundException`; exact owner and descriptor; caller APK/JAR; actual runtime provider and hierarchy | Compare the exact runtime caller/provider against the target framework and build artifacts. Check static-vs-instance shape, return type, parameter types, shared-library declarations and duplicate-class packaging. A class-initialization failure can also surface as `NoClassDefFoundError`; inspect the earlier cause. |
| Access denial | `SecurityException`, `IllegalAccessError`, permission/AppOp/role denial, SELinux denial, hidden-API denial, or Binder permission failure | Identify the caller identity, visibility/permission/privilege requirement, enforcement point, and actual package/signature/UID. Check hidden-API logs even if the final exception says a method is missing. Do not weaken checks globally. |
| Native failure | `SIGSEGV`, abort, tombstone, JNI error, or native linkage failure | Match the tombstone to the exact native library, process, build, and ABI. Distinguish a native root failure from later Java service crashes. |
| Registration/configuration failure | Process stays alive but registration is rejected, unavailable, stuck, or never attempted | Follow registration state/reason, carrier configuration, SIM/subscription, APN, network availability, modem and ePDG evidence. Do not infer a framework defect solely from “not registered.” |
| Modem/network/APN issue | Radio/data attach, DNS/IPsec/ePDG, provisioning, or network response evidence points below the IMS app/framework | Compare controlled carrier/SIM/network conditions and capture the corresponding radio/network events. Preserve the exact failure code and time. |
| UI-only symptom | Display or settings state disagrees with service/process/registration evidence, with no corresponding service failure | Trace the UI source and state update. Do not change IMS registration behavior to address a display-only defect. |

These are investigative categories, not conclusions. A symptom can span categories; retain competing explanations until a discriminating experiment resolves them.

## 4. Verify API linkage against the real target

For a suspected API incompatibility, write down the full invocation as observed, including:

1. Declaring class and method name.
2. Full parameter and return types (JVM descriptor where available).
3. Static or instance invocation and the actual receiver type when applicable.
4. Calling method/process and the exact installed caller APK/JAR version and hash.
5. Provider class in the target runtime, its superclass/interface hierarchy, and the exact framework artifact/build/slot being tested.
6. Required permissions, privilege/signature assumptions, Binder caller identity, and whether the API uses a subscription ID or phone ID.
7. Whether the call is direct, reflective, JNI-mediated, behind a feature/availability guard, or in code that is actually reachable on this device and carrier.

Inspect both sides from the exact installed APK and target framework. `jadx` and `baksmali` may help with inspection, but their command-line options vary by version; use the tool's own help and do not rely on an unverified invocation copied into a runbook. For source-based validation, map the API to the target build's actual classpath and implementation, not just a nearby source checkout. Check overlays, generated APIs, hidden-API enforcement, classloader boundaries, and packaged duplicate classes when relevant.

A static direct-member scan is a lead list, not a defect count. A listed reference may be unreachable, guarded, or resolved differently in the application's actual classloader. Reflective targets, JNI/native dependencies, dynamic invocation and type-only instructions need separate checks; they are not proven safe by resolving direct method/field references. Matching symbol names alone do not prove binary compatibility: descriptors and invocation shape must match. Manual triage is required before assigning severity or changing code.

Use the complete runtime boot classpath, including the relevant APEX JARs, and each app's declared shared libraries and transitive dependencies. Public/system SDK stubs are not a substitute for runtime framework JARs. A global union of every JAR can incorrectly resolve a class that the affected app cannot load. Mark an incomplete hierarchy or unknown classpath as **UNVERIFIED**, rather than PASS.

For Binder interfaces, compare the deployed client and service interface definitions and transaction ordering. Preserve existing transaction IDs/order and compatibility expectations. A newly declared method without matching implementation or transaction behavior can move a crash rather than fix it. For optional or carrier-specific paths, prefer a correctly scoped availability check/fallback when that matches the API contract; avoid adding a global fake implementation or returning a misleading success value.

## 5. Separate carrier selection, APN, modem, and framework evidence

Treat carrier selection as a decision to explain, not as proof of the failure's cause. Establish the active subscription and SIM, the selected carrier ID/config package, MCC/MNC and roaming inputs, and the effective carrier configuration at the time of the event. Compare the expected result with the device's observed result and the corresponding source/configuration. An unexpected selected carrier can explain a configuration mismatch, but it does not by itself prove why a process crashed or registration failed.

For this Samsung port, the following read-only properties can help correlate the Samsung MNO selection with the slot and operator context:

```text
adb -s SERIAL shell getprop gsm.sim.operator.numeric
adb -s SERIAL shell getprop gsm.operator.numeric
adb -s SERIAL shell getprop ril.epdg.currenMno
adb -s SERIAL shell getprop sys.smf.mnoname0
adb -s SERIAL shell getprop sys.smf.mnoname1
```

Property names and availability vary by port. An empty value is missing evidence, not proof of a wrong carrier. Distinguish the Samsung MNO/profile selection from Android's carrier ID and CarrierConfig: they are related inputs at different layers. A correct MNO label does not establish that every effective profile, entitlement or modem setting is correct. SIM/home operator and current registered operator can also differ during roaming.

For APN-related claims, record the effective APN type and protocol, the selected data subscription, data connectivity state, and relevant radio/network evidence. Redact credentials and subscriber identifiers. For modem/ePDG claims, correlate the event with the same reproduction and distinguish a modem/network rejection or timeout from a framework exception that happens earlier.

Use the following evidence standards:

- **Confirmed:** directly observed on the affected build/device and tied to the reproduction, with enough artifact identity and context to repeat or independently inspect it.
- **Inferred:** best explanation of the observed facts, but at least one causal link or alternative remains unverified. State what evidence would confirm or disprove it.
- **Unverified:** plausible lead, static scan finding, tester recollection, isolated log fragment, or result lacking artifact/runtime linkage.

Do not upgrade a hypothesis to confirmed because a patch compiles, a source symbol exists, a static scan reports a reference, or the visible symptom changes once.

## 6. Design a useful experiment and decide the next action

Before asking a tester to run anything, state the uncertainty being resolved, the controlled change, the expected observation under each live hypothesis, and the next action for each outcome. Batch compatible read-only captures and repetitions into one test session. Keep the build, SIM, carrier, location/network, APN, and action sequence fixed except for the one variable under test.

Examples of decision-oriented experiments:

| Experiment | Result A and next action | Result B and next action |
| --- | --- | --- |
| Compare the first fatal and registration timeline before and after a narrowly scoped API compatibility change, using otherwise identical build/device/SIM conditions | The specific linkage failure disappears and the expected call proceeds: retain the fix provisionally and continue through registration/call/hand-over validation. | The same failure remains: verify the flashed artifact and runtime class provider; if they match, revisit descriptor/owner/call path rather than layering another stub. |
| Compare effective carrier selection/configuration against the known SIM/MCC/MNC and roaming inputs | Selection is wrong and the relevant effective config differs: trace the mapping/overlay inputs and correct only the responsible selection/config. | Selection and effective config match expectation: move attention to registration, APN, modem/network, or another independently evidenced failure. |
| Compare the same build/SIM reproduction on a controlled known-good network condition or known-good build | Failure follows one network/SIM condition: examine provisioning, APN, carrier config, modem, and network response evidence for that condition. | Failure follows the ROM build across the controlled comparison: prioritize framework/package linkage and configuration differences; verify exact artifacts before editing. |

These examples are not mandatory tests. Select only an experiment that separates the hypotheses actually supported by the case. Do not ask for a clean flash or broad reset unless evidence establishes that the existing installation is too inconsistent to interpret; if required, first preserve the baseline and state what the reset will distinguish.

## 7. Make and validate a narrow source change

Change source when runtime evidence, or a verified call path and target-provider mismatch, sufficiently supports the change. Keep the patch small and correctly scoped to the failing caller, provider, permission path, subscription context, carrier, or optional feature. Document why adjacent cases are unaffected or how they are handled. Do not mask exceptions, return fabricated registration success, weaken permission checks, or add broad placeholder APIs to satisfy a scan.

Before the user builds, perform available non-build checks on the exact diff: inspect the changed method signature/descriptor and invocation shape; inspect class hierarchy and API availability; review permission/subscription semantics; verify Binder transaction stability if Binder code changed; search relevant call sites; inspect generated/overlay counterparts; run repository-prescribed static checks only when they do not invoke a ROM build. Record what was checked and what still needs device validation. Do not claim a build or runtime result that has not happened.

Keep source changes reviewable and commit small, logically related changes after validation. Before sharing publicly, remove private bugreports/logs, subscriber/device identifiers, credentials, local absolute paths, and unrelated worktree content. Public issue text should include redacted evidence and artifact hashes only when safe and useful.

## 8. One consolidated manual build and device validation batch

When a source fix is ready, prepare one batch containing the exact source revision, build targets/artifacts, expected file hashes, flash/install sequence, and all useful test cases. Build manually according to the target branch's instructions. Include enough cases to validate the failure path and important neighboring behavior in the same session, such as IMS process stability, registration, outgoing and incoming VoLTE calls, outgoing and incoming SMS over IMS if applicable, Wi-Fi calling/ePDG if provisioned, and a transition implicated by the original evidence. A successful SMS alone does not establish that it used IMS; record transport evidence if that is the claim being tested. Do not require irrelevant cases.

After flashing, distinguish the staged package from the actually installed/running package:

- Hash and archive the exact OTA and any separately delivered framework/APK artifacts before flashing.
- Record install/flash result, active slot if available, post-boot time, device-reported build identifiers, and installed package versions/paths.
- When practical, pull the installed package/framework artifact and compare its SHA-256 with the intended artifact. If direct access is not available, say so and rely on multiple installation records; do not treat a matching fingerprint alone as proof.
- Repeat the exact baseline sequence, then run relevant adjacent IMS cases while collecting the same logs and state. Preserve timestamps, SIM/network conditions, and result for each case.
- Compare the first relevant failure, state transitions, and user-visible behavior with baseline. A missing crash is useful but not sufficient if the expected IMS behavior still does not occur.

For each test, report pass/fail/not-run with observed evidence. If the new artifact is not verified as installed, classify the result as inconclusive and correct artifact provenance before changing source again.

## 9. Close the case and prepare any port

Record the level of closure. A reporter's confirmation that the affected feature works can close the functional report as **tester-reported resolution**, with the test details and evidence limits stated. Do not convert unreported neighboring tests into passes or demand additional logs merely to accept that report.

For **independently verified runtime closure**, identify the exact tested artifact, reproduce the relevant trigger across repeat runs, observe the expected IMS behavior, check relevant neighboring behavior, and inspect for replacement fatals or permission failures. Record residual limitations and untested carriers/features. For intermittent failures, state the repetition window and the number of successful/failed attempts; one success does not independently establish long-term stability. These stronger evidence requirements do not retroactively change what the tester reported.

Before porting a fix to crDroid or another ROM branch, audit that branch's target APIs, framework implementation, overlays, package versions, Binder interfaces, and permission model. Similar Android version labels do not guarantee matching vendor/framework APIs. Re-run non-build linkage checks against that branch and provide a separate source change/review for the port.

### Case-specific context: Jio investigation (tester-reported functional resolution)

For the maintained worked example and its reusable decision table, see [Jio M115F](cases/JIO_M115F.md). The decision table describes general evidence paths; it is not a pending request for this tester to repeat tests or provide logs. Keep case-specific observations separate from the general procedure.

The original Jio bugreport contained a `NoSuchMethodError` for `TelephonyManager.semGetDataServiceState(I)I` from `PaniGenerator`. The selected profile was `RJIL_IN`; the port's Samsung components originated from Taiwanese stock firmware. The report does not support a Taiwan stock regional-incompatibility diagnosis for this case. Source was updated to read the specified subscription's data registration state through the existing ServiceState backend, returning out-of-service when the state is absent. The completed OTA's `framework.jar` was verified to match the mapped OTA bytes. Together, the captured linkage failure and target-framework mismatch strongly support the missing-API diagnosis for the original crash. They do not establish a cause that applies to all carriers.

On 2026-10-20, a human-relayed tester report said that VoLTE and VoWiFi both work on the previously supplied `20261019-1423` fix build. Record this as **CONFIRMED — tester-reported functional result**: VoLTE PASS (reported); VoWiFi PASS (reported). The exact installed SHA-256 and a fresh crash buffer were not provided, so installation identity and independent log verification remain **UNVERIFIED**. Incoming/outgoing call details, SMS, reboot, handover, and long-duration stability were not reported. These are limitations of the available report; the functional result is accepted without requesting redundant logs.

A later `ePDG` `null IImsFramework` failure occurred roughly 0.54 seconds after an IMS fatal exception in the original report. It remains **INFERRED** as a possible fallout because timing suggests, but does not prove, causality. The tester's successful VoWiFi report confirms functional Wi-Fi calling in the reported test; it does not prove that no ePDG null-framework exception occurred or that the original event was causal. Follow-up APIs identified in source review include `semGetCallState(int)`, `semGetIsimImpu()`, `semGetDataState(int)`, and `getSubscriberIdForUiccAppType` (using the actually selected UICC IMSI and correct permission behavior). `SemCapabilities` has a static factory. These preventive API/factory changes were not included in the tested artifact and remain host-validated only. Existing Binder IDs/order were reported unchanged in that source update; re-check the exact reviewed diff before relying on that statement.

A static direct-member audit covered 8 APK/JAR inputs and an actual classpath with 133,158 reference keys and 245 findings. Those findings require manual triage; they are not 245 confirmed bugs. The scan compares descriptors, invocation shape and hierarchy, but does not establish complete bytecode verification, runtime reachability, reflective/JNI behavior, or hidden-API availability. Guarded optional paths need manual review; do not call a class dead without supporting evidence. Nine missing six-argument SMS calls occur in CDMA/non-3GPP branches; GSM uses the existing five-argument callback. Re-check the exact target branch before generalizing this result. Keep each runtime observation at its own confidence level. See the [case study and result record](cases/JIO_M115F.md).

## 10. Evidence bundle and privacy checklist

Keep a private, timestamped case directory with the original collected files, a short readme containing device/build/reproduction details, artifact hashes, and a timeline. Keep redacted share copies separate from originals. Before attaching anything to a public issue or GitHub discussion, inspect it for:

- IMSI, ICCID, phone number, account name, device serial, Wi-Fi identifiers, precise location, IP addresses, and contact/message content.
- APN usernames/passwords, tokens, URLs or endpoints that are not public, internal network names, and certificate/private-key material.
- Full bugreport sections or unrelated logs that are not needed to reproduce or review the claim.
- Private workspace paths, usernames, local hostnames, and uncommitted source unrelated to the issue.

Share the smallest excerpt that demonstrates the claim, with enough context to preserve the process, timestamps, exception, and relevant state. State any redaction and its effect on interpretation. Do not publish raw bugreports by default.
