# Source forks and patch index

Use this page to locate the source used by the CherishOS Android 13 integration.
The [machine-readable index](../devices/m11q/cherish-source-index.json) lists all
14 checkpointed projects, their locked bases, ordered patches and expected trees.
It also distinguishes the synchronized full-source forks from older donor branches.
This inventory does not cover every project in the Android manifest.

## Latest full-source branches

| Android project | Full source | Equivalent patches |
| --- | --- | --- |
| `frameworks/opt/telephony` | [Telephony: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_frameworks_opt_telephony/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/frameworks__opt__telephony/live-source.patch), then [legacy IWLAN MTU](../platform/checkpoints/cherish-20261016-vowifi/frameworks__opt__telephony/legacy-iwlan-mtu.patch) |
| `packages/services/Telecomm` | [Telecom: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_packages_services_Telecomm/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/packages__services__Telecomm/live-source.patch), [permission](../platform/checkpoints/cherish-20261012-ims-supplement/packages__services__Telecomm/secims-permission.patch), then [initial Wi-Fi audio](../platform/checkpoints/cherish-20261016-vowifi/packages__services__Telecomm/initial-wifi-audio.patch) |

Both new branches start from the exact CherishOS bases recorded in the
checkpoints. Their complete Git trees match the corresponding patch replay
results; this is stronger than comparing only the files changed in the latest
fix. Exact commits, trees and patch-to-commit mappings are in the index.

For either of these two projects, choose one source route: the indexed fork
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
| `frameworks/base` | [Combined baseline](../platform/checkpoints/cherish-20261012/frameworks__base/live-source.patch) |
| `frameworks/opt/net/ims` | [Combined baseline](../platform/checkpoints/cherish-20261012/frameworks__opt__net__ims/live-source.patch), then [capability test](../platform/checkpoints/cherish-20261012-ims-supplement/frameworks__opt__net__ims/emergency-capability-test.patch) |
| `packages/services/Telephony` | [Combined baseline](../platform/checkpoints/cherish-20261012/packages__services__Telephony/live-source.patch) |
| `system/netd` | [Combined baseline](../platform/checkpoints/cherish-20261012/system__netd/live-source.patch) |
| `packages/services/Mms` | [Combined baseline](../platform/checkpoints/cherish-20261012/packages__services__Mms/live-source.patch); the later supplement copy is reference-only |
| `hardware/qcom-caf/msm8953/audio` | Build prerequisite in the [baseline manifest](../platform/checkpoints/cherish-20261012/manifest.json) |
| `hardware/qcom-caf/msm8953/display` | Build prerequisite in the baseline manifest |
| `vendor/qcom/opensource/commonsys-intf/display` | Build prerequisite in the baseline manifest |
| `device/cherish/sepolicy` | Build prerequisite in the baseline manifest |
| `device/samsung/m11q` | Product/lunch selection in the baseline manifest; other device source pins remain in the handoff |
| `vendor/cherish` | Optional product/OTA customization in the baseline manifest |
| `build/make` | Optional companion OTA customization in the baseline manifest |

The full patch route is the 2026-10-12 combined baseline, the two applicable
patches from its IMS supplement, then the two 2026-10-16 VoWiFi patches. The
index resolves that global sequence into a separate ordered list for each
project. The baseline is not an additional layer on top of the historical
`ims-20261010` patch series.

## Older forks and historical checkpoints

Branches such as `m11q-volte`, `m11q-vowifi-audio-path` and
`m11q-emergency-capability-mask` remain available as recorded donor history.
Their names alone do not establish that they contain the latest Cherish
integration. In particular, the old Telecom donor follows a LineageOS-derived
base; its changes were adapted to CherishOS. It must not replace the current
Cherish project wholesale.

The `frameworks/base:m11q-volte` donor also contains microG and Play Integrity
changes outside the IMS checkpoint. This index describes the IMS source recipe;
it does not silently import those separate customizations or claim an exact
snapshot of every file in a previously built ROM.

Existing branches, checkpoints and APK hash contracts are retained. Patch paths
stay stable so older links and manifests continue to work.

## Keeping the two source routes synchronized

For subsequent changes to either synchronized project:

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

To also replay the patches against actual local fork objects, place the two
clones under a common directory as `telephony/` and `telecomm/`, with the indexed
commits available, then run:

```sh
python3 tools/verify_cherish_source_index.py --forks-root /absolute/path/to/fork-clones
```

The local verification uses temporary indexes and preserves checkout refs,
source files and the real indexes. It does not check GitHub availability or
establish that the current branch head still equals the recorded pin.
