# Samsung M115F IMS compatibility layer — public release SOP

Status: **published source-only compatibility layer**. The seven
project-authored bridge Java sources and fail-closed transformations are
published under Apache-2.0. Samsung payloads and generated private outputs
remain excluded. BT1 passed its complete source and non-ROM validation on
2026-09-26. On 2026-09-27, SV1 and EC1 each passed two deterministic clean
rebuilds from exact stock APKs, closing the last saved-final-payload
dependencies for `sveservice.apk` and `EpdgService.apk`.

This is not legal advice.  The conservative project policy is that Samsung APK,
JAR, ELF and executable files are supplied by the user from firmware they are
entitled to use; the public repository contains only project-authored source,
patches, manifests, hash gates, integration code and documentation.

## 1. Validated scope

Known-good device/firmware baseline:

- Device: Samsung Galaxy M11 `SM-M115F`.
- Region/CSC used for the golden reference: `BRI`.
- Stock build: `M115FXXS5CWK3`, Android 12.
- AP archive contains `super.img.lz4`.
- Extracted `system.img` SHA-256:
  `9136dc82d36367b09ff373af3b1adbfa75cedd1bf06f8648bf82069bc6f21b8d`.
- Target validated so far: CherishOS 4.12 / Android 13.
- Confirmed WWAN function with one active subscription at a time: SIM1 and
  SIM2 IMS registration, outgoing and incoming VoLTE with clear two-way speech
  and teardown, and SMS send/receive. Physical SIM1 hot-swap recovery was also
  validated under SELinux Enforcing.
- Confirmed Stage 3 function on the tested M11/Taiwan Mobile setup: outgoing
  VoWiFi to 188 with audible service audio and normal teardown, plus incoming
  VoWiFi from another handset with sustained bidirectional audio after BT1.
- Historical Stage 1 source checkpoints were compatibility layer `8a3dc34`,
  device tree `510d965`, Telephony `afedb3add`, and ROM pre-release
  `20260910-13-rc1`. Current behavior and reproducible output identities are
  recorded in `README.md`, `docs/IMS_APK_BUILDER.md`, and
  `docs/STAGE3_MT_VOWIFI_MEDIA.md` rather than inferred from those old commits.
- Selected candidate: BQ3 IMS bridge plus BQ6 generic Telephony fallback.
  BQ7 is excluded. A prior cold-boot failure was attributed to dirty `/data`
  persistent-state contamination; the exact contaminating item was not
  isolated.

Do not generalize the validated single-active SIM2 result to concurrent DSDS,
or the tested Taiwan Mobile VoWiFi result to general carrier support. Pure
IMS-SMS delivery, IMS emergency calling, ViLTE, handover, alternate audio
routes, other Samsung devices and other stock builds remain unverified.

## 2. What the public repository may contain

Publishable project material:

- Device integration, init definitions, SELinux policy and Android overlays.
- Android framework compatibility source/patches.
- Project-authored modern `ImsService`/MmTel bridge source.
- Ordered smali patches which describe the required transformation.
- Extraction, assembly and structural-verification scripts.
- File paths, sizes, SHA-256 values and ABI/behavior documentation.
- Tests and redacted runtime evidence.
- An Apache-2.0 or otherwise selected licence covering only project-authored
  work.

Keep out of the public repository:

- Stock or patched `imsservice.apk`.
- Samsung `*.jar`, `*.so`, `imsd` and `multiclientd` payloads.
- Full firmware, partition images and decoded stock smali trees.
- ROM platform private keys or any other signing key.
- Build outputs, backups and intermediate APKs.
- Runtime captures containing IMSI, MSISDN, SIP identities, IP addresses or
  other subscriber/carrier secrets unless reviewed and redacted.

Stock-derived configuration remains a local firmware input and is not included
in this repository. Do not assume that text is automatically redistributable.

The seven bridge Java implementations are project-authored compatibility code,
not decompiled Samsung sources. A technical audit found no Samsung implementation
bodies or decompiler markers. Their package names and Samsung-private method
signatures exist only for interoperability. Exact source hashes and provenance
are recorded in `docs/BRIDGE_SOURCE_PROVENANCE.md` and enforced by the builder.

## 3. Current public repository layout

```text
Samsung-m11-ims-compat-layer/
  README.md
  LICENSE
  bridge/java/
  bridge/abi/
  devices/m11q/
    payload-manifest.tsv
    *-contract.json
  patches/
  tools/
  tests/
  docs/
```

Device-tree packaging, init, SELinux and overlay integration live in the
separate public M11 device-tree repository, not under this compatibility-layer
checkout. This repository does not currently contain a universal Android
source patch runner, a complete firmware-image extractor, or a one-command
ROM build wrapper. See
[`M11_ANDROID13_ROM_BRINGUP.md`](M11_ANDROID13_ROM_BRINGUP.md) for the current
end-to-end boundary and manual hand-off between repositories.

Recommended `.gitignore` minimum:

```gitignore
/proprietary/
/out/
/build-inputs/
/**/*.apk
/**/*.jar
/**/*.so
/**/*.img
/**/*.bin
/**/*.tar
/**/*.tar.md5
/**/*.lz4
/**/*.pk8
/**/*.pem
/**/*.orig
```

If a project-authored test fixture legitimately uses one of these extensions,
add it back with a narrow `!path/to/file` exception after review.

## 4. Obtain and identify the stock input

The user obtains the exact Samsung firmware independently.  The script must not
download firmware or silently accept a nearby build.

Example local inputs:

```text
AP_M115FXXS5CWK3_...tar.md5
```

Record at least:

```text
model=SM-M115F
build=M115FXXS5CWK3
android=12
csc=BRI
AP archive SHA-256=<locally calculated>
```

The public tool must stop on model/build mismatch.  Supporting another CSC or
firmware revision is a new porting input, not a warning that may be ignored.

## 5. Extract `system.img` without modifying it

Reference Linux/WSL sequence:

```bash
mkdir -p work/ap work/super work/partitions
tar -xf "/path/to/AP_M115FXXS5CWK3_...tar.md5" -C work/ap super.img.lz4
lz4 -d work/ap/super.img.lz4 work/super/super.sparse.img
simg2img work/super/super.sparse.img work/super/super.raw.img
python3 /path/to/lpunpack.py -p system work/super/super.raw.img work/partitions
sha256sum work/partitions/system.img
```

Expected `system.img` SHA-256 is the value in section 1.  Stop if it differs.
In the original bring-up, `lpunpack.py` was the local
`stock_analysis/lpunpack.py` helper. It is not present at `tools/lpunpack.py`
in this public repository; substitute the local helper's actual path or a
compatible `lpunpack` implementation. Record its source/version and hash before
calling the extraction workflow reproducible. The image hashes from the
successful CWK3 extraction are in
[`FRESH_EXTRACTION_VALIDATION.md`](FRESH_EXTRACTION_VALIDATION.md).

## 6. Extract and verify the payload locally

The repository pins the expected files in
[`devices/m11q/payload-manifest.tsv`](../devices/m11q/payload-manifest.tsv),
but does not package the local ext4 file extractor used during bring-up. That
run used `stock_analysis/extract_ext4.py`, which accepts an image, output
directory and explicit `/system/...` paths; it depends on a local Python
`ext4` module and is not in this repository. The exact payload path list is the
manifest's `stock_path` column. From the repository root, the original
manifest-driven invocation is:

```bash
mapfile -t STOCK_PATHS < <(awk -F '\t' 'NR > 1 && $1 ~ /^\/system\// { print $1 }' \
  devices/m11q/payload-manifest.tsv)
python3 /path/to/extract_ext4.py \
  work/partitions/system.img \
  /path/to/private/m11q-cwk3-extracted \
  "${STOCK_PATHS[@]}"
```

The output directory must preserve the `system/...` path prefix expected by
the verifier. This records the original extraction method; the external
`lpunpack.py`, `extract_ext4.py`, and Python `ext4` dependency still need to be
obtained and version-pinned by the builder. The successful historical hashes
are in [`FRESH_EXTRACTION_VALIDATION.md`](FRESH_EXTRACTION_VALIDATION.md).

From the repository root, the public verifier can check all manifest inputs,
copy only rows marked `copy` to the device tree, and stage transformation/build
inputs in a private directory. Substitute local paths and keep the report and
private staging directory outside Git:

```bash
python3 tools/verify_payload.py \
  /path/to/extracted/system \
  /path/to/android/device/samsung/m11q \
  --copy \
  --stock-input-dir /path/to/private/m11q-cwk3-inputs \
  --report /path/to/private/reports/m11q-payload-verification.json
```

A successful report must show every manifest row as `verified`. `--copy` only
places unchanged `copy` rows under the device-tree root; it does not install
transformed outputs. `patch-to-stage1`, `transform-input`, and `build-input`
rows are staged as private builder inputs. The per-row action and output
destination are authoritative; follow
[`STAGE3_PAYLOAD_INPUTS.md`](STAGE3_PAYLOAD_INPUTS.md) before creating the
transformed APKs, libraries, or ABI stub. Never commit stock inputs, generated
outputs, or reports containing private paths.

## 7. Rebuild the IMS APK from stock

The public design follows the useful parts of
[`myesxc/Samsung-s20-ims-compat-layer`](https://github.com/myesxc/Samsung-s20-ims-compat-layer),
adapted and independently validated for the Galaxy M11:

1. Pin the exact stock APK input.
2. Decode into a private temporary directory.
3. Apply complete ordered patches; never patch a stale working directory.
4. Compile project-authored bridge Java against the selected Android framework.
5. Inject the generated DEX while preserving all required stock APK entries.
6. Rebuild, zipalign and structurally verify.
7. Leave the APK unsigned for an Android ROM source build, because the ROM's
   `LOCAL_CERTIFICATE := platform` signs it with that build's platform key.
8. Never distribute a platform private key.

The validated M11 chain is currently:

```text
stock CWK3 APK
  490e600fa7a8b111de83da6d20d87607f8db68b8447c98cacd2313055fd47f91
    │ Stage1BC1: modern service discovery/manifest baseline
    ▼
  1ee5307ddbb1b9d7f1fad12da19be711a32078dadf606beac4f3a1256b961b5e
    │ Stage1BC2: modern SIM1 registration/capability/call bridge
    ▼
  087c5ffbd86ecf002627e0e1c9055688e68e3b5c7e6e73a96ccf9a2538ad6414
    │ Stage1BG1: optional network-statistics compatibility guard
    ▼
  23bff0e7b91a55d206adf5bf2ff8fb277f0d5143a21b63fc05b9afe842a4124c
```

Final validated DEX identities before ROM signing:

```text
classes.dex  ab5b0fa1e3f244660d0ea6b287856409065381c78f9a682c4d03be5a15c8353c
classes2.dex c47750fb400ed9a4dca45490c9f4f5937bf99fa2d9e47b167866f46b7025a738
```

The whole APK hash is a useful exact-toolchain checkpoint, but the final public
verifier must prioritize structure and DEX identities because ZIP metadata,
compression and ROM signing can change the whole-file hash.

### Historical packaging caveat

The `23bff0e7...` APK is the confirmed on-device Stage 1 runtime reference, but
an entry-level comparison found that the historical BC1 apktool rebuild also
rewrote `resources.arsc` and several resource XML files, removed nine
non-signature `META-INF/maven/...` entries, and changed one WebP entry path.
Those collateral differences were not intended compatibility changes.

Therefore `23bff0e7...` remains historical evidence, not the expected whole-file
hash of the public builder.  The public packer must use the stock ZIP as its
base and import only the rebuilt `AndroidManifest.xml` and DEX entries.  It may
remove only the exact stale signature entries:

```text
META-INF/CERT.RSA
META-INF/CERT.SF
META-INF/MANIFEST.MF
```

All other `META-INF`, resource and asset entries must remain byte-for-byte
present.  A newly packaged APK must receive a new runtime validation before it
becomes the public golden baseline, even if its final DEX hashes match the
historical candidate.

Current source records for consolidation:

```text
work/stage1bc1_discovery/
  0002-imsservice-modern-mmtel-discovery.patch
  rebuild_and_apply.sh
work/stage1bc2_bridge/
  src/
  compile-only/
  generate_adapters.py
  native-hooks.patch
  patch_native.py
  pack_dex.py
  verify_candidate.py
work/stage1bg_stats_guard/
  stats-guard.patch
  patch_stats.py
  pack_candidate.py
  verify_candidate.py
```

Those historical scripts proved the individual stages locally, but contain
absolute paths and depend on intermediate artifacts. The repository now
consolidates their behavior into `tools/build_imsservice.py`; see
`docs/IMS_APK_BUILDER.md`. Its interface is:

When reviewed bridge source changes invalidate the final DEX/APK pins, mark the
config `needs-promotion` and run the explicit `candidate-invariants` mode twice.
That mode performs all non-pin gates and publishes only a `PIN_DISCOVERY` JSON
report; it never publishes an APK or edits the config. After identical observed
hashes are reviewed, manually promote all final hashes plus `pin_state` and
`pin_basis`, then use the default strict mode to rebuild and atomically publish
the exactly pinned unsigned APK. Only that strict artifact may proceed to the
manual ROM build and runtime-validation stages. Strict `PASS` is a build and
structure result, not evidence of device behavior.

The strict interface is:

```bash
tools/build_imsservice.py \
  --stock-apk proprietary/system/priv-app/imsservice/imsservice.apk \
  --framework-res-apk build-inputs/framework-res.apk \
  --imsmanager-jar proprietary/system/framework/imsmanager.jar \
  ... \
  --output out/imsservice.apk \
  --report out/imsservice-report.json
```

That command must reproduce the complete behavior from the clean stock hash in
one invocation, not require the BC1 or BC2 intermediate APK to be supplied by
the user.

## 8. Verify the generated APK

Minimum hard failures:

- Input APK hash is not the exact CWK3 stock hash.
- Required DEX is missing, duplicated or unexpectedly changed.
- Modern service manifest action, permission or MMTEL metadata is absent.
- Bridge classes or native hook targets are absent.
- Project compile-only Samsung stubs leaked into the output APK.
- Generated compile-only ABI stubs or their reports were committed, or any
  generated stub class entered either candidate DEX.
- APK ZIP integrity or alignment check fails.
- A patch applies with fuzz, rejected hunks or already-applied state.
- An undeclared APK entry changes relative to the expected transformation.

The verifier should emit a machine-readable report containing input hashes,
tool versions, applied patch IDs, DEX hashes, changed-entry inventory and final
structural results.  A signed APK may have a different whole-file hash; verify
its DEX and manifest contents independently after signing.

## 9. Integrate the payload and Android source

There is not yet a public preparation script that applies all device and
framework changes to a clean ROM checkout. The device-tree repository provides
the integration fragments and `ims/verify_payload.ps1`; use its README to
install the `ims` directory, review the `device.mk` / `BoardConfig.mk`
fragments, and verify the completed payload before building. The public device
tree update [`9aebafe`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/9aebafee57492a75cadd115ae80ea21db378a760) fixes the verifier's expected
BT1 APK hash and documents how to generate that APK.
The later device-tree commit
[`d11cbe58`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/d11cbe58dfdf81c284788c50e5b6e37de47cf5d4)
adds the stable IWLAN-to-EUTRAN fresh-bearer policy for PLMNs 46601, 46605,
46692, and 46697. TWM runtime validation is confirmed on 46697 only; turning
Wi-Fi off during an active VoWiFi call intentionally disconnects it.

Public Android source references and the manually restored crDroid baseline
are recorded in
[`CRDROID_ANDROID13_IMS_RESTORATION.md`](CRDROID_ANDROID13_IMS_RESTORATION.md).
That record is currently a source map and port review, not a ready-to-apply
patch bundle. A clean ROM checkout still requires a maintainer to port those
changes to its exact source revisions and review framework/build-context
differences. Do not infer that the Android forks' branches can be dropped into
an unrelated ROM manifest unchanged.

The source checkpoints checked on 2026-09-29 are:

```text
device/samsung/m11q: functional integration through 97206c0e; verifier/docs update 9aebafe; handover policy d11cbe58
frameworks/base:      e9346dd4 + 15a303b8 + 73178bfc (CherishOS fork)
frameworks/opt/net/ims: 1b1a3226 (CherishOS fork)
frameworks/opt/telephony: 6c209a7d (CherishOS fork)
packages/services/Telephony: cf338879 + afedb3ad + 26d0551a (CherishOS fork)
system/netd:           8e455b91 (CherishOS fork)
```

These are source references rather than one universal ROM baseline. For the
crDroid 13 port, the nine known runtime patch groups were found in the local
source trees, with documented context adaptations. The same static check does
not establish that an arbitrary ROM has those changes or that its VoWiFi media
path works. The step-by-step scope and remaining gaps are in
[`M11_ANDROID13_ROM_BRINGUP.md`](M11_ANDROID13_ROM_BRINGUP.md).

## 10. Builder responsibility

The user builds the ROM normally.  This compatibility project does not need and
must not ship platform keys.  For an in-tree Android build, the generated
`imsservice.apk` is an unsigned input and the target ROM build applies its own
platform signature.

After building, verify the APK extracted from the ROM or device:

- package is privileged and platform-signed for that ROM;
- DEX identities/bridge structure match the generated candidate;
- expected SELinux domains and services are present;
- no proprietary payload entered Git history.

## 11. Runtime acceptance gates

Publish results as separate facts:

```text
registration -> outgoing signaling -> bearer -> audio -> teardown
             -> incoming ringing/answer/audio/teardown
```

For the current M11 Stage 1, both outgoing and incoming branches are complete,
including incoming ringing, answer, bidirectional speech and teardown. Carrier
availability must not be presented as a universal hard-coded Taiwan setting.

Required issue template fields for other testers:

- exact model, CSC and firmware build;
- ROM name, Android version and source revisions;
- SIM slot and carrier;
- payload verifier report;
- SELinux enforcing state;
- redacted boot/registration/call logs;
- precise result stage, without treating `ril.lte.voice.status=0` alone as a
  failure (stock VoLTE was proven working with that value).

## 12. Release gate

Do not tag a public release until all of these are true:

- clean-room run starts from exact CWK3 firmware and an empty output directory;
- all stock inputs pass `PAYLOAD_MANIFEST.tsv`;
- the documented builders regenerate every transformed APK without historical
  patched/final binary inputs;
- structural checks and source-extracted unit tests pass;
- a manually built/flashed ROM made from those exact generated inputs repeats
  the confirmed outgoing and incoming two-way calls under Enforcing;
- A full Git-history scan—not only `git status`—finds no Samsung binaries,
  firmware, decoded trees or keys;
- README clearly limits runtime claims to the tested single-active-subscription
  VoLTE/SMS scope and the tested Taiwan Mobile VoWiFi calls.

## 13. Confirmed, recommended and pending

Confirmed:

- The 47 current payload identities and the historical three-stage IMS APK
  hash chain.
- The Stage 1BQ3/BQ6 candidate passed real-party SIM1 outgoing and incoming
  calls under Enforcing, including incoming ringing, answer, bidirectional
  speech and teardown, plus SMS send/receive and post-hot-swap recovery.
- Device/framework source checkpoints exist locally without the proprietary
  payload being committed.
- SV1 and EC1 rebuild their Stage 3 APKs from exact stock inputs without a
  saved decoded tree, patched DEX, or final APK. The clean unsigned outputs are
  deterministic and structurally match the runtime-validated implementations;
  those newly repacked files have not yet been separately flashed.

Recommended design:

- Use exact input hash gates, ordered patches, private temporary decode trees,
  structural verification and locally generated proprietary output, similar to
  the staged design documented by
  [`myesxc/Samsung-s20-ims-compat-layer`](https://github.com/myesxc/Samsung-s20-ims-compat-layer).
- Be more conservative than that reference repository by not publishing the
  Samsung prebuilt payload itself.

Remaining reproducibility work:

- Package and validate the firmware image extraction workflow from a clean
  checkout, or document a supported external extractor and its exact inputs.
- Export the reviewed Android source ports as ordered per-repository patches
  with baseline checks and an apply/preflight command that fails before making
  partial changes.
- Carry the published crDroid Telecom and m11q incoming-media commits in the
  clean-checkout patch workflow, and test the carrier policy on each listed
  PLMN before claiming broader cross-ROM/carrier support.

## 14. Cross-ROM IMS port acceptance

The CherishOS 4.12 runtime results are a historical baseline. For each new ROM
target, record its exact Android/framework revisions and keep shared Samsung
IMS API shims separate from ROM-specific build, product, SELinux, and carrier
configuration.

Before claiming the port works on that ROM:

- apply the ordered source-only patch set to a clean checkout of the recorded
  baseline and review every context adaptation;
- build and boot that ROM on the target device;
- verify the Samsung IMS process stays alive and registration completes;
- validate outgoing and incoming VoLTE through audio and teardown under
  Enforcing;
- validate SMS and hot-swap behavior separately from voice;
- for VoWiFi, verify ePDG service startup, tunnel interface creation, traffic
  rules, IMS IWLAN registration, call audio, and clean teardown;
- record unsupported Samsung APIs and any carrier/SIM-specific limits rather
  than treating compatibility stubs as full platform implementations.

The crDroid 13 restoration has partial user-built/flashed results. Direct LTE
calling and a fresh WWAN IMS setup after airplane-mode reset succeeded. The
call-state cleanup now clears the Dialer after a failed call, but does not
change the carrier SIP 487. On the validated Taiwan Mobile PLMN, the M11
CarrierConfig overlay change in
[`d11cbe58`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/d11cbe58dfdf81c284788c50e5b6e37de47cf5d4)
disallows idle IWLAN-to-EUTRAN IMS handover and forces a fresh WWAN bearer;
turning Wi-Fi off during an active VoWiFi call disconnects that call.
Incoming VoWiFi media is now validated on the tested crDroid build with the
same BT1 APK plus the m11q-gated post-`MODE_IN_CALL` Telecom callback. See the
restoration record and
[`M11_ANDROID13_ROM_BRINGUP.md`](M11_ANDROID13_ROM_BRINGUP.md) for the evidence,
limitations, and practical port boundary.

The repository includes `LICENSE`, which covers only project-authored source,
tooling, tests, contracts, ABI fixtures and documentation. It does not license
Samsung firmware, APK/JAR/SO/ELF files, decoded stock material, carrier inputs
or any other third-party payload.
