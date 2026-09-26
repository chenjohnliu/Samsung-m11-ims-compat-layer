# Remaining Stage 3 private payload status

Date: 2026-09-27

This audit compares pinned stock inputs, preserved runtime-validated outputs,
ZIP/ELF entry identities, decoded research trees, and retained preparation
scripts. It publishes only project-authored logic and metadata.

| Output | Status | Evidence and boundary |
| --- | --- | --- |
| `UnifiedWFC.apk` | Public UW1 transform | One exact DEX method is neutralized by a stock-hash and code-item-pinned direct transformer. |
| `liberis_strongswan.so` | Public ER1 transform | Two `DT_NEEDED` names move to the private namespace. |
| `liberc.so` / `libers.so` | Public ER1 transform | Exact private SONAME/dependency renames are reproducible; fresh source-build provenance remains unverified. |
| `sveservice.apk` | Blocked | The retained tree confirms a project loader insertion for `libm11q_sve_compat`, but the archived final DEX differs from the retained intermediate DEX. No retained procedure explains that final delta, so an exact public transformer would guess. |
| `EpdgService.apk` | Blocked | The archived output preserves all ZIP entries except `classes.dex`, but its DEX accumulates setting synchronization, CID fallback, and interface configuration edits across several rebuilt intermediates. The exact stock-to-final ordered transformation and deterministic final DEX pin were not retained as a single reviewed procedure. |

The blocked classification does not mean the files may be uploaded instead.
Their private final APKs and decoded trees remain proprietary reference data.
To unblock either APK, recover or independently re-derive the complete ordered
source edits from the exact stock APK, build twice with a pinned toolchain,
verify identical DEX/APK identities, and validate the generated candidate on
device. A raw smali diff or copied final `classes.dex` is not an acceptable
public substitute.

The SVE native compatibility source and `libAudioFWInterface.so` import patch
are project-authored but form a broader build closure than the six files in
this audit. They should be published only together with a reviewed Android
source build description and synthetic ABI tests; their existence does not
make the unexplained final `sveservice.apk` DEX reproducible.
