# crDroid IMS source-verified route — 2026-10-18

This recipe describes the seven-project IMS source closure for the M11q crDroid 13 port. The index pins seven source repositories and twelve ordered patch steps. Eleven patch bodies reuse their existing public files; only the device SVE build/JNI integration is new. The index is not a full Android manifest, Android build receipt, or runtime receipt.

## Source replay and patch application

Run the following compatibility-repository commands from the compatibility checkout; Android source and device destinations are rooted separately. Use `devices/m11q/crdroid-source-index.json` as the source of truth. Replay verifies every patch hash and forward/reverse tree result without changing project worktrees:

```sh
python3 tools/replay_public_source_index.py \
  --repo-root <compat-checkout> \
  --index devices/m11q/crdroid-source-index.json \
  --source-root <ignored-temp-directory-inside-compat-checkout> \
  --report <private-work>/crdroid-source-replay.json
```

After syncing the seven projects to their indexed bases, preflight and apply the ordered patches:

```sh
python3 tools/apply_crdroid_source_index.py \
  --source-root <android-source-root> \
  --apply \
  --report <private-work>/crdroid-source-apply.json
```

The apply tool validates the complete batch before applying anything. Keep each project checkout clean. The device project must follow the indexed base `0f1da5855d27841d53743cd878ecd2d09679a941` plus its SVE patch to produce tree `e2c444a9c9a528417a088396bc52265c8ae78a98`. The same SVE integration is published in device commit [a125368a53a8ace26d91f778f28a12b240f46dbb](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/a125368a53a8ace26d91f778f28a12b240f46dbb), which also has later documentation changes and therefore is not the indexed final tree. For strict index validation, use the pinned base-plus-patch route. If a source tree already contains that commit, do not apply the SVE patch a second time; the later tree is outside the strict indexed route.

## Private payload inputs

Before copying or producing files, create `<work>/outputs`, `<work>/reports`, and the temporary parent directories `<work>/tmp/ims-source`, `<work>/tmp/ims-bv1`, `<work>/tmp/ims-lg3`, `<work>/tmp/epdg-ec2`, and `<work>/tmp/epdg-lg2`. Leave producer output files and the ER1 output directory `<work>/outputs/er1` absent; the producers create them.

Prepare the legally obtained CWK3 stock inputs privately. The public manifest contains metadata only. With the extracted `system/` directory (or its parent), stage the forty unchanged IMS payload files and private producer inputs:

```sh
mkdir -p <work>/outputs <work>/reports
python3 tools/verify_payload.py \
  <extracted-system-or-parent> <android-source-root>/device/samsung/m11q \
  --manifest devices/m11q/payload-manifest.tsv \
  --copy \
  --stock-input-dir <work>/stock-inputs \
  --report <work>/reports/payload-copy.json
```

All forty `copy` destinations are under `ims/`. Keep the nine source/transform inputs and every generated file under the private producer workspace. Do not publish firmware, generated APKs, libraries, decoded Samsung code, or machine-local paths.

## Source-verified producer order

Use the local compatible framework API JAR generated from the pinned source build as a compile/ABI classpath input. Public ABI fixtures and normalized `javap` comparisons provide the compatibility check; no framework JAR is distributed. The strict historical hash mode remains the default. Select `--mode source-verified` explicitly for this route. Java launchers are stage-specific as recorded in each public contract: the IMS builder uses the crDroid bundled JDK 11 launcher/compiler; BV1, LG3, SV1, EC2, and LG2 use their respective pinned launchers. Matching Java version strings do not imply matching launcher hashes.

Set `<bridge-java-root>` to this checkout's `bridge/java` directory. Run IMS source, BV1, and LG3 in order, passing each input report forward:

```sh
python3 tools/build_imsservice.py --stock-apk <stock-ims.apk> --framework-res-apk <framework-res.apk> --imsmanager-jar <imsmanager.jar> --bridge-source-root <bridge-java-root> --framework-jar <compatible-framework-api.jar> --framework-mode compatible --apktool-jar <apktool.jar> --java <ims-java> --javac <ims-javac> --javap <javap> --r8-jar <r8.jar> --zipalign <zipalign> --mode source-verified --output <work>/outputs/ims-source-unsigned.apk --report <work>/reports/ims-source-verified.json --work-dir <work>/tmp/ims-source
python3 tools/build_imsservice_w2l_trial.py --base-apk <work>/outputs/ims-source-unsigned.apk --imsmanager-jar <imsmanager.jar> --apktool-jar <apktool.jar> --java <bv1-java> --source-verified-input-report <work>/reports/ims-source-verified.json --output <work>/outputs/ims-bv1-unsigned.apk --report <work>/reports/ims-bv1-source-verified.json --work-dir <work>/tmp/ims-bv1
python3 tools/build_legacy_wfc_gate.py --base-apk <work>/outputs/ims-bv1-unsigned.apk --apktool-jar <apktool.jar> --java <lg3-java> --source-verified-input-report <work>/reports/ims-bv1-source-verified.json --output <work>/outputs/ims-lg3-unsigned.apk --report <work>/reports/ims-lg3-source-verified.json --work-dir <work>/tmp/ims-lg3
```

Build SVE and EPDG EC2 independently, then LG2 from EC2 and its receipt:

```sh
python3 tools/build_sveservice.py --stock-apk <stock-sveservice.apk> --apktool-jar <apktool.jar> --java <sv1-java> --output-apk <work>/outputs/sveservice-sv1-source-verified-unsigned.apk --report <work>/reports/sveservice-sv1-source-verified.json --source-verified
python3 tools/build_epdgservice_w2l_trial.py --stock-apk <stock-epdgservice.apk> --apktool-jar <apktool.jar> --java <ec2-java> --output <work>/outputs/EpdgService-ec2-source-verified-unsigned.apk --report <work>/reports/EpdgService-ec2-source-verified.json --work-dir <work>/tmp/epdg-ec2 --source-verified
python3 tools/legacy_epdg_prefix_compat.py --base-apk <work>/outputs/EpdgService-ec2-source-verified-unsigned.apk --source-verified --source-receipt <work>/reports/EpdgService-ec2-source-verified.json --apktool-jar <apktool.jar> --java <lg2-java> --output <work>/outputs/EpdgService-lg2-source-verified-unsigned.apk --report <work>/reports/EpdgService-lg2-source-verified.json --work-dir <work>/tmp/epdg-lg2
```

The `--stock-input-dir` option stages all three ER1 transform inputs under `<work>/stock-inputs/system/lib/`; pass that directory directly to ER1. Run UW1 and ER1 from the public contracts, and patch the exact stock AudioFW file with the indexed device helper. The AudioFW helper itself emits no JSON receipt, so record the output digest in the final verifier's expected `audiofw.json` shape:

```sh
mkdir -p <work>/outputs/er1 <work>/reports
python3 tools/transform_unifiedwfc_sim_mobility.py --contract devices/m11q/unifiedwfc-sim-mobility-contract.json --stock-apk <stock-UnifiedWFC.apk> --output-apk <work>/outputs/UnifiedWFC-uw1-unsigned.apk --report <work>/reports/UnifiedWFC-uw1.json
python3 tools/transform_eris_private_crypto.py --contract devices/m11q/eris-private-crypto-contract.json --input-dir <work>/stock-inputs/system/lib --output-dir <work>/outputs/er1 --report <work>/reports/er1.json
python3 <android-source-root>/device/samsung/m11q/ims/compat/sve/patch_audiofw_imports.py <work>/stock-inputs/system/lib/libAudioFWInterface.so <work>/outputs/libAudioFWInterface.so
python3 -c 'import hashlib,json,pathlib; p=pathlib.Path("<work>/outputs/libAudioFWInterface.so"); print(json.dumps({"status":"PASS","output_sha256":hashlib.sha256(p.read_bytes()).hexdigest()}))' > <work>/reports/audiofw.json
```

Stage the final generated files relative to `device/samsung/m11q/`. Keep the intermediate IMS source/BV1 and EPDG EC2 outputs for later stages, and preserve all reports at the filenames above.

| Generated output | Device destination | Producer output |
| --- | --- | --- |
| LG3 IMS APK | `ims/proprietary/priv-app/imsservice/imsservice.apk` | `outputs/ims-lg3-unsigned.apk` |
| SV1 SVE APK | `ims/proprietary/app/sveservice/sveservice.apk` | `outputs/sveservice-sv1-source-verified-unsigned.apk` |
| LG2 ePDG APK | `ims/proprietary/priv-app/EpdgService/EpdgService.apk` | `outputs/EpdgService-lg2-source-verified-unsigned.apk` |
| UW1 APK | `ims/proprietary/app/UnifiedWFC/UnifiedWFC.apk` | `outputs/UnifiedWFC-uw1-unsigned.apk` |
| ER1 `liberc.so`, `libers.so`, `liberis_strongswan.so` | `ims/proprietary/lib/arm/` | `outputs/er1/` |
| Patched AudioFW | `ims/proprietary/app/sveservice/lib/arm/libAudioFWInterface.so` | `outputs/libAudioFWInterface.so` |

The two SVE compatibility modules are compiled from public source by the user's normal Android build; they are not copied from stock firmware.

## Final source gate

After staging, run the final verifier:

```sh
python3 tools/verify_crdroid_ims_implementation.py \
  --source-root <android-source-root> \
  --producer-work <work> \
  --compat-root <compat-checkout> \
  --report <work>/reports/final-integration-verification.json
```

It checks the forty IMS copy rows, device source properties, payload paths, native SVE Soong/JNI wiring including `libmedia_headers`, generated APK receipts, and transformed payloads. A pass establishes those source conditions only; the user's normal Android build, flash, and device testing remain separate.

## Scope outside this index

This index covers IMS integration only. A full crDroid Android source build still uses the ROM's normal manifest and may need the separately documented M11 display build fixes plus the WebView manifest entry and Git LFS APK inputs. Those are external build prerequisites, not entries in this IMS index. This route does not claim to recreate the complete ROM manifest or identify the exact flashed ZIP by hash.
