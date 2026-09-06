# Samsung Galaxy M11 IMS compatibility layer

Reproducible tooling and documentation for bringing Samsung's stock IMS stack
to Android 13 custom ROMs on the Galaxy M11 (`SM-M115F`, `m11q`).

## Status

This repository is an early **private engineering checkpoint**, not a release or
flashable package.

Confirmed on one device with CherishOS 4.12 / Android 13:

- SIM1 WWAN IMS registration;
- outgoing VoLTE establishment;
- clear two-way speech;
- local and remote teardown;
- SELinux Enforcing throughout the validated call.

Not yet claimed: incoming calls, SIM2/DSDS, VoWiFi, IMS emergency calls,
handover, other Samsung models, other stock builds, or general carrier support.

## Proprietary-file policy

This repository intentionally contains no Samsung APK, JAR, shared library,
daemon, firmware image, signing key, or decoded stock tree. Users must extract
the exact inputs locally from firmware they are entitled to use. Hash-pinned
tools then verify and transform those inputs.

Current validated stock reference:

```text
Device:  Samsung Galaxy M11 SM-M115F
CSC:     BRI
Build:   M115FXXS5CWK3
Android: 12
```

See [the public-release SOP](docs/PUBLIC_RELEASE_SOP.md) and the
[M11 payload manifest](devices/m11q/payload-manifest.tsv). Reproducible APK and
toolchain identities are centralized in
[`devices/m11q/imsservice-build.json`](devices/m11q/imsservice-build.json).
The historical patch material is being filtered through the conservative
[`docs/PATCH_PROVENANCE.md`](docs/PATCH_PROVENANCE.md) publication boundary.

## Tools currently available

- `tools/verify_payload.py` verifies the 13 declared stock inputs and can stage
  only the explicitly permitted payload categories.
- `tools/apk_entry_replace.py` rebuilds a ZIP/APK from a stock base while
  changing only explicitly allowed entries and removing only exact stale v1
  signature entries.
- `tools/verify_framework_abi.py` verifies the local Android 13
  `framework-minus-apex.jar` in exact golden-hash or ABI-compatible mode; see
  [the framework ABI guide](docs/FRAMEWORK_ABI.md).
- `tools/generate_compile_stubs.py` verifies allowlisted declarations in
  private local smali roots and emits disposable compile-only Java ABI stubs.
  It never copies implementations, fields or debug metadata.
- `tools/transform_bc1_manifest.py` performs the fail-closed, MMTEL-only BC1
  manifest transformation without embedding the surrounding stock XML; see
  [the BC1 manifest guide](docs/BC1_MANIFEST.md). The future outer orchestrator,
  not this XML tool, is responsible for stock APK and apktool hash pinning.
- `tools/transform_bc2_native_hooks.py` validates three exact private smali
  targets and emits a three-file overlay containing only the BC2 bridge hooks.
  It never edits or copies the decoded tree; see
  [the BC2 native-hook guide](docs/BC2_NATIVE_HOOKS.md).
- `tools/transform_bg1_stats_guard.py` validates the two exact CWK3 statistics
  classes and emits a two-file overlay that degrades unavailable optional video
  accounting without fabricating a zero-byte result; see
  [the BG1 statistics guide](docs/BG1_STATS_GUARD.md).
- Synthetic unit tests contain no Samsung code or binaries.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

## Work still required before a release

- Consolidate the implemented BC1, BC2 and BG1 transformations into one
  relocatable clean-stock-to-final APK builder.
- Verify the new ZIP-preserving package from a fresh firmware extraction.
- Build and flash a ROM manually, then repeat the runtime acceptance tests.
- Review provenance of stock-derived text configuration and framework
  compatibility source before publication.
- Add a licence for project-authored work after the provenance boundary is
  finalized.

No ROM build is performed by the tools in this repository.
