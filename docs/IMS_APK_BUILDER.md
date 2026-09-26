# Local clean-stock IMS APK builder and pin promotion

`tools/build_imsservice.py` is the fail-closed outer orchestrator for the M11
IMS APK. It performs no ROM build, no signing, no download and no
device operation.

## Evidence status

The current deterministic output includes Stage 3 BT1, which selects Samsung's
SAE audio interface for an ordinary incoming IWLAN voice call only after the
call reaches ESTABLISHED. Two independent pin-discovery runs produced:

- unsigned APK SHA-256
  `832ad6fca643791a19776be14cb11ad6d1395bfe3d128e058dc4442e703990a9`;
- primary DEX SHA-256
  `cd8be33628bfabeafe77e78c58bf13ba8207e0eba41718845dcf116a8594cfe2`;
- unchanged bridge DEX SHA-256
  `b9d57c1a1aab37fd88a5443bde177c710897b1603481350e8037cf332ce0d325`.

The BT1 behavior was independently runtime-validated in the locally integrated
ROM: the previously silent incoming VoWiFi call no longer disconnected after
about 16 seconds and instead sustained bidirectional audio. The deterministic
public-builder APK above is structure-verified against the same narrowly
specified transformation; its bytes are not claimed to be identical to the
separately packaged and signed ROM input.

The last runtime-tested **Stage 2 BR1 IMS-SMS** unsigned APK identity is
`db2caaa254f017a3f79b0cbb0fd549f97a79fdf8278e7a208412426a77476954`.
The current **Stage 2 SMSC E.164 build candidate** was promoted after two
independent pin-discovery runs produced identical values:

- the pinned Stage 2 unsigned APK SHA-256 is
  `3df8042a57f6359887e68b1e285d68290376801305bc153268c7d512827a75e8`;
- the pinned clean primary DEX SHA-256 is
  `0f5bc4f2cf36af2b43c15c9c9d0f1d445b4e68afe49f6230d329fcee542f8774`;
- the pinned Stage 2 bridge DEX SHA-256 is
  `58142f4656bc867b2325bf7b4ddd3c6b52b2e4012d699ab087cfd824824ebe80`;
- each run passed manifest, native-hook, statistics-guard, class-inventory,
  compile-stub leakage, ZIP-entry preservation and alignment gates.

These current identities are build- and structure-verified only. The earlier
BR1 build is runtime validated for MT IMS acknowledgement and preserved MO
fallback. The new SMSC normalization remains runtime-unverified until the
separately built ROM is manually tested.

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
That historical Stage 1 validation did not by itself validate SIM2 or VoWiFi.
Later Stage 2 testing validated SIM2 as the sole active subscription, and the
Stage 3 BT1 result at the top of this document validates the stated Taiwan
Mobile VoWiFi call scope. Concurrent DSDS, emergency calling, ViLTE and
extended regression behavior remain unverified.

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

## Two-stage invocation

The default mode is strict and never accepts unpromoted pins. When
`final_dex_invariants.pin_state` is `needs-promotion`, first run the explicit
pin-discovery mode. It executes the complete compile, transform, packaging,
alignment and final re-decode checks, but does not gate either DEX or APK bytes
on the stale Stage 1 final pins:

```bash
python3 tools/build_imsservice.py \
  --mode candidate-invariants \
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
  --report out/imsservice-stage2-pin-discovery.json \
  --work-dir /tmp
```

Candidate-invariants mode rejects `--output`. It publishes only an atomic,
privacy-safe report with status `PIN_DISCOVERY`, the observed primary DEX,
bridge DEX and aligned unsigned APK hashes, and explicit false values for
strict-pin verification, artifact publication, release eligibility and runtime
validation. The temporary APK is deleted with the private staging tree.

Run discovery twice into distinct empty report paths and require identical
observed invariants. Review the source and report, then manually update the two
DEX hashes, unsigned APK hash, `pin_state` to `pinned`, and `pin_basis` to
`current-source-build`. The tool never edits its config. Finally run the strict
command below; it independently rebuilds the candidate and publishes the APK
only after every observed value exactly matches the promoted pins.

### Strict build

Run from the repository root. Paths below are placeholders and must point to
regular, non-symlink files on the local machine. The builder uses the published
`bridge/java` tree by default; `--bridge-source-root` remains available for an
explicit hash-matching source tree:

```bash
python3 tools/build_imsservice.py \
  --mode strict \
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
  --output out/imsservice-strict-unsigned.apk \
  --report out/imsservice-strict-report.json \
  --work-dir /tmp
```

Use `--framework-mode golden` for the exact historical framework JAR. The
`compatible` mode still enforces the recorded Binder ABI but reports that the
framework identity is ABI-compatible rather than golden.

The output and report parents must already exist. Existing outputs, symlinks,
input/hash drift, partially applied transformations and undeclared APK changes
all fail closed. Output/report publication occurs only after the full final
re-decode verification succeeds.

A strict report status of `PASS` means only that the pinned deterministic build
and structural checks passed. Its `runtime_validated` and `release_eligible`
fields remain false until separate manual ROM integration and device testing;
the builder never makes a runtime claim.

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
8. In candidate-invariants mode, atomically publishes only the pin-discovery
   report. In strict mode, atomically publishes the unsigned APK and strict
   report. Both modes then delete temporary decoded trees and generated stubs.

The Android ROM build must apply its own platform signature. Never put a
platform private key in this repository or pass one to this tool.
