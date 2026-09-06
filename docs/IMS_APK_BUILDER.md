# Local clean-stock IMS APK builder

`tools/build_imsservice.py` is the fail-closed outer orchestrator for the M11
Stage 1 IMS APK. It performs no ROM build, no signing, no download and no
device operation.

## Evidence status

Confirmed locally from the exact CWK3 inputs:

- two independent runs from new temporary directories produced the identical
  unsigned APK SHA-256
  `8f3e111e9ab93a27a3622c497f3d9e4926f98951b4e29f8af4fbe4579684b2d7`;
- the clean primary DEX was identical in both runs:
  `e2fc4bfa6bbe5c5d85993b11397d6d06eeb7ab4d6b6e8d740f26c1baa758f899`;
- the bridge DEX reproduced the historical runtime identity:
  `fec3ab32d03b929edf432fd810b824108eb02acd781d051c987ca3a1d8ad9c34`;
- each run passed manifest, native-hook, statistics-guard, class-inventory,
  compile-stub leakage, ZIP-entry preservation and alignment gates.

The new APK has **not** been runtime validated. The confirmed phone call used
the historical three-stage candidate. Its primary DEX hash was `f0b64b6f...`;
that remains historical evidence, not the expected clean one-pass output.

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
