# Stage 3 private payload inventory

The public [`payload-manifest.tsv`](../devices/m11q/payload-manifest.tsv) pins
stock inputs by path, byte size, and SHA-256. It contains metadata only, not
Samsung payload bytes. The Stage 3 rows were identified from the M115F CWK3
`system.img` and the local device-tree integration.

`copy` means the verified stock file is used unchanged at the listed device-tree
destination. `transform-input` means the listed hash belongs to the **stock
input**, while the locally used destination is modified or repacked. The
verifier never copies a `transform-input` over that destination; with
`--stock-input-dir`, it stages the original under its stock `/system/` path.
The existing `patch-to-stage1` row has the same separation for `imsservice.apk`.

`mnomap.json`, `imsswitch.json`, `imsprofile.json`, and `globalsettings.json`
are entries inside the stock `imsservice.apk` (`res/raw/`), not separate files
on the system partition. The existing APK row pins those embedded resources;
they must not be published as independent Samsung-derived JSON files.

Four local device-tree outputs have no one-to-one Samsung stock source and are
therefore **not** represented as `copy` rows:

| Local output under `ims/proprietary/` | Provenance boundary |
| --- | --- |
| `app/sveservice/lib/arm/libm11q_sve_compat.so` | Built from project-authored `ims/compat/sve/m11q_sve_compat.cpp` using the device-tree helper. |
| `app/sveservice/lib/arm/lib_android_FrameCapture.so` | Audio-safe, video-disabled ABI stub built from `ims/compat/sve/m11q_framecapture_stub.c`; not a copy of the stock FrameCapture library. |
| `lib/arm/liberc.so` and `lib/arm/libers.so` | Private renamed compatibility libraries; the exact source and preparation procedure are not yet captured in the public workflow. |

The `transform-input` rows for `UnifiedWFC.apk`, `sveservice.apk`,
`EpdgService.apk`, and `liberis_strongswan.so` pin the original Samsung files,
but their complete local transformation procedures are not yet published.
The `libAudioFWInterface.so` stock input is transformed by the device-tree
`ims/compat/sve/patch_audiofw_imports.py` helper. This inventory is not a
claim that a fresh public checkout can rebuild every Stage 3 private output.

The existing verifier accepts an extracted `system/` directory (or its parent),
not an ext4 `system.img` directly. It verifies stock inputs without publishing
them. No APK, JSON payload, ELF, or other Samsung-derived content belongs in
Git history.
