# Source forks and patch index

The supplementary [2026-10-21 SMS over IWLAN bridge fix](SMS_IWLAN_FIX_20261021.md) changes compatibility-layer Java sources. It is not part of the historical platform patch chains listed below; keep its three bridge source changes together.

Use this page to locate the source used by the CherishOS Android 13 integration.
The [machine-readable index](../devices/m11q/cherish-source-index.json) lists all
14 checkpointed projects, their locked bases, ordered patches and expected trees.
It also distinguishes the synchronized full-source forks from older donor branches.
This inventory does not cover every project in the Android manifest.

The [2026-10-20 IMS API supplement](IMS_API_SUPPLEMENT_20261020.md) extends the
framework/base and Telephony source routes. The original data-service-state
fix has a Jio tester report; the preventive group and crDroid port remain
source/host-validated only. The Cherish index now has 24 ordered patches.

The [October 23 local-source update](CHERISH_LOCAL_CHANGES_20261023.md) explicitly
adds the existing microG signature and certificate-chain product policies, plus
the shared-device fingerprint and DT2W integration. These additions do not claim
a new ROM build or hardware acceptance.

The [shared-device source update](DEVICE_SHARED_SOURCE_20261023.md) now selects
`m11q-volte` directly. Its pinned base already includes fingerprint and DT2W;
only the Cherish product-registration patch is applied on top.

## Latest full-source branches

| Android project | Full source | Equivalent patches |
| --- | --- | --- |
| `frameworks/base` | [Framework: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_frameworks_base/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/frameworks__base/live-source.patch), [IMS API supplement](IMS_API_SUPPLEMENT_20261020.md), then [October 23 policies](CHERISH_LOCAL_CHANGES_20261023.md) |
| `frameworks/opt/net/ims` | [IMS framework: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_frameworks_opt_net_ims/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/frameworks__opt__net__ims/live-source.patch), then [capability test](../platform/checkpoints/cherish-20261012-ims-supplement/frameworks__opt__net__ims/emergency-capability-test.patch) |
| `frameworks/opt/telephony` | [Telephony: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_frameworks_opt_telephony/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/frameworks__opt__telephony/live-source.patch), [legacy IWLAN MTU](../platform/checkpoints/cherish-20261016-vowifi/frameworks__opt__telephony/legacy-iwlan-mtu.patch), then [UICC API service](IMS_API_SUPPLEMENT_20261020.md) |
| `packages/services/Telephony` | [Phone service: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_packages_services_Telephony/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/packages__services__Telephony/live-source.patch) |
| `system/netd` | [netd: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_system_netd/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/system__netd/live-source.patch) |
| `packages/services/Telecomm` | [Telecom: cherish-13-m11q-ims](https://github.com/chenjohnliu/android_packages_services_Telecomm/tree/cherish-13-m11q-ims) | [Baseline](../platform/checkpoints/cherish-20261012/packages__services__Telecomm/live-source.patch), [permission](../platform/checkpoints/cherish-20261012-ims-supplement/packages__services__Telecomm/secims-permission.patch), then [initial Wi-Fi audio](../platform/checkpoints/cherish-20261016-vowifi/packages__services__Telecomm/initial-wifi-audio.patch) |

The six platform branches start from the exact CherishOS bases recorded in the
checkpoints. Their complete Git trees match the patch replay results; this is
stronger than comparing only the files changed in the latest fix. Exact commits,
trees and patch-to-commit mappings are in the index.

The current device base is [m11q-volte at a42e98ad](https://github.com/chenjohnliu/android_device_samsung_m11q/tree/a42e98add2d431b5d677b4ec6e51f5f02ca3e0e7).
Apply only the [Cherish product-registration patch](../platform/checkpoints/m11q-shared-20261023/cherish-product.patch)
recorded in the [shared-device manifest](../platform/checkpoints/m11q-shared-20261023/manifest.json).
Fingerprint, shared-TSP DT2W and the current native IMS library packaging are
already in that shared base. The new device route supersedes the earlier
three-step recipe; its fingerprint and DT2W patches are historical, not extra
steps to apply on top of the current base. The older device
`cherish-13-m11q-ims` branch is left unchanged as historical provenance.

For each of the six platform projects, choose one source route: the indexed fork
commit already contains its entire listed patch chain. Applying those patches
again would duplicate the integration. Alternatively, use the locked upstream
base and apply its listed patch chain once. The current build checkout was not
switched or modified as part of this organization.

These are complete individual Android projects, not standalone ROM trees.
Their framework APIs, device overlay and other dependencies still come from
the rest of the [CherishOS handoff](CHERISH_ANDROID13_IMS_HANDOFF.md). A matching
source tree does not expand the [device validation scope](VALIDATED_FEATURES.md).

## crDroid patch route

The [crDroid index](../devices/m11q/crdroid-source-index.json) keeps seven
projects and now has 16 ordered patches. It uses the existing pinned public
upstream bases and complete ordered patch recipes, including the four new
API suffix patches. All seven final trees and reverse recovery were verified.
This supplement does not advertise a new full-source crDroid branch in the
maintainer's Cherish-parent forks. The local crDroid port and the published
patch route have the same four changed source files.

## Other projects and the patch route

| Project | Published source recipe |
| --- | --- |
| `packages/services/Mms` | [Combined baseline](../platform/checkpoints/cherish-20261012/packages__services__Mms/live-source.patch); the later supplement copy is reference-only |
| `device/samsung/m11q` | Pinned `m11q-volte` base, then the single [Cherish product-registration patch](../platform/checkpoints/m11q-shared-20261023/cherish-product.patch) |
| `hardware/qcom-caf/msm8953/audio` | Build prerequisite in the [baseline manifest](../platform/checkpoints/cherish-20261012/manifest.json) |
| `hardware/qcom-caf/msm8953/display` | Build prerequisite in the baseline manifest |
| `vendor/qcom/opensource/commonsys-intf/display` | Build prerequisite in the baseline manifest |
| `device/cherish/sepolicy` | Build prerequisite in the baseline manifest |
| `vendor/cherish` | Optional product/OTA customization in the baseline manifest |
| `build/make` | Optional companion OTA customization in the baseline manifest |

The full Cherish patch route is the 2026-10-12 combined baseline, the two applicable
patches from its IMS supplement, the two 2026-10-16 VoWiFi patches, then the
four 2026-10-20 API suffix patches and the two October 23 framework product-policy
steps. For the device only, the shared-device manifest replaces the earlier
base and chain with `m11q-volte` plus one product patch. Use each project's
current ordered list in the index; the chronological historical manifests are
not all extra layers to apply. The baseline is not an additional layer on top
of the historical `ims-20261010` patch series.

## Older forks and historical checkpoints

Six non-current platform donor refs were retired on 2026-10-17 and preserved by
archive tags at their recorded commits. Their archive tags and exact SHAs
are listed in the [branch retirement record](M11Q_BRANCH_RETIREMENT_20261017.md)
and machine-readable index. The six platform repositories use
`cherish-13-m11q-ims` as their default branch. The device repository retains
`m11q-volte` as its default and release branch.

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

The frameworks/base donor history also contains microG and certificate-chain
policy changes outside the historical IMS checkpoint. The October 23 supplement
now explicitly indexes the current local versions as two separate product-policy
patches. This does not claim a passing Play Integrity result or an exact snapshot
of every project in a previously built ROM.

The Telecom repository was recreated at the same URL as a direct fork of
`CherishOS/android_packages_services_Telecomm`, replacing its earlier crDroid
fork relationship. Its default branch is `cherish-13-m11q-ims`. The current
Cherish integration commit and historical donor commit were restored unchanged;
the latter is preserved by the archive tag in the retirement record. The 29
inherited crDroid branches remain in the verified local backup rather than
being republished. See the
[fork-origin verification record](../devices/m11q/telecomm-fork-origin.json).

The five other platform forks already have CherishOS parents. The device
repository is maintained on the shared `m11q-volte` branch; the older
`cherish-13-m11q-ims` branch remains historical provenance and is not updated
or removed by this source-index change. Checkpoint and APK hash contracts,
source commit pins and patch paths stay stable so the existing integration
recipe and historical M11 links continue to work.

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

To also replay the patches against actual local fork objects, place the six
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

The local verification uses temporary indexes and preserves checkout refs,
source files and the real indexes. It does not check GitHub availability or
establish that the current branch head still equals the recorded pin.
