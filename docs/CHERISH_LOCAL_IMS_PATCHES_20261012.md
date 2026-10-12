# Cherish local IMS patches (2026-10-12)

This supplement inventories the three IMS-related local patch copies from `my_rom_patches/cherish`. Each patch file is a literal byte-for-byte copy of its local WSL original and contains Android Java or XML source.

The MMS service compatibility patch is included here so all three local copies are represented publicly. It is already present in the parent checkpoint at `platform/checkpoints/cherish-20261012/manifest.json`; keep it as reference material and do not apply it again.

The newer Telecom permission patch and IMS emergency-capability test patch belong after the parent combined checkpoint. Apply each once to the matching project in the chosen source checkout. Do not replay the entire donor commits `66d3d91` or `1b1a3226`: their production hooks and capability correction are already included in the parent checkpoint. The parent checkpoint publication commit is pinned as `3b254f2c77ce6f7bcd3402643a44276a6f69337d`. Apply that checkpoint before these two supplemental changes.

In a WSL/Linux shell, set both variables below to absolute paths for the chosen source checkout and this repository's supplement directory. Run the check command for each patch, then its apply command:

```bash
CHERISH_SOURCE_ROOT="/absolute/path/to/chosen/cherish/source/root"
IMS_SUPPLEMENT="/absolute/path/to/cherish-public-source-completion/platform/checkpoints/cherish-20261012-ims-supplement"

git -C "$CHERISH_SOURCE_ROOT/packages/services/Telecomm" apply --check "$IMS_SUPPLEMENT/packages__services__Telecomm/secims-permission.patch"
git -C "$CHERISH_SOURCE_ROOT/frameworks/opt/net/ims" apply --check "$IMS_SUPPLEMENT/frameworks__opt__net__ims/emergency-capability-test.patch"

git -C "$CHERISH_SOURCE_ROOT/packages/services/Telecomm" apply "$IMS_SUPPLEMENT/packages__services__Telecomm/secims-permission.patch"
git -C "$CHERISH_SOURCE_ROOT/frameworks/opt/net/ims" apply "$IMS_SUPPLEMENT/frameworks__opt__net__ims/emergency-capability-test.patch"
```

Expected before and after Git trees, source repository URLs, source base commits, changed paths, and patch SHA-256 values are in [the manifest](../platform/checkpoints/cherish-20261012-ims-supplement/manifest.json). The source-copy hashes were checked against the local originals. The standalone MMS patch produces the same tree as the existing checkpoint's MMS patch.

The [source verification record](../devices/m11q/cherish-ims-supplement-source-verification.json) records replay and reverse replay for all three public patches, plus byte comparisons against nine live source files. Source HEADs and real Git indexes were unchanged.

The permission hunk comes from [Telecomm commit 66d3d91](https://github.com/chenjohnliu/android_packages_services_Telecomm/commit/66d3d91d238436c9a04cd4b653f3db02db4f901e). It declares `com.sec.imsservice.PERMISSION` for the existing Samsung audio-path call. The current Telecom uses system UID, so this restores the donor declaration without claiming that its previous absence caused a runtime failure.

The test comes from [IMS commit 1b1a3226](https://github.com/chenjohnliu/android_frameworks_opt_net_ims/commit/1b1a32269a62de0e82e3ede53bf2c44751307f18). It uses simulated capability masks to check that zero and an unrelated bit do not report emergency MMTEL, while the emergency bit does. It does not originate a telephone call.

No Android ROM build, Android unit test run, or new runtime validation was performed for this supplement. A manual build and runtime validation remain pending. The earlier capability correction and its 2026-09-26 no-dial runtime evidence remain recorded in [the emergency audit](EMERGENCY_CALLING_AUDIT.md).

The full local inventory contained 14 regular files, including 13 patches: these three IMS-related patches and ten non-IMS patches. The non-IMS group comprises eight build/product/app/OTA customization patches and two microG patches (one saved under `crdroid`). Local files remain useful copies; the three IMS patches now also have exact public copies and hashes here.

The non-IMS `microg_play_integrity.patch` is omitted from this IMS supplement. Its four public commits already exist on [the frameworks/base m11q-volte branch](https://github.com/chenjohnliu/android_frameworks_base/tree/m11q-volte): `eaf637ff`, `253643b4`, `b1fc884b`, and `b205e278`.
