# Local clean-stock IMS APK builder

`tools/build_imsservice.py` is the fail-closed outer orchestrator for the M11
Stage 1 IMS APK. It performs no ROM build, no signing, no download and no
device operation.

## Evidence status

Confirmed locally from the exact CWK3 inputs:

- the current unsigned APK SHA-256 is
  `453d228f77441e4e0df4b1d45ac055740f70ce1aa295c80d8c8d1a2e058ada87`;
- the clean primary DEX SHA-256 is
  `ab5b0fa1e3f244660d0ea6b287856409065381c78f9a682c4d03be5a15c8353c`;
- the current bridge DEX SHA-256 is
  `c47750fb400ed9a4dca45490c9f4f5937bf99fa2d9e47b167866f46b7025a738`;
- each run passed manifest, native-hook, statistics-guard, class-inventory,
  compile-stub leakage, ZIP-entry preservation and alignment gates.

The current Stage 1BJ APK is runtime validated for SIM1 WWAN registration plus
outgoing and incoming VoLTE under SELinux Enforcing. The incoming test reached
Android ringing, answer, clear bidirectional speech and teardown without an IMS
process restart or VoLTE-indicator loss. This does not validate SIM2/DSDS, IMS
SMS, VoWiFi, emergency calling, ViLTE or extended regression behavior.

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
- the six reviewed bridge Java files while their final licence record remains
  pending;
- an Android 13 `framework-minus-apex.jar`;
- the hash-pinned apktool 2.9.3, JDK 11, R8 and zipalign files.

Use `tools/verify_payload.py` to verify and privately stage stock inputs first.
The command accepts an explicit `--stock-input-dir` for both the source IMS APK
and the apktool framework input.

## Invocation

Run from the repository root. Paths below are placeholders and must point to
regular, non-symlink files on the local machine:

```bash
python3 tools/build_imsservice.py \
  --stock-apk PRIVATE/imsservice.apk \
  --framework-res-apk PRIVATE/framework-res.apk \
  --imsmanager-jar PRIVATE/imsmanager.jar \
  --bridge-source-root PRIVATE/bridge-src \
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
3. Applies BC1, BC2 and BG1 exactly once in the declared order.
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
