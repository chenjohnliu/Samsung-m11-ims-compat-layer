# Independent CherishOS Android 13 IMS handoff — M11

The 2026-10-12 checkpoint contains the source changes used for the user's
fresh CherishOS 4.12 / Android 13 M11 build. On 2026-10-13, after all six
previously omitted changes were applied, the user reported a passing manual build,
boot after Format Data, microG Self Check, SMS send/receive and IMS bridge.
Single-active IMS was validated on SIM1 and SIM2: incoming and outgoing VoLTE
and VoWiFi with two-way audio passed on each slot. WiFi/LTE handover passed;
calls stayed connected when leaving weak WiFi and returned to VoWiFi after
about 120 seconds back on WiFi. The root agent also verified an incoming IMS
SMS trace read-only.

See [validated features](VALIDATED_FEATURES.md) for the current acceptance
matrix, tested setup and remaining limits.

Start with [the target source checkpoint](CHERISH_SOURCE_CHECKPOINT.md) and
its [manifest](../platform/checkpoints/cherish-20261012/manifest.json).
The [machine-readable handoff](../devices/m11q/cherish-android13-handoff.json)
records current readiness, historical artifacts and remaining limits.

After that baseline, apply the
[IMS local-patch supplement](CHERISH_LOCAL_IMS_PATCHES_20261012.md): the Telecom
permission declaration and emergency capability unit-test hunk. The MMS copy
in that inventory is already included in the baseline and must not be applied
again. The 2026-10-13 build and runtime acceptance includes the supplemental
changes.

## Locked source inputs

The [baseline manifest](../platform/checkpoints/cherish-20261012/base-manifest.xml)
locks the 1,200 selected projects to exact revisions, including Jelly and
excluding Calendar. The Cherish manifest source was
`CherishOS/android_manifest`, `tiramisu`, commit
`327f31acac15efa57f4c0a759a7079f3955839ad`; per-project locks take precedence
over moving branches. Use this compatibility repository at this publication
commit or later for the combined patches and promoted ER1 contract.

| Device input | Public repository | Locked revision |
| --- | --- | --- |
| M11 device | [android_device_samsung_m11q](https://github.com/chenjohnliu/android_device_samsung_m11q) | `0f1da5855d27841d53743cd878ecd2d09679a941` |
| M11 vendor | [proprietary_vendor_samsung_m11q](https://github.com/chenjohnliu/proprietary_vendor_samsung_m11q) | `6a8923918e90b734913cab84bc8ac7022a2dc143` |
| M11 kernel | [android_kernel_samsung_sdm450](https://github.com/chenjohnliu/android_kernel_samsung_sdm450) | `3936713dfd4d653c2c0cc4852ec412c0b6bd01b3` |
| Samsung hardware | [android_hardware_samsung](https://github.com/LineageOS/android_hardware_samsung) | `65fcb7bb55a35d6751bbe289fcba894fce39becf` |

The source checkpoint adapts each platform project on its own locked Cherish
base; it does not replace entire projects with donor trees. It includes the
framework/Telephony/netd series, corrected SystemUI imports, complete Telecom
hooks and SA2 helpers, MmsService API companion, four build fixes, and product
selection. Optional Jelly/OTA changes are recorded separately by role.

Run the source replay verifier before application. Then apply each manifest
patch to a clean project at its specified base, as described in the checkpoint
guide. Do not stack the historical `ims-20261010` patches, separate SystemUI
patch or SA2 renderer on top of the combined target patches. New Java source
files are included. The historical checkpoint remains available as evidence.

## Private stock inputs and preparation

Use legally owned raw Samsung `M115FXXS5CWK3` stock inputs. The public device
repository does not contain tracked `ims/proprietary` payload. Neither the
device/vendor source repositories nor this compatibility repository distribute
a complete flashable image.

Verify all rows of [payload-manifest.tsv](../devices/m11q/payload-manifest.tsv).
The manifest now includes the raw ARM32 crypto/SSL transform inputs. The
[ER1 contract](ER1_ERIS_PRIVATE_CRYPTO.md) pins the complete stock trio and
generated outputs, with the stock image hash and read-only extraction paths.
The old pair is archival metadata and is not required by the default tool.

The APK producer sequence remains IMS source build → BV1 → LG3 (stock Timer F
128 seconds), and EpdgService EC2 → LG2 with retired AP-assisted trials disabled.
Use UW1 for UnifiedWFC and SV1 for sveservice, plus the public device-tree SVE
native helpers. Do not consume another ROM's source/out directory, patched
APK, saved decoded tree or signing keys. These transformations happen privately;
no Samsung APK/JAR/DEX/SO, firmware or key belongs in Git history.

**Exact APK reproduction remains a separate open boundary.** The fresh IMS
candidate passed source-content, class-round-trip, reference, ZIP preservation
and stock-timer checks, but its primary DEX and whole unsigned APK differ from
the historical strict contracts. Its observed hashes and limited acceptance
are recorded separately; its producer pin profile is not published here.
The historical producer contracts have not been relaxed or silently repinned.
Thus this handoff closes the known source omissions and ER1 input provenance,
but does not claim that every strict historical APK command reproduces this
new candidate from a fresh checkout without a reviewed producer adaptation.

## Build, install and runtime scope

The user performs Android ROM builds, signing, flashing and device tests.
Source replay compares exact result trees; it does not run an Android build.
Product gates for SA2, SEH and global WFC passed on this build, and the ER1
trio and SVE library hashes matched the freshly prepared inputs. The user
reported the build and normal-call results in
[the acceptance record](../devices/m11q/cherish-20261012-user-acceptance.json).

When changing from another ROM, back up internal-storage files before TWRP
Format Data, which erases apps, settings and internal storage. In this run,
Wipe alone left `decryptWithKeystoreKey failed` / `enablefilecrypto_failed`;
Android explicitly rebooted to recovery. Format Data was followed by the
user's successful boot. This was a data-encryption state issue, separate
from the MMS interface compilation fix.

The 2026-10-13 user-reported acceptance covers the build, boot, microG Self
Check, SMS send/receive and IMS bridge, plus per-slot single-active VoLTE and
VoWiFi calls, two-way audio, WiFi/LTE handover and weak-WiFi call continuity
with return to VoWiFi after about 120 seconds on WiFi. An incoming IMS SMS
trace was separately verified read-only by the root agent. ERIS/IPsec execution
and an emergency actual dial remain unverified; dual-active DSDS IMS is outside
the supported single-active-subscription scope. Historical runtime records
remain historical. New captures are private and should be labelled by exact
build, slot, carrier and tested behavior before extending those claims.
