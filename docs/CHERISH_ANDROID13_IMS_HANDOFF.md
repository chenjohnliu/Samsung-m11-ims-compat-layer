# Independent CherishOS Android 13 IMS handoff — M11

## Outcome and hard boundary

This is a source inventory and porting procedure, **not a verified clean-build
recipe**. The intended target is Samsung M11 (`m11q`, SM-M115F), CherishOS
Android 13, using Samsung firmware `M115FXXS5CWK3`. The exact new CherishOS
manifest and per-project revisions still need to be selected and recorded.
No target port, Android ROM build, signing, flashing or runtime validation was
performed for this handoff.

Allowed inputs are public GitHub source, the user's
`~/my_rom_patches/cherish`, and legally owned, hash-matching **raw CWK3 stock
originals**. The latter is an explicitly approved exception, not permission to
consume existing patched binaries. Do not read or consume a crDroid checkout,
its output directories, private patched APKs, saved decoded trees, or keys
from that build. Published project-authored patches are allowed source inputs;
their historical donor commit IDs are metadata, not instructions to access
the donor checkout. This guide does not require that checkout or its logs.

**One input gap remains:** ER1 requires two exact Android 12 ARM32 BoringSSL
libraries with unknown source/build provenance. The raw CWK3 pair was checked
and is different. See [the comparison](ER1_ERIS_PRIVATE_CRYPTO.md#cwk3-input-comparison--2026-10-10).
Do not claim dependency closure or a deployable port until this is resolved.
Do not remove ER1 or repin an arbitrary pair to make verification pass.
Either change would need a separate compatibility decision and device test.

The authoritative inventory is
[`cherish-android13-handoff.json`](../devices/m11q/cherish-android13-handoff.json).
It intentionally records `dependency_closure=false` and `deployable=false`.

## Public inputs and revision lock

Clone/fetch these repositories from GitHub and verify each pinned commit.
Use this guide and inventory from their publication commit or later, but use
the following donor revisions for the source being ported. A moving branch
name alone is not a lock.

| Input | Branch | Donor revision |
| --- | --- | --- |
| [Compatibility source](https://github.com/chenjohnliu/Samsung-m11-ims-compat-layer) | `main` | `9b94f710ac189db495326c72d99c1e350c445305` |
| [M11 device source](https://github.com/chenjohnliu/android_device_samsung_m11q) | `m11q-volte` | `0f1da5855d27841d53743cd878ecd2d09679a941` |
| [M11 vendor source](https://github.com/chenjohnliu/proprietary_vendor_samsung_m11q) | `13-64` | `6a8923918e90b734913cab84bc8ac7022a2dc143` |
| [Telecom source](https://github.com/chenjohnliu/android_packages_services_Telecomm) | `m11q-vowifi-audio-path` | `8e1a9a333a5692343f8bede5a2fe2dcac0d44489` |
| [M11 kernel source](https://github.com/chenjohnliu/android_kernel_samsung_sdm450) | `lineage-20` | `3936713dfd4d653c2c0cc4852ec412c0b6bd01b3` |

The public device repository contains no tracked `ims/proprietary` payload.
The vendor repository is not a substitute for the Samsung IMS APK/JAR/native
inputs. Presence of these repositories alone does not make a complete image.

The local Cherish patch directory was inventoried as ten flat patch files:
`audio_hal.patch`, `basicapps.patch`, `calendar.patch`,
`cherish_product.patch`, `glengine.patch`, `gralloc_pagesize.patch`,
`optimization.patch`, `ota_survival.patch`, `ota_survival2.patch`,
`sepolicy_property.patch`. It contains no IMS implementation, ordering guide
or apply script. Identify each destination project from its diff paths in
the selected target tree; do not infer patch order or project from filename.
Record file hashes before replay and stop if the local inputs have changed.

## Source port: preserve target ownership

1. Resolve the public CherishOS Android 13 manifest and record the manifest
   commit plus a revision-locked project list. Start with clean target trees.
   Resolve the device product naming/inheritance: the donor exposes
   `lineage_m11q`, not a ready-to-use Cherish product. Retain `device.mk`'s
   inclusion of `ims/ims.mk` and the intended platform-signed, privileged
   system_ext/32-bit Samsung IMS packaging when adapting product names.
2. Review and adapt the eight source patches listed, in per-project order,
   in [`platform/checkpoints/ims-20261010/manifest.json`](../platform/checkpoints/ims-20261010/manifest.json).
   They cover `frameworks/base`, `frameworks/opt/net/ims`,
   `frameworks/opt/telephony`, `packages/services/Telephony`, and `system/netd`.
   Preserve Cherish-specific behavior; do not replace those projects with
   donor trees. The recorded base/head/tree hashes prove historical replay,
   **not** applicability or identical tree hashes on a new target base.
3. After the historical frameworks/base series, apply the
   [import-only SystemUI correction](../platform/systemui/0001-fix-ims-registration-constant-import-package.patch)
   using `git apply` (it is a plain diff). The constants belong to
   `android.telephony.ims.stub.ImsRegistrationImplBase`.
   Do not also apply the [complete icon patch](../platform/systemui/wfc-registration-icon.patch)
   on top of the checkpoint: that would duplicate the change.
4. Port the Telecom call-audio hooks from the pinned public Telecom revision
   onto Cherish's `packages/services/Telecomm`. Include the published
   [SA2 helper sources](../platform/telecom/sa2/) and the corresponding device
   resource overlay. Review both call-audio manager and mode-state-machine
   hooks; copying only the helper classes does not integrate them.
5. Integrate the four published SEH bridge sources under
   [`platform/java/com/android/internal/telephony`](../platform/java/com/android/internal/telephony/)
   through the Telephony patch/build configuration. These publish Samsung
   modem APN profiles; they are not a substitute for the IMS service bridge.
6. Retain the existing phone-number fallback and registration-derived icon
   changes from the frameworks/base series. They are Android API/UI
   compatibility changes, not a fake number or network-state override.
7. For each destination project, record its target base, applied/adapted
   patch hashes, resulting commit/tree hashes, and conflict resolutions.
   Do not bypass a source gate with a new baseline pin merely to get PASS.

The independent port may need source-gate adaptation because several tools
expect an exact historical baseline. A failed baseline/context check is a
request for source review, not proof of a runtime bug and not permission to
consume a forbidden donor output.

## Private payload reconstruction order

Work in fresh private staging directories. Never commit raw, decoded,
transformed or signed Samsung binaries. Verify every required stock file
against [`payload-manifest.tsv`](../devices/m11q/payload-manifest.tsv), including
unchanged-copy rows; matching a firmware label is insufficient.
`tools/verify_payload.py --help` documents the extractor-layout and copy
arguments. Keep the manifest's `system/...` paths rather than guessing names.

Use the toolchain pins in
[`imsservice-build.json`](../devices/m11q/imsservice-build.json), including
apktool 2.9.3, the pinned Java 11 executables, R8 and zipalign. Builders must
use fresh decoding/cache state. A tool name/version alone does not establish
its required hash. Invoke each script's `--help` for exact file arguments.

| Order | Producer and inputs | Contract / final boundary |
| --- | --- | --- |
| 1 | `build_imsservice.py`: raw imsservice, raw framework-res, raw imsmanager, fresh target Android 13 framework JAR, seven public bridge Java sources | [IMS build](../devices/m11q/imsservice-build.json); intermediate only |
| 2 | `build_imsservice_w2l_trial.py`: order-1 output plus raw imsmanager | [BV1](../devices/m11q/imsservice-w2l-trial-build.json); intermediate only |
| 3 | `build_legacy_wfc_gate.py`: exact order-2 output | [LG3](../devices/m11q/legacy-wfc-gate-build.json); final unsigned IMS, stock Timer F restored |
| 4 | `build_epdgservice_w2l_trial.py`: raw EpdgService | [EC2](../devices/m11q/epdgservice-w2l-trial-build.json); intermediate only |
| 5 | `legacy_epdg_prefix_compat.py`: exact order-4 output | [LG2](../devices/m11q/legacy-epdg-prefix-build.json); final unsigned ePDG |
| 6 | `transform_unifiedwfc_sim_mobility.py`: raw UnifiedWFC | [UW1](../devices/m11q/unifiedwfc-sim-mobility-contract.json) |
| 7 | `build_sveservice.py`: raw sveservice | [SV1](../devices/m11q/sveservice-media-contract.json) |
| 8 | `transform_eris_private_crypto.py`: raw stock ERIS plus exact crypto/SSL pair | [ER1](../devices/m11q/eris-private-crypto-contract.json); **input provenance blocked** |
| 9 | `global_wfc_profile_policy.py`: reviewed IMS profiles, ePDG config and base vendor XML | [global WFC v2](../devices/m11q/global-wfc-profile-policy.json); source XML, not an APK |

All producers are under [`tools/`](../tools/). These historical `trial` names
do not mean the old experimental switches should be enabled. The intermediate
IMS artifact contains the old BU1 16-second timer experiment: **never deploy
it**. Only the LG3 terminal artifact restores the stock 128-second Timer F.

For the first IMS builder, use `--framework-mode compatible` with the freshly
built **CherishOS** `framework-minus-apex.jar`. This validates the required ABI;
it does not relax exact DEX/APK output hashes. `golden` mode demands the old
exact framework hash and must not be satisfied using a forbidden ROM output.
The user performs any target framework/ROM build required to obtain this JAR.
Stop and review if strict output hashes differ; `--discover-pins` is an audit
mechanism, not automatic acceptance of a new payload.

Unsigned terminal identities are recorded in the JSON inventory. Platform
signing/zip alignment and packaging must use the target's own approved keys
and build integration. Signed APK hashes will differ from unsigned hashes;
verify payload content and certificate separately. Do not recycle old keys.

## Behavior to carry forward, and not to invent

- Use modem-led **legacy IWLAN** and stock Samsung handover. Keep Android's
  Wi-Fi deferred shutdown. Do not enable the retired AP-assisted EC2/BV1
  W2L experiment or introduce a new arbitrary delay/retry/media algorithm.
- Retain BT1's stock-derived incoming-audio placement, the post-`MODE_IN_CALL`
  incoming-audio hook, and SA2 transition callbacks. Do not strip these
  compatibility hooks just because stock lacks an Android 13 adapter.
- Keep stock Timer F at 128 seconds. Do not ship the old 16-second BU1 trial.
- Use global WFC v2: 93 stock-profile PLMNs across 33 MCCs, with the four old
  Taiwan-specific framework IWLAN-to-LTE blocking arrays removed. This is
  availability configuration, not a bypass of carrier provisioning or proof
  that every listed carrier works.
- Support one active IMS subscription in SIM1 **or** SIM2. Dual-active/DSDS
  operation is not claimed. Functional SMS includes supported fallback;
  pure outgoing IMS SMS is not guaranteed.
- Stock weak-signal testing did not automatically return an ongoing LTE call
  to IWLAN merely because Wi-Fi reconnected; VoWiFi returned after hang-up.
  Do not add a forced mid-call return just to change that behavior.
- Do not claim or test emergency calling by placing real emergency calls.
  Existing capability-bit correctness does not establish emergency service.

## Validation and acceptance

Host tests are source-only and do not supply the missing ER1 inputs:

```bash
python -m unittest discover -s tests -v
```

Run the full suite on a Linux filesystem/environment for its POSIX permission
checks. Source-dependent tests may skip when optional target inputs or a host
JDK are absent; skips are not target validation. To exercise the actual icon
source, set `M11_SYSTEMUI_SOURCE` to the freshly patched **CherishOS**
`MobileSignalController.java`; set `M11_SYSTEMUI_API_CLASSPATH` to that target's
Android 13 API JARs for the real constant-import compilation check. Never use
an archived donor source/JAR to turn this target check green.

Run the following gates from the compatibility repository against the **new
target**. Replace the example paths with its actual source/product directories:

```bash
python tools/global_wfc_profile_policy.py verify-source --android-root /path/to/cherish
python tools/legacy_iwlan_trial.py verify-product --product-root /path/to/cherish/out/target/product/m11q
python tools/global_wfc_profile_policy.py verify-product --product-root /path/to/cherish/out/target/product/m11q
python tools/legacy_seh_apn_trial.py verify-product --product-root /path/to/cherish/out/target/product/m11q
python tools/sa2_telecom_audio_trial.py verify-product --product-root /path/to/cherish/out/target/product/m11q
```

LEG1 and SEH1 also support `verify-source --android-root ... --state-dir ...`;
SA2 supports `verify-source --source-root ... --backup ...`. Those source gates
require their own prepared transaction/backup manifests; do not manufacture
PASS by reusing another ROM's state directory after manually porting patches.
Inspect their `--help` and baseline requirements first. Review any
target-specific gate adaptation separately. Product gates inspect packaged
content, not platform-signing validity or live audio. Check final
LG3/LG2 payload contracts, stock Timer F, disabled AP-assisted flags, active-SIM
scope, SELinux/product packaging and the corrected SystemUI imports.
Source checks or icon appearance alone are not call-continuity proof.

Only after source integration and input closure are complete, ask the user
to perform one build/flash/test batch:

1. Verify the installed framework and terminal APK/DEX versions and active
   subscription. Use a known-good Internet connection: stock also failed
   VoWiFi incoming calls on the problematic home connection but passed on
   an alternate mobile hotspot. Do not attribute that failure to the port
   without the network control.
2. Test incoming and outgoing VoLTE and VoWiFi with a real peer, confirming
   both directions of audio. A service call to 188 cannot verify upstream
   speech. Test SMS send/receive and post-hang-up calling.
3. Test manual Wi-Fi off/on handovers in both directions and weak-signal
   departure. Maintain the same call/session without redial, with at most
   two seconds of audio interruption and at least 30 seconds of subsequent
   two-way speech. Repeat each intended transition three times.
4. Repeat the supported single-active configuration on the other SIM slot,
   then verify a fresh LTE call after switching. Check icons with Wi-Fi
   off and after teardown; do not use an icon as a bearer/media assertion.
5. Use [`capture_ims_stock_handover_termux.sh`](../tools/diagnostics/capture_ims_stock_handover_termux.sh)
   on either ROM to record a labelled timeline; consult its help/doctor
   before capture. Archives may contain subscriber data and IPsec keys:
   keep them private, never publish them to GitHub.

A target bearer failure calls for modem/network investigation. A successful
bearer transfer followed by silence/disconnection calls for the IMS session
and media timeline. Build/API failures call for target-source adaptation.
Do not mix these outcomes or modify timers to conceal them.

This handoff is complete as an honest inventory; **the independent port is
blocked on ER1 input provenance and remains unvalidated on CherishOS**.

## Handoff publication checks — 2026-10-10

The public repository links, source/contract paths and producer CLI order
were inspected. Ten focused handoff tests passed. After removing the implicit
private SystemUI source fallback, the full source-only suite ran under Linux:
`Ran 343 tests`, `OK (skipped=5)`. Optional source/JDK-dependent checks were
not promoted to target acceptance. No Android ROM build or private payload
reconstruction was run for this publication, and no stock binary or key is
included in its commits. ER1's mismatch is recorded evidence, not a fix.

## Local patch snapshot — 2026-10-10

This table records the earlier read-only snapshot of
`/home/user/my_rom_patches/cherish`; hashes have not been freshly checked for
this document update. Rehash the current local files in the next task before
using these values as source pins. Each target path is relative to a project
whose repository has not yet been resolved. No patch ordering is inferred.

| Patch file | SHA-256 | Target diff path |
|---|---|---|
| `audio_hal.patch` | `1cdaa2ce6a1cb9a5f695e04be209ab3853f3cb768eebcc75979d3035c4ae2581` | `hal/Android.mk` |
| `basicapps.patch` | `70845f2d3dcab6ffbc32cfe713690ada4b7fc50a10b6108993bcbd9fea417590` | `config/basicapps.mk` |
| `calendar.patch` | `30dd87b6efccd70ab324a6744a3b8f2b99604fff7905be55e04a730493982ad9` | `src/com/android/calendar/Event.kt` |
| `cherish_product.patch` | `fa9ba7e09923cab166e5ba45b9c2301b40a4ca0805972168629a33e9e618e9e0` | `AndroidProducts.mk` |
| `glengine.patch` | `8a7fdee95cbe4322e60f4940336b573ee75af76c18cee910694b256dc88cd8dc` | `gpu_tonemapper/glengine.cpp` |
| `gralloc_pagesize.patch` | `f457d3461919c2aefec264cf2f2c5bf33f5ce7bee79c9e90e8b049589ac1e43e` | `gralloc/gralloc_priv.h` |
| `optimization.patch` | `50d27511b3a39a744b2a47721a3cc8b69aeb92e38064a552fa89780f02426be5` | `config/common.mk` |
| `ota_survival.patch` | `5673e6036a584011776c86d525e6ab39a62957a46f762855fcf5ab393331a72a` | `prebuilt/common/bin/backuptool.sh` |
| `ota_survival2.patch` | `77b3dcc2bac9c450d90bd9d131f4bd84f1675e2dad5822156cd5cfd382524cbf` | `tools/releasetools/non_ab_ota.py` |
| `sepolicy_property.patch` | `871c4cf274b79a0d45490f7eff8ae03f58cd49d0e5e3222336c24595584a5121` | `common/public/property.te` |
