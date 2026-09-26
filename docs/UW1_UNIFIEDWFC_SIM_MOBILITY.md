# UW1 UnifiedWFC SIM-mobility compatibility

## Outcome

`tools/transform_unifiedwfc_sim_mobility.py` applies the one confirmed
project change in the CWK3 `UnifiedWFC.apk` without publishing decoded Samsung
code. It verifies the complete stock APK and `classes.dex` hashes, resolves one
exact class/method/prototype in the DEX tables, verifies the complete code-item
shape and instruction hash, and replaces that method with `return false`.

The disabled method is Samsung's SIM-mobility extension gate. The ordinary
carrier path remains available; no carrier, MCC/MNC, IMSI, account, or forced
Wi-Fi Calling setting is embedded in the public transform.

This is intentionally a smaller output than the historical private APK. The
historical file was produced through a full decode/rebuild and therefore also
contains assembler normalization and removed metadata. UW1 changes only the
target method inside `classes.dex`, recalculates the DEX SHA-1 signature and
Adler-32 checksum, preserves all unrelated ZIP entries byte-for-byte, and
removes only the three standard APK v1 signature entries. The result must be
signed by the user's private ROM signing workflow.

## Use

```bash
python tools/transform_unifiedwfc_sim_mobility.py \
  --contract devices/m11q/unifiedwfc-sim-mobility-contract.json \
  --stock-apk /private/extract/system/app/UnifiedWFC/UnifiedWFC.apk \
  --output-apk /private/output/UnifiedWFC.apk \
  --report /private/output/UnifiedWFC.report.json
```

The report contains hashes and changed-entry metadata only. It contains no
input/output path, decoded implementation, device identifier, or signing data.
Hash drift, method ambiguity, code-item drift, partial/repeated application,
multidex input, unsafe files, and existing outputs all fail closed.

## Evidence classification

- **Confirmed:** exact CWK3 APK/DEX identity; the historical source edit makes
  the target method return false; the private final APK changed `classes.dex`;
  the direct DEX transform resolves exactly one method and passes against the
  preserved stock APK.
- **Inferred:** the historical decode/rebuild differences outside the method
  were tool normalization rather than required runtime behavior. UW1 avoids
  relying on that inference by not reproducing those differences.
- **Unverified:** a newly generated, re-signed UW1 APK has not yet been flashed
  independently of the runtime-validated historical Stage 3 image.
