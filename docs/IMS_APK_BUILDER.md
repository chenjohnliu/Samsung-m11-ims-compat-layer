# Local clean-stock IMS APK builder

`tools/build_imsservice.py` is the fail-closed outer orchestrator for the M11
Stage 1 IMS APK. It performs no ROM build, no signing, no download and no
device operation.

## Evidence status

Confirmed locally from the exact CWK3 inputs:

- the current runtime-validated Stage 1BQ3 unsigned APK SHA-256 is
  `a9de2549bad19b3aeae3815e689b111384b81cc9dd59944a37e40fe1cda72d67`;
- the clean primary DEX SHA-256 is
  `a16a42ed01d284dc20efa57c67c6f18b6ffb20132367228b7e8a8c90f5eb90c6`;
- the current bridge DEX SHA-256 is
  `5379c0688e2eaa48684d4d3ba7ff2cf570f7f28cca13d6d8934b0ebcad37d031`;
- each run passed manifest, native-hook, statistics-guard, class-inventory,
  compile-stub leakage, ZIP-entry preservation and alignment gates.

The preceding Stage 1BJ APK is runtime validated for SIM1 WWAN registration plus
outgoing and incoming VoLTE under SELinux Enforcing. The incoming test reached
Android ringing, answer, clear bidirectional speech and teardown without an IMS
process restart or VoLTE-indicator loss. Stage 1BK proved that the SIM1 IMS SMS
bridge loaded but failed runtime validation because this Android 13 branch does
not issue a `changeEnabledCapabilities` request for SMS, leaving SMS capability
false. Stage 1BL then successfully exposed SMS capability and reached Samsung's
`ImsSmsImpl`, but Android supplied a null SMSC and Samsung failed before network
transmission. Stage 1BM retains the validated primary DEX, resolves the SMSC
using the framework/SIM/Samsung-profile order used by the S20 compatibility
  design, and forwards retry state before sending. Stage 1BO then reached SIP
  `202 Accepted`, but optional HQM telemetry crashed on a null Android 13 SMS
  role service before the true result could reach Android. Stage 1BP guards only
  that telemetry lookup. It is runtime validated under Enforcing: carrier RP
  cause 50 reached Android as fallback, Android retried through `SEND_SMS`, the
  modem returned success, and the user confirmed delivery without an IMS
  process restart. This validates outgoing SMS fallback, not final pure IMS-SMS
  delivery. Stage 1BQ additionally restores Voice capability from the strict
  normal Samsung `mmtel` registration snapshot when the legacy positive
capability callback is not replayed after SIM hot-swap. Runtime testing showed
that BQ1 alone was insufficient because a late legacy callback could clear
Voice after typed registration. Stage 1BQ2 periodically reconciles that state
only while typed registration and the strict normal cellular `mmtel` snapshot
both remain true. BQ2 runtime testing then proved that the lost gate was
Android's context-local Voice enablement rather than Samsung's native Voice
state. Stage 1BQ3 retains only Android's last explicit enable/disable setting
across an in-process SIM1 feature recreation. Clean-flash BQ3+BQ6 runtime
validation on 2026-09-10 confirmed that SIM removal/reinsertion restores VoLTE
availability and preserves outgoing calls, incoming ringing/answer/two-way
speech/teardown, and SMS send/receive. BQ7 was excluded: the apparent
call-failure regression that motivated it persisted after source rollback but
disappeared after formatting `/data`, so it was not valid evidence for a code
change.
This does not validate
SIM2/DSDS, VoWiFi, emergency
calling, ViLTE or extended regression behavior.

The deterministic build invokes apktool with
`-XX:ActiveProcessorCount=1`. Without that setting, apktool 2.9.3/smali 3.0.3
produced semantically transformed but byte-different primary DEX files between
runs. The exact JVM argument and all executable hashes are hard gates in
`devices/m11q/imsservice-build.json`.

## Required local inputs

All Samsung material remains outside Git:

- exact CWK3 `imsservice.apk`;
- exact CWK3 `framework-res.apk` (required for a private apktool framework
  directory; never rely on the user's global apktool cache);
- exact CWK3 `imsmanager.jar`;
- the seven project-authored bridge Java files included in `bridge/java`;
- an Android 13 `framework-minus-apex.jar`;
- the hash-pinned apktool 2.9.3, JDK 11, R8 and zipalign files.

Use `tools/verify_payload.py` to verify and privately stage stock inputs first.
The command accepts an explicit `--stock-input-dir` for both the source IMS APK
and the apktool framework input.

## Invocation

Run from the repository root. Paths below are placeholders and must point to
regular, non-symlink files on the local machine. The builder uses the published
`bridge/java` tree by default; `--bridge-source-root` remains available for an
explicit hash-matching source tree:

```bash
python3 tools/build_imsservice.py \
  --stock-apk PRIVATE/imsservice.apk \
  --framework-res-apk PRIVATE/framework-res.apk \
  --imsmanager-jar PRIVATE/imsmanager.jar \
  --framework-jar ANDROID_OUT/framework-minus-apex.jar \
  --framework-mode compatible \
  --apktool-jar TOOLS/apktool_2.9.3.jar \
  --java ANDROID_TREE/prebuilts/jdk/jdk11/linux-x86/bin/java \
  --javac ANDROID_TREE/prebuilts/jdk/jdk11/linux-x86/bin/javac \
  --javap ANDROID_TREE/prebuilts/jdk/jdk11/linux-x86/bin/javap \
  --r8-jar ANDROID_TREE/prebuilts/r8/r8.jar \
  --zipalign ANDROID_TREE/prebuilts/sdk/tools/linux/bin/zipalign \
  --output out/imsservice-stage1-unsigned.apk \
  --report out/imsservice-stage1-report.json \
  --work-dir /tmp
```

Use `--framework-mode golden` for the exact historical framework JAR. The
`compatible` mode still enforces the recorded Binder ABI but reports that the
framework identity is ABI-compatible rather than golden.

The output and report parents must already exist. Existing outputs, symlinks,
input/hash drift, partially applied transformations and undeclared APK changes
all fail closed. Output/report publication occurs only after the full final
re-decode verification succeeds.

## What the command does

1. Verifies every private input and tool identity.
2. Creates a disposable private apktool framework cache and decodes stock APK
   and JAR inputs.
3. Applies BC1, BC2, BG1, BH1 and BP1 exactly once in the declared order. BH1
   replaces Samsung's removed Android 12 `IccUtils.getIccType(int)` dependency
   with an APK-local implementation that preserves the stock
   `ril.ICC_TYPE0/1` lookup semantics. BP1 makes only the optional Samsung HQM
   default-SMS-role lookup fail soft so the real acknowledgement can continue.
4. Generates declaration-only compile stubs and verifies Android 13 framework
   ABI compatibility.
5. Compiles only the allowlisted bridge sources and builds the pinned
   `classes2.dex`; generated stubs are excluded.
6. Builds the transformed primary DEX, then imports only the manifest and two
   DEX entries into the stock ZIP while removing the three stale v1 signature
   entries.
7. Aligns, re-decodes and structurally verifies the final candidate.
8. Atomically publishes an unsigned APK and privacy-safe JSON report, then
   deletes temporary decoded trees and generated stubs.

The Android ROM build must apply its own platform signature. Never put a
platform private key in this repository or pass one to this tool.
