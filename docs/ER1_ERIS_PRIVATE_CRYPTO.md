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

## CWK3 input comparison — 2026-10-10

The independent CherishOS handoff permits hash-matching raw CWK3 originals,
but not another custom ROM's checkout or generated outputs. To test whether
that exception closes ER1, the audit read the stock `system.img` with SHA-256
`9136dc82d36367b09ff373af3b1adbfa75cedd1bf06f8648bf82069bc6f21b8d`.
Read-only `debugfs` extraction of the two `/system/lib` files gave:

| File | Raw CWK3 SHA-256 | Required ER1 input SHA-256 |
| --- | --- | --- |
| `libcrypto.so` | `8f92b691991bb0841228cc67a05c079a46065c4d80a43144cb3be6fb4fdc4bc3` | `cf6dfdaf8a57730364e2be816c45d4fbdf1d3b196f5467e340e8c998d2631040` |
| `libssl.so` | `729df965c522f88554dd278118d8514852ecf5daf97973837fa06745b94bf3ea` | `d8eef149d87bab37c66ade6d39c3ff93d6f922dc0dd4a126a3d4cca08a3dc478` |

**Confirmed:** the checked raw CWK3 pair does not match ER1. This is not a
reason to relax the contract or copy libraries out of a forbidden build.
The transform is reproducible given its exact inputs; acquiring or rebuilding
those inputs from the permitted source set remains blocked. This audit did
not upload any extracted library or change any input/output pin.

Resolution requires identifying the lawful provenance of the exact pair, or
designing and validating a reproducible replacement from public source.
Replacing the pair or omitting ER1 is an ABI/runtime change, not a harmless
handoff cleanup, and cannot inherit the existing runtime acceptance.
