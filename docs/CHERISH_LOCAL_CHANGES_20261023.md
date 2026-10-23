# Current CherishOS source changes: October 23, 2026

This records the earlier local-tree audit on October 23. Its device route was
subsequently replaced by the [direct m11q-volte source reference](DEVICE_SHARED_SOURCE_20261023.md).
The current device instructions are the shared pin plus one product patch; the
three-step device recipe and 26-step audit below remain historical evidence.

The source audit covered the 15 CherishOS projects with local changes. Twelve
project trees already exactly matched the published source index, and the vendor
tree exactly matched the previously published fingerprint commit. The new source
commits are the two product-policy groups and the shared-device DT2W change below.
Previously published work was not recommitted or used to rewrite existing history.

## New source commits

| Group | Source commit | Behavior and validation limit |
| --- | --- | --- |
| microG compatibility | [Framework 8a9f497d](https://github.com/chenjohnliu/android_frameworks_base/commit/8a9f497d0633eec34cf68bc24313c4079ff4979a) | Allows the compatibility signature and requested package visibility for the two supported package names signed with the pinned microG certificate. It does not grant this behavior to arbitrary packages. |
| Certificate-chain policy | [Framework 80a5b4fc](https://github.com/chenjohnliu/android_frameworks_base/commit/80a5b4fca0bbb2a2d08c9acf4c6e11ed3bb467fd) | Publishes the existing local removal of the PixelPropsUtils caller rejection. This changes the ROM policy; it is not a claim that Play Integrity passes. |
| Shared touchscreen DT2W | [Device a42e98ad](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/a42e98add2d431b5d677b4ec6e51f5f02ca3e0e7) | Replaces the Focaltech-only boot write with the shared Samsung `aot_enable,1` command. Focaltech command acceptance was checked; other controllers and a newly flashed boot path still require hardware validation. |

All four configured SPI touchscreen drivers implement that command: Focaltech's
FT8615 build profile, the Ilitek ILI9881/ILI7807 TDDI family, Himax HX83112 and
ILI7806S. These are source-supported candidates, not four newly tested phones.
The patch preserves forced enablement at boot and does not connect the Settings
switch to a power HAL.

## Device branch policy and dependencies

Only [device `m11q-volte`](https://github.com/chenjohnliu/android_device_samsung_m11q/tree/m11q-volte)
is maintained. The existing device `cherish-13-m11q-ims` branch is retained at
`f4a8473a4c8e14c85cce08241e2691e15ddd0a55`; this update neither advances nor deletes it.
The framework repository's Cherish branch is separate from this device policy.

The earlier audited Cherish device tree was reproduced with the indexed patch
recipe: the pinned base, the existing Cherish product-registration patch, the
fingerprint integration and then DT2W. The shared branch is provenance for the
device changes, not a claim that its whole tree is the Cherish product tree.

Fingerprint was already published as [device b47f3ce2](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/b47f3ce29f06c8b490ae2e3089e97b5c36b0423b)
and [vendor 8aac25ba](https://github.com/chenjohnliu/proprietary_vendor_samsung_m11q/commit/8aac25babaee78b9243c2ee05aaf8180d88b3902).
The recipe now accounts for that device integration and records the matching
vendor dependency without copying Samsung binary payloads into this repository.
The maintainer reported working Focaltech fingerprint; other fingerprint backends
remain pending community validation.

## Existing changes accounted for

| Area | Existing source content |
| --- | --- |
| IMS, framework and telephony | Samsung API compatibility, SEH APN and routing bridge, IWLAN recovery/MTU, caller/subscription handling, IMS capability handling, SystemUI indicators and number display |
| Telecom and MMS | Samsung audio handover, permissions and paired MMS binder compatibility |
| Build, graphics and policy | Legacy audio power dependency, graphics compiler fixes and existing camera-property policy adjustment |
| OTA and product | Non-A/B addon.d support, backuptool lifecycle and Jelly inclusion |

These existing trees match the indexed public patches. Their presence as local
diffs results from the build checkouts remaining pinned to their original bases.
Publishing does not require resetting those source trees or rebuilding the ROM.

## Reproduction and validation

The [local supplement manifest](../platform/checkpoints/cherish-20261023-local/manifest.json)
added four ordered patch steps. That audit covered 14 projects and 26 steps,
with six synchronized platform forks and eight patch-only routes. The current
[source index](../devices/m11q/cherish-source-index.json) has 24 steps after the
device base migration described in the shared-device guide. Device branch
history is kept explicitly historical.

The accompanying [validation record](../devices/m11q/cherish-source-validation-20261023.json)
records exact forward/reverse tree replay and comparison with the audited current
source trees. No Android ROM build, APK build, release upload or new hardware wake
test was performed for this publication. The crDroid-only Light HAL patch remains
outside this update. The withdrawn NFC candidate remains withdrawn.
