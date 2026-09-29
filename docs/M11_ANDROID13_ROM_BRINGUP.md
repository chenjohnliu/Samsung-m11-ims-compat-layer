# Samsung Galaxy M11 Android 13 IMS ROM bring-up

Status snapshot: 2026-09-29. This guide joins the public IMS payload builders,
the M11 device-tree integration, and the ROM-specific Android source changes.
It is an evidence-based bring-up path, not a claim that every Android 13 ROM
can currently be built from one command or that all carriers have working IMS.

## What is validated

| ROM / target | Validated result | Still unverified or failing |
|---|---|---|
| CherishOS 4.12 / Android 13, M11 `SM-M115F`, CWK3 stock inputs, Taiwan Mobile | With one active SIM at a time and SELinux Enforcing: outgoing/incoming VoLTE with two-way audio; SMS send/receive; SIM1 hot-swap recovery; outgoing VoWiFi to 188; incoming VoWiFi with sustained two-way audio after BT1. | Concurrent DSDS, emergency calls, ViLTE, handover, alternate audio routes, other carriers/firmware/models. Pure IMS transport for outgoing SMS is not claimed. |
| crDroid 13 / Android 13, same device and BT1 payload | Direct-LTE 188, outgoing VoWiFi and incoming VoWiFi succeeded with audible media and normal teardown. Incoming media additionally requires the m11q-gated post-`MODE_IN_CALL` Telecom callback published as [`66d3d91d`](https://github.com/chenjohnliu/android_packages_services_Telecomm/commit/66d3d91d238436c9a04cd4b653f3db02db4f901e) and [`29fc1533`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/29fc1533c06fe54ef80d3808698d33edd93caed8). The source audit found all nine known production patch groups from the public CherishOS forks in the local crDroid source trees. | Before the workaround, an allowed IWLAN-to-LTE handover led to an INVITE rejected with SIP 487; the policy in [`d11cbe58`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/d11cbe58dfdf81c284788c50e5b6e37de47cf5d4) now forces a fresh bearer and restores calling on PLMN 46697. The UE-versus-carrier cause of the 487 remains unresolved. Turning Wi-Fi off during an active VoWiFi call intentionally drops that call. Other configured PLMNs, concurrent DSDS, emergency calls and alternate audio routes are not runtime-validated. |

The detailed source map and log interpretation are in
[`CRDROID_ANDROID13_IMS_RESTORATION.md`](CRDROID_ANDROID13_IMS_RESTORATION.md).
The BT1 cross-ROM media result is in
[`STAGE3_MT_VOWIFI_MEDIA.md`](STAGE3_MT_VOWIFI_MEDIA.md). A source patch match
does not prove a ROM's audio route or native media path is compatible.

## 1. Pin the target before copying anything

Record these values for the build you intend to reproduce:

- Device: Samsung Galaxy M11 `SM-M115F`, codename `m11q`.
- Android base and exact ROM revision.
- Device, vendor, kernel and common-tree revisions from that ROM's manifest.
- Stock firmware / CSC. The public payload manifest is pinned to
  `M115FXXS5CWK3` (Android 12, BRI reference).
- SIM slot, carrier PLMN, and whether the subscription is the only active SIM.

The compatibility repository does not pin a complete ROM manifest, vendor
tree, kernel, or compiler configuration. Use matching M11 device/vendor/kernel
sources for the selected ROM and record their revisions. Do not transplant
source or proprietary files from another Samsung model.

## 2. Extract and verify private stock inputs

Obtain the firmware through a lawful source. The original bring-up used this
Linux/WSL sequence to extract the CWK3 `system` partition:

```bash
mkdir -p work/ap work/super work/partitions
tar -xf /path/to/AP_M115FXXS5CWK3_...tar.md5 -C work/ap super.img.lz4
lz4 -d work/ap/super.img.lz4 work/super/super.sparse.img
sha256sum work/super/super.sparse.img
simg2img work/super/super.sparse.img work/super/super.raw.img
python3 /path/to/lpunpack.py -p system \
  work/super/super.raw.img work/partitions
sha256sum work/partitions/system.img
```

For the reference BRI firmware, the decompressed sparse `super` hash is
`5416b7e351ff075aee6c04ad274bb040483f80d36d72d81d3fec5811aa761e92` and the
extracted `system.img` hash is
`9136dc82d36367b09ff373af3b1adbfa75cedd1bf06f8648bf82069bc6f21b8d`. Stop if
either differs. The original `lpunpack.py` was a workspace-local helper and is
not bundled in this repository.

The original bring-up then extracted the manifest's `/system/...` files from
that image with a local `extract_ext4.py` script that imports a Python `ext4`
module. Neither helper nor that dependency is published here. To repeat the
file-extraction step, pass the manifest's stock paths to the local helper and
retain the `system/` directory prefix:

```bash
mapfile -t STOCK_PATHS < <(awk -F '\t' 'NR > 1 && $1 ~ /^\/system\// { print $1 }' \
  devices/m11q/payload-manifest.tsv)
python3 /path/to/extract_ext4.py \
  work/partitions/system.img \
  /path/to/private/m11q-cwk3-extracted \
  "${STOCK_PATHS[@]}"
```

This documents the actual manual extraction sequence; the helper tools and
Python dependency still need to be obtained and version-pinned by the builder.
The hash-verified historical run is recorded in
[`FRESH_EXTRACTION_VALIDATION.md`](FRESH_EXTRACTION_VALIDATION.md).

Run the public manifest verifier from this repository's root. The first path
must be the extracted `system/` directory, not the ext4 image. Use a private
staging path outside Git for stock inputs and reports:

```bash
python3 tools/verify_payload.py \
  /path/to/private/m11q-cwk3-extracted \
  /path/to/android/device/samsung/m11q \
  --copy \
  --stock-input-dir /path/to/private/m11q-cwk3-inputs \
  --report /path/to/private/reports/m11q-payload-verification.json
```

Require every row in `devices/m11q/payload-manifest.tsv` to report `verified`.
`--copy` places only unchanged `copy` rows at their device-tree destinations;
the verifier stages original stock inputs for `patch-to-stage1`,
`transform-input`, and `build-input` rows under the private staging directory.
It does not create the transformed IMS payload.

Generate the required project-modified files from those exact inputs using the
linked builder instructions:

- `imsservice.apk`: [`IMS_APK_BUILDER.md`](IMS_APK_BUILDER.md) and
  [`STAGE3_MT_VOWIFI_MEDIA.md`](STAGE3_MT_VOWIFI_MEDIA.md), including the BT1
  post-ESTABLISHED transform. The expected aligned unsigned BT1 output is
  `832ad6fca643791a19776be14cb11ad6d1395bfe3d128e058dc4442e703990a9`.
- `UnifiedWFC.apk`: [`UW1_UNIFIEDWFC_SIM_MOBILITY.md`](UW1_UNIFIEDWFC_SIM_MOBILITY.md).
- `sveservice.apk`: [`SV1_SVESERVICE_MEDIA.md`](SV1_SVESERVICE_MEDIA.md).
- `EpdgService.apk`: [`EC1_EPDGSERVICE_ANDROID13_COMPAT.md`](EC1_EPDGSERVICE_ANDROID13_COMPAT.md).
- ERIS private crypto libraries: [`ER1_ERIS_PRIVATE_CRYPTO.md`](ER1_ERIS_PRIVATE_CRYPTO.md).
- Remaining copied, transformed and locally compiled device outputs:
  [`STAGE3_PAYLOAD_INPUTS.md`](STAGE3_PAYLOAD_INPUTS.md) and the M11 device
  tree's [`ims/README.md`](https://github.com/chenjohnliu/android_device_samsung_m11q/blob/9aebafee57492a75cadd115ae80ea21db378a760/ims/README.md).

Follow each builder's hash and structural checks. A deterministic unsigned APK
is not automatically a runtime-validated ROM input: platform signing, ROM
integration, flashing, and device testing remain downstream steps. Never add
Samsung stock inputs, transformed APKs/SOs, decoded trees, or signing keys to
Git.

## 3. Integrate the M11 device tree

Use the public M11 device-tree `m11q-volte` branch at `d11cbe58` or a later
revision. Its IMS integration history is present through `97206c0e`;
[`9aebafe`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/9aebafee57492a75cadd115ae80ea21db378a760)
updates the payload verifier and generation instructions, and
[`d11cbe58`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/d11cbe58dfdf81c284788c50e5b6e37de47cf5d4)
adds the stable fresh-bearer policy in
`overlay/packages/apps/CarrierConfig/res/xml/vendor.xml`. Read that tree's
`ims/README.md` and follow its Integration section to install the `ims`
directory and apply the `device.mk` and `BoardConfig.mk` fragments. Run its
`ims/verify_payload.ps1` after private outputs are in place.

Keep SELinux Enforcing. Review the exact ROM branch's policy for the Samsung
IMS processes, ePDG tunnel and system_ext paths. Do not use global permissive
SELinux or copy generated `audit2allow` output as a substitute for a policy
review. A path mismatch, missing service label, or absent native dependency is
a stop condition even if the ROM compiles.

## 4. Port the Android framework changes

The nine known production changes in the five public CherishOS Android forks
are enumerated with source and target baselines in
[`CRDROID_ANDROID13_IMS_RESTORATION.md`](CRDROID_ANDROID13_IMS_RESTORATION.md).
The documented source history has two distinct baselines: the M11 public fork
refs based on CherishOS, and the manually adapted crDroid source revisions.
For a matching CherishOS checkout, require clean Git trees and confirm each
checkout is at the recorded base revision before using the commands below to
replay only the IMS commits in order. Do not switch an entire project to the
fork branch: `frameworks/base:m11q-volte` also contains unrelated microG and
Play Integrity changes. This command sequence is reconstructed from the public
commit map and has not been replayed from a fresh checkout in this task.

```bash
git -C frameworks/base fetch \
  https://github.com/chenjohnliu/android_frameworks_base.git m11q-volte
git -C frameworks/base cherry-pick \
  e9346dd40f6095d85c8ac90f46e935ab7c60e240 \
  15a303b8fa069ff03b6aa9a0964067b152742fac \
  73178bfc7d1e81b64b02d2b24c14ef24a8a1ecdf

git -C frameworks/opt/net/ims fetch \
  https://github.com/chenjohnliu/android_frameworks_opt_net_ims.git \
  m11q-emergency-capability-mask
git -C frameworks/opt/net/ims cherry-pick \
  1b1a32269a62de0e82e3ede53bf2c44751307f18

git -C frameworks/opt/telephony fetch \
  https://github.com/chenjohnliu/android_frameworks_opt_telephony.git m11q-volte
git -C frameworks/opt/telephony cherry-pick \
  6c209a7d4fb239e8c8826d1c303f26dd6417dd5a

git -C packages/services/Telephony fetch \
  https://github.com/chenjohnliu/android_packages_services_Telephony.git m11q-volte
git -C packages/services/Telephony cherry-pick \
  cf338879ae9ae3a946a84d4678c245c51c98e753 \
  afedb3add75f2f5120f598942f91d8f4ba07d382 \
  26d0551acfa76e1fbcbc63e1114327e578badef7

git -C system/netd fetch \
  https://github.com/chenjohnliu/android_system_netd.git m11q-volte
git -C system/netd cherry-pick \
  8e455b91f8aa5b52771fbcf0250a7181f16ec43e
```

Stop on a baseline mismatch or cherry-pick conflict and review the source
context; do not resolve it by taking the complete fork branch. For crDroid 13,
the original port did not cherry-pick those commits. It applied their
production behavior to the crDroid baselines listed in the restoration record
and reconciled the different `Android.bp` dependency context. That record is
the source map for repeating this manual port. Required pairings include:

- `IPhoneSubInfo.aidl` with its `PhoneSubInfoController` implementation;
- framework ePDG Binder methods with `system/netd`'s `IOemNetd` AIDL and
  implementation, plus the generated AIDL build dependency;
- the IPv6-before-address setup change with the legacy ePDG service; and
- Telephony's SIM fallback logic with the M11 carrier resource overlay.

`SemSystemProperties.java` must follow the public fork implementation recorded
in the source map. The emergency MMTEL production change is present in the
crDroid port, but its upstream test-only hunk was not imported. Do not replace
ROM-specific `Android.bp`, product, SELinux, or carrier configuration with a
mechanical cherry-pick without checking the local source context.

**Porting limitation:** the matching CherishOS commit replay and the crDroid
manual source map are now documented, but the compatibility repository still
does not package crDroid's adapted changes as ordered patch files or provide an
apply/preflight tool. A new ROM port must be reviewed against its own baseline;
do not describe it as reproducible until the changes apply cleanly from a
recorded checkout.

## 5. Build, flash, and validate in stages

Build the ROM with its normal project workflow. The compatibility repository
does not build the Android ROM or provide signing keys. The ROM build should
sign integrated privileged APKs with that ROM's platform key. Preserve the
exact source, stock-input, builder-report, and payload-verifier identities for
the build under test.

After flashing, verify each stage separately under SELinux Enforcing:

1. **Boot and registration:** `com.sec.imsservice` remains alive; the active
   subscription registers for IMS; Android reports the expected MmTel voice
   capability. An icon alone is not sufficient evidence.
2. **VoLTE:** place a known test call such as 188, then test a real incoming
   call. Confirm ringing, answer, bidirectional audio, and normal teardown.
3. **SMS:** test outgoing and incoming separately. Record whether outgoing
   delivery was IMS `MESSAGE` or the validated modem fallback; do not infer
   pure IMS transport from a successful message.
4. **VoWiFi:** wait for IWLAN registration, call 188, then test an incoming
   call from another handset. Verify sustained audio in both directions and
   normal teardown, not only call setup.
5. **Idle Wi-Fi-to-LTE transition:** for the M11/Taiwan Mobile overlay, test
   after Wi-Fi is disabled and the status returns to VoLTE. On PLMN 46697 the
   configured disallow rule should tear down IWLAN and establish a fresh WWAN
   IMS bearer. This avoids the handover continuity path associated with the
   reproduced SIP 487; the precise UE-versus-carrier cause remains unresolved.
6. **Active-call transition:** document that the same policy disconnects an
   active VoWiFi call when Wi-Fi is turned off. This is the configured tradeoff,
   not successful handover.

The policy from device-tree commit `d11cbe58` is present for PLMNs 46601,
46605, 46692, and 46697, but only 46697 has runtime validation. The attempted
native active-W2L experiment was reverted; this CarrierConfig rule is the
current implementation. Recheck carrier registration and call behavior before
claiming support for the other three or another operator.

## 6. Reproducibility gaps to close before claiming general bring-up

The public material now records the original manual CWK3 extraction commands,
manifest-driven payload extraction, CherishOS commit replay order, crDroid
source map, deterministic transformers, device integration, and runtime
results. The manual procedures for the first two areas are now written above;
the remaining work is to package and pin those helper tools and turn the
crDroid source map into a clean-checkout patch workflow. It still lacks:

These are independent gaps, not a required sequence. The earlier crDroid
incoming-VoWiFi media blocker is closed by the published Telecom and m11q
post-`MODE_IN_CALL` integration. Remaining work concerns clean-checkout
reproducibility, additional carriers and the separately tracked handover scope.

1. bundled, version-pinned image and ext4 extraction tools plus a clean-checkout
   extraction validation; the documented workflow currently uses
   workspace-local helpers;
2. ordered patch files and an apply/preflight tool for the crDroid adaptations
   and other non-CherishOS baselines; the matching CherishOS commit replay is
   documented above;
3. a pinned complete ROM/device/vendor/kernel manifest for a fresh build; and
4. additional runtime carrier and handover results beyond the tested
   M11/Taiwan Mobile configuration.

Until those are closed, the public recipe is reproducible for the individual
payload transformations and documents the tested CherishOS baseline, but it is
not yet a one-command, clean-room recipe for arbitrary M11 Android 13 ROMs.
