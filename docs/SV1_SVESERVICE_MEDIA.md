# SV1 SVE media APK reconstruction

SV1 closes the public `sveservice.apk` reproducibility gap. It consumes only
the exact M115F CWK3 stock APK pinned in the public manifest and produces the
unsigned Android 13-compatible APK without using a saved patched APK, DEX, or
decoded tree.

## Authored changes

The fail-closed transform makes three narrow changes:

1. load the project-authored media compatibility library before Samsung's SVE
   JNI library;
2. retain the entry/return diagnostic around SAE channel creation; and
3. retain the entry/return diagnostic around SAE channel start, including the
   required local-register expansion.

The contract pins the stock APK and DEX, both touched class files, each touched
method before and after transformation, occurrence counts, ordering, and final
invariants. The transformer rejects an unknown class, superclass, method,
anchor, hash, partially patched tree, or repeated application. It also verifies
that every method outside the three named methods is byte-identical.

The media compatibility library itself is a separate, project-authored native
component. SV1 does not replace, remove, or rebuild that component; it makes the
APK-side loader and retained diagnostics reproducible.

## Build

Supply apktool 2.9.3 and an independently obtained stock CWK3 APK matching the
published hash. The deterministic validation runs used OpenJDK 11.0.32.1; the
builder's final DEX/APK pins reject output drift from another Java runtime:

```text
python tools/build_sveservice.py \
  --stock-apk /private/input/sveservice.apk \
  --apktool-jar /private/tools/apktool_2.9.3.jar \
  --output-apk /private/output/sveservice-unsigned.apk \
  --report /private/output/sveservice-report.json
```

The builder:

- verifies the APK, every stock ZIP entry, and apktool before decoding;
- creates all decoded and rebuilt material in a disposable private directory;
- invokes the SV1 transformer and verifies its target/method output hashes;
- extracts only the rebuilt `classes.dex`;
- replaces only `classes.dex` in the original stock ZIP;
- removes only the three exact v1 signature entries; and
- re-decodes the output, checks structural invariants, and verifies that every
  unrelated ZIP entry remains byte-identical.

The deterministic unsigned output pins are public. Platform signing remains a
downstream ROM integration step and is intentionally outside this builder.

## Runtime reference equivalence

The preserved runtime-validated APK came from the historical iterative apktool
workflow, so it is not byte-identical to the clean reconstruction. Its DEX
layout/debug encoding and APK packaging history differ, and it did not preserve
the original ZIP entry set.

The closure check decoded the exact stock and runtime-reference APKs, applied
only the two touched class outputs to a clean stock tree, and rebuilt both trees
with the pinned apktool. Both routes produced the same deterministic DEX. The
two touched class files and all three touched methods also match the runtime
reference hashes exactly. The clean builder deliberately preserves the stock
manifest, resources, native entries, vendor metadata, ZIP metadata, and comment;
only the DEX and invalidated v1 signatures differ.

No Samsung APK, DEX, decoded smali, raw implementation diff, signing material,
or private filesystem path belongs in this repository.
