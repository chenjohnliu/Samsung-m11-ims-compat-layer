# Stage 3 transformed payload status

Date: 2026-09-27

This audit compares pinned stock inputs, preserved runtime-validated outputs,
ZIP/ELF entry identities, decoded research trees, and retained preparation
scripts. It publishes only project-authored logic and metadata.

| Output | Status | Evidence and boundary |
| --- | --- | --- |
| `UnifiedWFC.apk` | Public UW1 transform | One exact DEX method is neutralized by a stock-hash and code-item-pinned direct transformer. |
| `liberis_strongswan.so` | Public ER1 transform | Two `DT_NEEDED` names move to the private namespace. |
| `liberc.so` / `libers.so` | Public ER1 transform | Exact private SONAME/dependency renames are reproducible; fresh source-build provenance remains unverified. |
| `sveservice.apk` | Public SV1 transform | The loader plus retained SAE diagnostics are rebuilt from exact stock. Two clean builds produced identical DEX/APK pins, target files and methods match the runtime reference, and all unrelated stock ZIP entries are preserved. |
| `EpdgService.apk` | Public EC1 transform | Seven reviewed Android 13 compatibility edits are rebuilt from the exact stock APK. The deterministic DEX/APK pins, final re-decode, unrelated-class checks, and stock ZIP-entry preservation are enforced without a saved patched/final payload. |

The two former APK gaps are closed at the source-reconstruction level. Private
final APKs and decoded trees remain proprietary reference data and are not
required by either builder. A raw smali diff or copied final `classes.dex` is
not an acceptable public substitute.

SV1 and EC1 produce clean deterministic DEX files that are not byte-identical
to the historical runtime APKs because those references accumulated different
apktool assembly histories. SV1 exactly reproduces the touched runtime class
and method hashes. EC1's final decoded class tree exactly matches the runtime
reference; its rebuilt DEX difference is therefore representation/layout, not
an additional class-level implementation delta. See `SV1_SVESERVICE_MEDIA.md`
and `EC1_EPDGSERVICE_ANDROID13_COMPAT.md`.

The reconstructed unsigned SV1 and EC1 APKs have not themselves been
platform-signed, flashed, and separately runtime-tested. Runtime confidence is
derived from exact structural equivalence to the implementations already
validated on device; a future ROM validation should record the fresh output
identities explicitly.
