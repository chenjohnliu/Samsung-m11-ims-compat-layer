# Fresh CWK3 extraction validation

On 2026-09-10 the Stage 1 source-only pipeline was rerun from a newly created
extraction directory. No previously extracted payload tree or historical
intermediate APK was used as an input.

## Extraction chain

The locally held `M115FXXS5CWK3` AP `super.img.lz4` was decompressed again,
converted from Android sparse format, and unpacked for the `system` dynamic
partition. Only the 14 paths declared in
`devices/m11q/payload-manifest.tsv` were then extracted.

Identity checkpoints:

```text
decompressed sparse super.img SHA-256
5416b7e351ff075aee6c04ad274bb040483f80d36d72d81d3fec5811aa761e92

fresh system.img SHA-256
9136dc82d36367b09ff373af3b1adbfa75cedd1bf06f8648bf82069bc6f21b8d
```

`tools/verify_payload.py` verified all 14 files against the public manifest:

```text
verified: 14
failed:    0
```

The JSON verifier report and extracted proprietary files remained in the
ignored local `out/` directory and were not committed because the report
contains local paths and the extracted files are Samsung proprietary inputs.

## Non-ROM rebuild

`tools/build_imsservice.py` was then run with the freshly extracted
`imsservice.apk`, `framework-res.apk`, and `imsmanager.jar`, the seven
hash-matching pre-BQ7 bridge sources, and the documented Android 13 toolchain.
No Android ROM build was run.

The complete builder passed and reproduced the recorded identities:

```text
status                 PASS
unsigned APK SHA-256   a9de2549bad19b3aeae3815e689b111384b81cc9dd59944a37e40fe1cda72d67
classes.dex SHA-256    a16a42ed01d284dc20efa57c67c6f18b6ffb20132367228b7e8a8c90f5eb90c6
classes2.dex SHA-256   5379c0688e2eaa48684d4d3ba7ff2cf570f7f28cca13d6d8934b0ebcad37d031
bridge JAR SHA-256     0189c5a32655d4d62390762fa66d28d939e1fcd0cf1e3f6e07229aa0d314b0cd
```

The framework input was classified `compatible-abi-only`, with SHA-256
`c0521a70c31fd722d9210dc39524b2c6500087ff92cc50bd6af58a3c1a639d2c`.
The builder still enforced the recorded Binder ABI fixtures and all manifest,
native-hook, statistics, SMS, source inventory, stub-leakage, ZIP preservation,
alignment, and final re-decode gates.

This closes the fresh-extraction/static-rebuild gate. Runtime claims remain
bound to the separately documented `20260910-13-rc1` device validation; this
run did not create or flash a ROM.
