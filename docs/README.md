# Documentation guide

Start with the question you want to answer. You do not need to read the experiment history to understand the project's working features.

## Current entry points

| Question | Read this |
| --- | --- |
| Where are the full source forks and their corresponding patches? | [Source and patch index](SOURCE_INDEX.md) — current Cherish branches, exact commits and all 14 project recipes |
| What works, and on which phone/ROM? | [Validated features](VALIDATED_FEATURES.md) |
| Where can I download a ROM? | [Project README](../README.md#where-to-start) |
| How do I reproduce the CherishOS source integration? | [Android 13 handoff](CHERISH_ANDROID13_IMS_HANDOFF.md) |
| Which source changes belong to that checkpoint? | [Combined source checkpoint](CHERISH_SOURCE_CHECKPOINT.md) |
| What must be applied after the checkpoint? | [IMS supplement](CHERISH_LOCAL_IMS_PATCHES_20261012.md) — two new patches; the MMS copy is reference-only |
| What fixes the later home-Wi-Fi incoming-call failures? | [2026-10-16 VoWiFi supplement](CHERISH_VOWIFI_FIXES_20261016.md) — initial audio and legacy MTU, after the earlier supplement |
| What proves the crDroid handovers worked? | [Hotspot call and handover record](CRDROID_HOTSPOT_HANDOVER_PASS_20261010.md) |
| What may be published? | [Patch provenance](PATCH_PROVENANCE.md), [LICENSE](../LICENSE), [NOTICE](../NOTICE) |

For the CherishOS port, follow the handoff's combined checkpoint, the two earlier supplemental patches, and then the 2026-10-16 VoWiFi supplement **once**. Do not also replay the old platform series, separate SystemUI correction or audio renderer over the combined checkpoint. Exact base revisions and application rules are recorded in the linked guides.

## Component references

These are technical references for a particular part of the port. Their pinned contracts describe build inputs and transformations; they do not expand the phone-validation claims.

| Component | References |
| --- | --- |
| IMS bridge and APK preparation | [APK builder](IMS_APK_BUILDER.md), [bridge provenance](BRIDGE_SOURCE_PROVENANCE.md), [framework ABI](FRAMEWORK_ABI.md) |
| Stock input preparation | [Payload inputs](STAGE3_PAYLOAD_INPUTS.md), [fresh extraction record](FRESH_EXTRACTION_VALIDATION.md) |
| Incoming VoWiFi media | [Stage 3 media fix](STAGE3_MT_VOWIFI_MEDIA.md) |
| Samsung audio integration | [Telecom audio port](SA2_STOCK_TELECOM_AUDIO_PORT_20261009.md) |
| Stock-backed Wi-Fi Calling profiles | [Profile policy](GLOBAL_PROFILE_BACKED_WFC_20261009.md) |
| Single active SIM in either slot | [Slot policy](IMS_SINGLE_SIM_EITHER_SLOT_20261009.md) |
| Stock-derived native dependencies | [ER1 crypto dependencies](ER1_ERIS_PRIVATE_CRYPTO.md) |
| Other Samsung services | [SVE media](SV1_SVESERVICE_MEDIA.md), [ePDG compatibility](EC1_EPDGSERVICE_ANDROID13_COMPAT.md), [UnifiedWFC](UW1_UNIFIEDWFC_SIM_MOBILITY.md) |
| UI companion changes | [VoWiFi icon](SYSTEMUI_IMS_IMPORT_BUILD_FIX_20261010.md), [SIM phone-number display](PHONE_NUMBER_DISPLAY_FIX_20261009.md) |
| Emergency capability and no-dial audit | [Emergency calling audit](EMERGENCY_CALLING_AUDIT.md) |

## Development history

Dated files record investigation states, failures, experiments and source decisions. A statement such as “pending” or “current workaround” in an old capture is not the current project status; use [validated features](VALIDATED_FEATURES.md) first.

- [Original Stage 1 voice baseline](STAGE1_RUNTIME_BASELINE.md) and [Stage 2 handoff](STAGE2_VOWIFI_HANDOFF.md): how registration, voice and SMS were brought up.
- [crDroid restoration](CRDROID_ANDROID13_IMS_RESTORATION.md): cross-ROM source comparisons and earlier audio/handover failures.
- [Broad ROM bring-up notes](M11_ANDROID13_ROM_BRINGUP.md): historical integration snapshots and extraction references, not a replacement for the current CherishOS recipe.
- [Publication workflow notes](PUBLIC_RELEASE_SOP.md): private-input/public-source handling, with historical runtime and payload checkpoints.
- [Integration cleanup](IMS_INTEGRATION_CLEANUP_20261009.md) and [publication/policy cleanup](IMS_PUBLICATION_AND_POLICY_CLEANUP_20261010.md): removal of experimental policy and redundant integration steps.
- Other `EC2`, `BV1`, `LG*`, `SA2` and stage-labelled files remain available for deeper investigation. Their names are development checkpoint labels, not steps every user must follow.

The old carrier-specific workaround that disconnected an active Wi-Fi call is retired. It must not be copied as the current handover policy. Successful handovers and the current scope are documented in the acceptance entry points above.
