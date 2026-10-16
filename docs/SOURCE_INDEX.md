# Source forks and patch index

Use this page to locate the source used by the CherishOS Android 13 integration.
The [machine-readable index](../devices/m11q/cherish-source-index.json) lists all
14 checkpointed projects, their locked bases, ordered patches and expected trees.
It also distinguishes the synchronized full-source forks from older donor branches.
This inventory does not cover every project in the Android manifest.

## Latest full-source branches

| Android project | Full source | Equivalent patches |
| --- | --- | --- |
| `frameworks/base` | [Framework: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_frameworks_base/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/frameworks__base/live-source.patch) |
| `frameworks/opt/net/ims` | [IMS framework: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_frameworks_opt_net_ims/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/frameworks__opt__net__ims/live-source.patch), then [capability test](../platform/checkpoints/cherish-20261012-ims-supplement/frameworks__opt__net__ims/emergency-capability-test.patch) |
| `frameworks/opt/telephony` | [Telephony: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_frameworks_opt_telephony/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/frameworks__opt__telephony/live-source.patch), then [legacy IWLAN MTU](../platform/checkpoints/cherish-20261016-vowifi/frameworks__opt__telephony/legacy-iwlan-mtu.patch) |
| `packages/services/Telephony` | [Phone service: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_packages_services_Telephony/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/packages__services__Telephony/live-source.patch) |
| `system/netd` | [netd: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_system_netd/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/system__netd/live-source.patch) |
| `packages/services/Telecomm` | [Telecom: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_packages_services_Telecomm/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/packages__services__Telecomm/live-source.patch), [permission](../platform/checkpoints/cherish-20261012-ims-supplement/packages__services__Telecomm/secims-permission.patch), then [initial Wi-Fi audio](../platform/checkpoints/cherish-20261016-vowifi/packages__services__Telecomm/initial-wifi-audio.patch) |
| `device/samsung/m11q` | [Device: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_device_samsung_m11q/tree/cherish-13-m11q-ims) | Pinned device source, then [Cherish product registration](../platform/checkpoints/cherish-20261012/device__samsung__m11q/live-source.patch) |

The six platform branches start from the exact CherishOS bases recorded in the
checkpoints; the device branch starts from the pinned device source with the
Cherish product registration patch. Their complete Git trees match the patch replay
results; this is stronger than comparing only the files changed in the latest
fix. Exact commits, trees and patch-to-commit mappings are in the index.

For each of these seven projects, choose one source route: the indexed fork
commit already contains its entire listed patch chain. Applying those patches
again would duplicate the integration. Alternatively, use the locked upstream
base and apply its listed patch chain once. The current build checkout was not
switched or modified as part of this organization.

These are complete individual Android projects, not standalone ROM trees.
Their framework APIs, device overlay and other dependencies still come from
the rest of the [CherishOS handoff](CHERISH_ANDROID13_IMS_HANDOFF.md). A matching
source tree does not expand the [device validation scope](VALIDATED_FEATURES.md).

## Other projects and the patch route

| Project | Published source recipe |
| --- | --- |
| `packages/services/Mms` | [Combined baseline](../platform/checkpoints/cherish-20261012/packages__services__Mms/live-source.patch); the later supplement copy is reference-only |
| `hardware/qcom-caf/msm8953/audio` | Build prerequisite in the [baseline manifest](../platform/checkpoints/cherish-20261012/manifest.json) |
| `hardware/qcom-caf/msm8953/display` | Build prerequisite in the baseline manifest |
| `vendor/qcom/opensource/commonsys-intf/display` | Build prerequisite in the baseline manifest |
| `device/cherish/sepolicy` | Build prerequisite in the baseline manifest |
| `vendor/cherish` | Optional product/OTA customization in the baseline manifest |
| `build/make` | Optional companion OTA customization in the baseline manifest |

The full patch route is the 2026-10-12 combined baseline, the two applicable
patches from its IMS supplement, then the two 2026-10-16 VoWiFi patches. The
index resolves that global sequence into a separate ordered list for each
project. The baseline is not an additional layer on top of the historical
`ims-20261010` patch series.

## Older forks and historical checkpoints

The `m11q-emergency-capability-mask` ref and the `m11q-volte` refs for
`frameworks/opt/telephony`, `packages/services/Telephony` and `system/netd` were
retired on 2026-10-17 and preserved as lightweight tags at their recorded donor
commits. Their archive tags and exact SHAs are listed in the
[branch retirement record](M11Q_BRANCH_RETIREMENT_20261017.md) and the
machine-readable index. The `frameworks/base:m11q-volte` ref remains for its
separate microG and Play Integrity history; the device-tree `m11q-volte` ref
remains the live default and release target; and the Telecom
`m11q-vowifi-audio-path` ref remains for the crDroid replay path.

None of these donor refs identifies the current Cherish integration. In
particular, the old Telecom donor follows a LineageOS-derived base; its changes
were adapted to CherishOS. It must not replace the current Cherish project
wholesale.

The recorded `frameworks/base`, IMS framework, Telephony framework, phone service
and netd donor histories already use CherishOS bases even though their branch
names do not say Cherish. They still require a full-tree comparison before being
treated as the current integration. The uniform branches above make that source
state explicit. For the remaining dependencies, Cherish's locked manifest itself
selects some LineageOS or AOSP projects; their source origin does not turn the
target ROM into crDroid or require a second repository for the same source pin.

The `frameworks/base:m11q-volte` donor also contains microG and Play Integrity
changes outside the IMS checkpoint. This index describes the IMS source recipe;
it does not silently import those separate customizations or claim an exact
snapshot of every file in a previously built ROM.

The Telecom repository was recreated at the same URL as a direct fork of
`CherishOS/android_packages_services_Telecomm`, replacing its earlier crDroid
fork relationship. Its default branch is `cherish-13-m11q-ims`. The current
Cherish integration commit and the historical `m11q-vowifi-audio-path` commit
were restored unchanged; the 29 inherited crDroid branches remain in the
verified local backup rather than being republished. See the
[fork-origin verification record](../devices/m11q/telecomm-fork-origin.json).

The remaining repositories were retained: the five other platform forks
already have CherishOS parents, and the device fork remains based on ifoodplayer.
Checkpoint and APK hash contracts, source commit pins and patch paths stay
stable so the existing integration recipe and historical M11 links continue
to work.

## Keeping the two source routes synchronized

For subsequent changes to any synchronized project:

1. Commit the source change on its Cherish fork branch, with its baseline and
   prerequisite commits retained.
2. Publish the corresponding incremental patch and a new dated checkpoint in
   this repository; retain old checkpoints and their hashes.
3. Update the source index with the fork commit, parent/result tree and patch
   hash. Verify that patch replay and the fork commit produce the same full tree.
4. Publish the fork commit before the index that points to it. Update the scoped
   validation record separately from source synchronization.

The branch names are convenient browsing links. Use the exact commit pins in
the index for reproducibility. Remaining projects use their listed patch recipe
until an explicitly verified full-source fork mapping is added.

Check index coverage, patch hashes, ordering and tree mappings offline:

```sh
python3 tools/verify_cherish_source_index.py
```

To also replay the patches against actual local fork objects, place the seven
clones under a common directory with the names below and the indexed commits
available, then run:

```sh
python3 tools/verify_cherish_source_index.py --forks-root /absolute/path/to/fork-clones
```

| Project | Local clone directory |
| --- | --- |
| `frameworks/base` | `frameworks_base/` |
| `frameworks/opt/net/ims` | `net_ims/` |
| `frameworks/opt/telephony` | `telephony/` |
| `packages/services/Telephony` | `phone_service/` |
| `system/netd` | `netd/` |
| `packages/services/Telecomm` | `telecomm/` |
| `device/samsung/m11q` | `device/` |

The local verification uses temporary indexes and preserves checkout refs,
source files and the real indexes. It does not check GitHub availability or
establish that the current branch head still equals the recorded pin.
