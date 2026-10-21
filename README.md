# Samsung Galaxy M11 IMS compatibility layer

This project ports Samsung's IMS stack for the Galaxy M11 to Android 13 custom ROMs. It publishes the compatibility source, ROM integration notes, and a small tool to decompile `imsservice.apk` from your own firmware. It does not contain Samsung firmware or a flashable ROM.

[繁體中文](README.zh-TW.md) · [Source and patch index](docs/SOURCE_INDEX.md) · [Documentation guide](docs/README.md) · [Validation details](docs/VALIDATED_FEATURES.md)

## Decompile `imsservice.apk`

The decompiler reads the APK and the matching `framework-res.apk` from the same firmware. It writes decoded files to a new directory; it does not modify the APK, build an APK, or build Android.

### 1. Install the requirements and clone this repository

The commands below use Linux or WSL Bash. Use Python 3, Java from JDK 11 or JDK 17, and apktool 2.9.3. Download the [apktool 2.9.3 release](https://github.com/iBotPeaches/Apktool/releases/tag/v2.9.3) JAR separately. Confirm `python3` and `java` are available in your shell. In WSL, keep the decoded output under your Linux home directory to preserve case-sensitive filenames. Clone the public compatibility repository:

```sh
mkdir -p "$HOME/src" "$HOME/tools" "$HOME/firmware/m115f-cwk3" "$HOME/work"
git clone https://github.com/chenjohnliu/Samsung-m11-ims-compat-layer.git "$HOME/src/Samsung-m11-ims-compat-layer"
```

The two APKs come from your Samsung phone or firmware, not this Git repository. Use both files from the same stock firmware build; the published port targets `M115FXXS5CWK3` (Android 12). The next step explains how to obtain them.

### 2. Set the file paths

The example below stores the two APKs in `~/firmware/m115f-cwk3` and assumes apktool 2.9.3 is in `~/tools`. Change these values if your files are elsewhere. Pick a new output directory for each run.

```sh
export COMPAT_ROOT="$HOME/src/Samsung-m11-ims-compat-layer"
export STOCK_APK="$HOME/firmware/m115f-cwk3/imsservice.apk"
export FRAMEWORK_RES="$HOME/firmware/m115f-cwk3/framework-res.apk"
export APKTOOL="$HOME/tools/apktool_2.9.3.jar"
export DECODED="$HOME/work/imsservice-cwk3-decoded"
```

**Option A — pull from a Samsung phone running stock firmware.** Install [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools), enable USB debugging, connect the phone and accept its debugging prompt. `adb devices` must list it as `device`. Query the APK path instead of assuming which system directory it uses:

```sh
adb devices
adb shell pm path com.sec.imsservice
IMS_APK_PATH="$(adb shell pm path com.sec.imsservice | tr -d '\r' | sed -n 's/^package://p' | head -n 1)"
if [ -n "$IMS_APK_PATH" ]; then
  adb pull "$IMS_APK_PATH" "$STOCK_APK"
  adb pull /system/framework/framework-res.apk "$FRAMEWORK_RES"
else
  echo "IMS package not found. Check the device connection and package name." >&2
fi
```

This copies the phone's **currently installed** IMS APK. A phone running CherishOS or crDroid supplies its modified APK, not the original Samsung input. Use a stock phone or Option B when you need the original firmware files for the port.

**Option B — extract from your stock firmware.** If the phone no longer runs stock firmware, extract the matching firmware's system filesystem. These are paths inside that extracted filesystem:

```text
system/priv-app/imsservice/imsservice.apk
system/framework/framework-res.apk
```

Copy them to `$STOCK_APK` and `$FRAMEWORK_RES`. Samsung's AP archive can contain compressed/sparse or dynamic-partition images; opening the AP archive alone does not necessarily expose the APKs. Image extraction is separate from APK decompilation; the [CWK3 extraction record](docs/FRESH_EXTRACTION_VALIDATION.md) records the layout and hashes used here. Its image extraction helpers are not bundled with this repository.

### 3. Run the decompiler

Run this from the cloned repository. The wrapper uses `java` from `PATH` by default. Its `--java` option is available if Java has a different executable name or location.

```sh
cd "$COMPAT_ROOT"
python3 tools/decompile_imsservice.py \
  --apk "$STOCK_APK" \
  --framework-res "$FRAMEWORK_RES" \
  --apktool "$APKTOOL" \
  --output "$DECODED"
```

The output has this layout:

```text
$DECODED/
├── framework/                 # isolated apktool framework cache
├── decoded/
│   ├── AndroidManifest.xml
│   ├── res/
│   ├── smali/
│   └── smali_classes2/         # present when the APK has another DEX
└── receipt.json
```

Inspect `$DECODED/decoded/AndroidManifest.xml`, `res/`, and `smali/`. Smali is a readable form of compiled Android bytecode, not the original Java source. To find the existing Samsung backend and the related package classes:

```sh
find "$DECODED/decoded" -type f \( -name 'GoogleImsService.smali' -o -name 'GoogleModern*.smali' \)
```

The stock backend is normally at `smali/com/sec/internal/google/GoogleImsService.smali` (or under `smali_classes2/` if it is in a secondary DEX). `GoogleModernImsService` and `GoogleModernMmTelFeature` are added by this project's compatibility patch, so they will not appear in a stock APK decompile. The tool uses an isolated apktool framework cache for the supplied `framework-res.apk` and records its run in `receipt.json`.

Samsung firmware and decoded files remain subject to Samsung's terms. Keep the inputs and output private; do not publish them with this repository.

## Build or apply ROM compatibility changes

Decompiling an APK is separate from building or applying the Android compatibility changes. For CherishOS, start with the [Android 13 source handoff](docs/CHERISH_ANDROID13_IMS_HANDOFF.md) and [source index](docs/SOURCE_INDEX.md). For crDroid, use the [seven-project source recipe](docs/CRDROID_IMS_SOURCE_VERIFIED_20261018.md). Those guides cover source application, private payload preparation, integration and ROM-level validation; neither is a one-command full ROM build.

The latest tested crDroid IMS APK includes the October 21 SMS-over-Wi-Fi change, while the public APK builder still pins the earlier bridge source hashes. The [October 21 follow-up](docs/SMS_IWLAN_FIX_20261021.md) records the change and inspected APK identity. Rebuilding that exact latest IMS payload from clean inputs requires an updated, reviewed producer contract. The October 18 producer recipe is an earlier baseline, not a recipe for the latest APK. The latest CherishOS release was built, published, and source/ZIP validated, but phone SMS validation for that release has not been reported.

## ROM downloads

For installation, use the published [CherishOS release](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261020-13-Cherish) or [crDroid release](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261021-13-CrDroid) and follow its instructions. This repository is not a flashable package.

## Feature support

These results were validated on a Galaxy M11 (`SM-M115F`) with Android 13 and Taiwan Mobile, using **one active SIM at a time**. See [validation details](docs/VALIDATED_FEATURES.md) for the tested builds and evidence. The latest crDroid SMS result is maintainer-reported; SMS phone validation for the latest CherishOS release has not been reported.

| Feature | CherishOS 4.12 | crDroid 9.20 |
| --- | --- | --- |
| IMS registration with the active SIM in SIM1 or SIM2 | Supported | Supported |
| Outgoing and incoming VoLTE calls | Supported | Supported |
| Outgoing and incoming Wi-Fi Calling (VoWiFi) | Supported | Supported |
| Two-way call audio and normal hang-up | Supported | Supported |
| SMS send and receive | Earlier build validated; latest release not reported | Maintainer-reported on October 21 build |
| Wi-Fi Calling → VoLTE during an ongoing call | Supported | Supported |
| VoLTE → Wi-Fi Calling during an ongoing call | Supported | Supported |
| Leaving weak Wi-Fi coverage without dropping the call | Supported | Supported |
| ViLTE (IMS video calling) | Not supported | Not supported |
| Concurrent dual-SIM/DSDS IMS | Not supported | Not supported |
| Emergency calling over LTE or Wi-Fi | Not validated | Not validated |

SIM1 and SIM2 were tested separately; concurrent dual-SIM IMS is unsupported. Other carriers and models are not runtime-certified. Emergency calls have not been placed, ViLTE is unsupported, and brief audio pauses may occur during handover. See the [Jio case record](docs/cases/JIO_M115F.md) for that separate limited report.

## Project contents

| Directory | Purpose |
| --- | --- |
| `tools/` | APK decompilation, stock-payload transformations and verification |
| `bridge/` | Android/Samsung IMS compatibility code and Android ABI fixtures |
| `platform/`, `patches/` | Android framework, Telephony, Telecom and ROM integration changes |
| `devices/m11q/` | Pinned input hashes, contracts and source/acceptance inventories |
| `tests/` | Source and host checks; these do not replace phone testing |
| `docs/` | Integration guides, technical references and development history |

Use the [documentation guide](docs/README.md) for current entry points. For troubleshooting, see the [IMS debugging runbook](docs/IMS_DEBUGGING.md) and [issue template](docs/ISSUE_TEMPLATE.md).

## Credits and license

- [myesxc/Samsung-s20-ims-compat-layer](https://github.com/myesxc/Samsung-s20-ims-compat-layer): the stock-IMS adaptation and compatibility-layer approach that informed this work.
- **@ifoodplayer**: kernel source and original device/vendor trees.
- **chenjohnliu**: M11 integration, ROM builds and device validation, with ChatGPT/Codex-assisted implementation and analysis.

[Apache-2.0](LICENSE) applies to project-authored material. Samsung-derived inputs remain subject to their own terms; see [NOTICE](NOTICE) and [patch provenance](docs/PATCH_PROVENANCE.md).
