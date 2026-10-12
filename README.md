# Samsung Galaxy M11 IMS compatibility layer

**Working VoLTE, Wi-Fi Calling and IMS SMS on Android 13 custom ROMs for the Samsung Galaxy M11.**

This project adapts Samsung's stock IMS stack to **CherishOS 4.12** and **crDroid 9.20** on the Galaxy M11 (`SM-M115F`, `m11q`). It publishes the compatibility code, Android source patches, transformation tools and development records used to make that port work.

The port was developed with **ChatGPT/Codex assistance**. The maintainer built and flashed the ROMs, made real calls, checked SMS and tested handovers on the phone. Those results are the basis for the feature status below.

[繁體中文](README.zh-TW.md) · [Documentation guide](docs/README.md) · [Validation details](docs/VALIDATED_FEATURES.md)

## Feature support

Supported functions below were validated on the tested M11/Taiwan Mobile setup, using **one active SIM at a time**. Unsupported functions and functions without actual device validation are listed separately in the same table.

| Feature | CherishOS 4.12 | crDroid 9.20 |
| --- | --- | --- |
| IMS registration with the active SIM in SIM1 or SIM2 | Supported | Supported |
| Outgoing and incoming VoLTE calls | Supported | Supported |
| Outgoing and incoming Wi-Fi Calling (VoWiFi) | Supported | Supported |
| Two-way call audio and normal hang-up | Supported | Supported |
| SMS sending and receiving, including the IMS SMS bridge | Supported | Supported |
| Wi-Fi Calling → VoLTE during an ongoing call | Supported | Supported |
| VoLTE → Wi-Fi Calling during an ongoing call | Supported | Supported |
| Leaving weak Wi-Fi coverage without dropping the call | Supported | Supported |
| ViLTE (IMS video calling) | Not supported | Not supported |
| Concurrent dual-SIM/DSDS IMS | Not supported | Not supported |
| Emergency calling over LTE or Wi-Fi | Not validated | Not validated |

SIM1 and SIM2 were tested separately. This does **not** support two active IMS subscriptions together. On the latest CherishOS test, the ongoing call returned to Wi-Fi Calling about **two minutes** after Wi-Fi coverage returned; that timing can vary.

## Scope and limitations

- Tested hardware: **Samsung Galaxy M11 SM-M115F**; stock inputs: **M115FXXS5CWK3**; target: **Android 13**.
- Runtime results are from **Taiwan Mobile** and the tested Wi-Fi environments. Stock-backed carrier profiles provide wider configuration coverage, but other carriers and models are not runtime-certified.
- **Concurrent dual-SIM/DSDS IMS is unsupported.**
- **Actual emergency calling has not been tested**, including emergency calls over Wi-Fi. The capability regression test does not place a call.
- **ViLTE (IMS video calling) is unsupported.** Other audio accessories are outside the reported validation scope. Brief audio pauses can occur during handover.

See [current validation details](docs/VALIDATED_FEATURES.md) for the evidence and limits. Older failure captures and retired experiments remain in the documentation as development history.

## Where to start

**To use a ROM:** download the [CherishOS](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261012-13-Cherish) or [crDroid](https://github.com/chenjohnliu/android_device_samsung_m11q/releases/tag/20261010-13-CrDroid) release and follow its installation instructions. This repository is not a flashable package.

**To reproduce the CherishOS port:** start with the [Android 13 source handoff](docs/CHERISH_ANDROID13_IMS_HANDOFF.md). It points to the pinned source checkpoint, the two supplemental source patches and the stock-input workflow. Use the combined checkpoint once; do not stack the historical patch series on top of it.

**To understand how it works:** use the [documentation guide](docs/README.md), which separates current integration instructions from component references and historical experiments.

## What is in this repository

| Directory | Purpose |
| --- | --- |
| `bridge/` | Android/Samsung IMS compatibility code and Android ABI fixtures |
| `platform/`, `patches/` | Android framework, Telephony, Telecom and ROM integration changes |
| `tools/` | Stock-payload transformations, source replay and verification |
| `devices/m11q/` | Pinned input hashes, contracts and source/acceptance inventories |
| `tests/` | Source and host tests; these do not replace real phone testing |
| `docs/` | Integration guides, technical references and development history |

You supply the matching stock firmware privately. Samsung APKs, JARs, libraries, decoded code, ROM ZIPs and signing keys are not distributed here.

The working port and an exact artifact rebuild are separate results: the latest CherishOS ROM passed phone validation, while reproducing its fresh IMS APK byte for byte under the historical strict producer contracts remains an open tooling boundary. This is not a one-command port for arbitrary ROMs. Details are in the [source handoff](docs/CHERISH_ANDROID13_IMS_HANDOFF.md).

## Credits and license

- [myesxc/Samsung-s20-ims-compat-layer](https://github.com/myesxc/Samsung-s20-ims-compat-layer): the stock-IMS adaptation and compatibility-layer approach that informed this work.
- **@ifoodplayer**: kernel source and original device/vendor trees.
- **chenjohnliu**: M11 integration, ROM builds and device validation, with ChatGPT/Codex-assisted implementation and analysis.

[Apache-2.0](LICENSE) applies to project-authored material. Samsung-derived inputs remain subject to their own terms; see [NOTICE](NOTICE) and [patch provenance](docs/PATCH_PROVENANCE.md).
