# ER1 ERIS private crypto namespace

## Outcome

`tools/transform_eris_private_crypto.py` reproduces the three native outputs
that isolate ERIS from Android 13's platform BoringSSL ABI:

| Pinned input | Generated output | ELF change |
| --- | --- | --- |
| `libcrypto.so` | `liberc.so` | `DT_SONAME` renamed |
| `libssl.so` | `libers.so` | `DT_SONAME` and crypto `DT_NEEDED` renamed |
| `liberis_strongswan.so` | same filename | SSL and crypto `DT_NEEDED` renamed |

The transformation is length-preserving and changes only strings within each
ELF dynamic string table. It does not embed any library bytes. The contract
pins complete input/output SHA-256 values, ELF32/ARM identity, SONAME,
ordered dependencies, replacement occurrence counts, and exact output names.

## Use

Place the three legally obtained, hash-matching inputs in one private
directory, then run:

```bash
python tools/transform_eris_private_crypto.py \
  --contract devices/m11q/eris-private-crypto-contract.json \
  --input-dir /private/eris-input \
  --output-dir /private/eris-output \
  --report /private/eris-report.json
```

The two BoringSSL inputs are the exact Android 12 ARM32 build artifacts pinned
by the contract, not Samsung APK contents. Their source checkout/build
provenance was not retained, so the public workflow deliberately does not
claim that an arbitrary Android 12 `libcrypto.so` or `libssl.so` is compatible.
Only exact hash matches are accepted.

## Evidence classification

- **Confirmed:** reversible byte comparison identifies the private SONAME and
  dependency renames; the preserved stock ERIS input transforms to the exact
  runtime-validated output hash; reverse-and-forward validation reproduces all
  three archived outputs; output ELF identity and ordered dependencies match.
- **Inferred:** the pinned BoringSSL pair came from the target Android 12 build
  environment. The precise source revision/toolchain was not retained.
- **Unverified:** rebuilding that exact pair from a fresh source checkout and
  validating a newly generated ER1 closure on-device.
