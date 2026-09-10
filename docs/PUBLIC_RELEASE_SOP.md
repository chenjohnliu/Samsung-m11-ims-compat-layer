# Samsung M115F IMS compatibility layer — public release SOP

Status: **source-only publication prepared; public visibility is still gated**.
The Stage 1 runtime baseline is verified, but a clean public checkout cannot
currently regenerate the complete APK because the seven bridge Java sources
remain restricted inputs. A fresh firmware extraction has also not been run in
this checkout. Do not represent the repository as fully reproducible until
both gates are closed.

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
- Confirmed function: SIM1 WWAN IMS registration, outgoing and incoming VoLTE
  establishment, incoming ringing/answer, clear two-way speech and teardown,
  SMS send/receive, and physical SIM1 hot-swap recovery followed by VoLTE and
  SMS operation under SELinux Enforcing.
- Verified source checkpoints: compatibility layer `8a3dc34`, device tree
  `510d965`, Telephony `afedb3add`, and ROM pre-release `20260910-13-rc1`.
- Selected candidate: BQ3 IMS bridge plus BQ6 generic Telephony fallback.
  BQ7 is excluded. A prior cold-boot failure was attributed to dirty `/data`
  persistent-state contamination; the exact contaminating item was not
  isolated.

Do not describe SIM2/DSDS, pure IMS-SMS delivery, VoWiFi, IMS emergency calling, ViLTE,
handover, other Samsung devices, other stock builds or general carrier support
as working until each is tested separately. SIM2 currently exposes no
VoLTE/MMTEL support flag; this remains a SIM1-only claim.

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

The current `config/cscfeature.xml`, `config/floating_feature.xml` and
`config/customer_carrier_feature.json` are stock-derived inputs.  Before public
release, either extract them locally as firmware inputs or replace them with a
reviewed minimal project-authored configuration.  Do not assume that being text
rather than an ELF makes redistribution automatically safe.

Likewise, framework compatibility `.java` files need a provenance review. Only
clean-room/project-authored implementations should be offered under the
project's licence; a Java filename or source representation is not by itself
proof of redistributability. The current public checkout deliberately omits
all seven bridge Java implementations. Their names and hashes are an inventory
and verification boundary, not a licence grant. A restricted local bridge
bundle must be supplied separately and must match
`devices/m11q/imsservice-build.json` before the builder may run.

The public checkout can therefore reproduce the declaration-only ABI checks,
fail-closed transformation logic and synthetic tests, but not the complete APK
until that bridge bundle is lawfully publishable or a clean-room replacement is
created and independently reviewed. Never substitute Samsung-decompiled code
or a stock payload to make the public checkout appear complete.

## 3. Proposed public repository layout

```text
Samsung-QCOM-IMS-Compat/
  README.md
  LICENSE
  docs/
    M115F_STAGE1.md
    ARCHITECTURE.md
    PORTING_GUIDE.md
    RUNTIME_VALIDATION.md
  devices/m11q/
    payload-manifest.tsv
    integration/
    init/
    permissions/
    sepolicy/
    overlay/
    patches/frameworks-base/
    patches/device-tree/
    patches/imsservice/
  bridge/
    java/
    tests/
  tools/
    extract-firmware.sh
    patch-imsservice.sh
    verify-input.sh
    verify-output.sh
    prepare-device-tree.sh
  proprietary/                 # generated locally; gitignored
  out/                         # generated locally; gitignored
```

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
python3 tools/lpunpack.py -p system work/super/super.raw.img work/partitions
sha256sum work/partitions/system.img
```

Expected `system.img` SHA-256 is the value in section 1.  Stop if it differs.
Tool versions and their own hashes must be documented in the final public
`tools/README.md`.  The exact command above is a reference derived from the
current local extraction method; the public wrapper still requires a clean
end-to-end verification run.

## 6. Extract the payload locally

Extract only paths declared in `PAYLOAD_MANIFEST.tsv`.  The current research
workspace has a local `stock_analysis/extract_ext4.py` helper which supports an
explicit path list.  The example below describes the planned public
`tools/extract_ext4.py`; that public helper has not yet been packaged or tested
from a clean checkout:

```bash
python3 tools/extract_ext4.py \
  work/partitions/system.img proprietary \
  /system/bin/imsd \
  /system/bin/multiclientd \
  /system/framework/EpdgManager.jar \
  /system/framework/imsmanager.jar \
  /system/framework/framework-res.apk \
  /system/framework/rcsopenapi.jar \
  /system/framework/vsimmanager.jar \
  /system/lib/libaresdns.so \
  /system/lib/libcurl2.so \
  /system/lib/libext2_uuid.so \
  /system/lib/libsec-ims.so \
  /system/lib/vendor.samsung.hardware.radio.bridge@2.0.so \
  /system/lib/vendor.samsung.hardware.radio.bridge@2.1.so \
  /system/priv-app/imsservice/imsservice.apk
```

The release wrapper should then copy each file into the device-tree destination
specified by the manifest.  It must verify every stock SHA-256 before applying
any transformation.

## 7. Rebuild the IMS APK from stock

The public design should follow the useful part of the S20 project:

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

## 9. Place payload into the Android tree

The preparation script should copy verified local inputs into:

```text
device/samsung/m11q/ims/proprietary/
```

and apply the published integration/framework patches.  It must refuse to:

- overwrite a non-matching APK or source file;
- apply to an unsupported branch;
- copy signing keys;
- enable global permissive SELinux;
- change SIM2, VoWiFi or emergency behavior implicitly.

Known local source checkpoints:

```text
device/samsung/m11q: 4ada41f + 566bfd4 on m11q-volte-stage1
frameworks/base:      e9346dd40f60 on m11q-volte-stage1
```

These are local checkpoint identities, not public remote references.  Export
reviewable patches or recreate clean commits in the eventual public repo.

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
- a single command regenerates the final APK without historical binary inputs;
- structural checks and source-extracted unit tests pass;
- a manually built/flashed ROM made from those exact generated inputs repeats
  the confirmed outgoing and incoming two-way calls under Enforcing;
- A full Git-history scan—not only `git status`—finds no Samsung binaries,
  firmware, decoded trees or keys;
- README clearly limits the validated runtime claim to the actually tested
  SIM1 WWAN configuration.

## 13. Confirmed, recommended and pending

Confirmed:

- The 14 current payload identities and the historical three-stage APK hash
  chain.
- The Stage 1BQ3/BQ6 candidate passed real-party SIM1 outgoing and incoming
  calls under Enforcing, including incoming ringing, answer, bidirectional
  speech and teardown, plus SMS send/receive and post-hot-swap recovery.
- Device/framework source checkpoints exist locally without the proprietary
  payload being committed.

Recommended design:

- Use exact input hash gates, ordered patches, private temporary decode trees,
  structural verification and locally generated proprietary output, similar to
  the staged design documented by the S20 project.
- Be more conservative than the current S20 repository by not publishing the
  Samsung prebuilt payload itself.

Pending before changing GitHub visibility to public:

- Exercise the current 14-file `verify_payload.py` against a fresh firmware
  extraction and keep stock-input hashes separate from patched-output hashes.
- Re-run the complete pipeline from a fresh CWK3 extraction.
- Finalize the provenance/licence record for all seven bridge sources, or
  publish a reviewed clean-room replacement. Until then the bridge remains a
  restricted input and the complete APK is not publicly reproducible.
- Confirm that any stock-derived configuration is extracted locally rather than
  redistributed, or replace it with reviewed project-authored configuration.
- Confirm the full-history audit again immediately before visibility change.

The repository includes `LICENSE`, which covers only project-authored source,
tooling, tests, contracts, ABI fixtures and documentation. It does not license
Samsung firmware, APK/JAR/SO/ELF files, decoded stock material, carrier inputs
or any other third-party payload.
