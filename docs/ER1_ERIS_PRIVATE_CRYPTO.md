# ER1 ERIS private crypto namespace

The strict default now uses the three ARM32 libraries from Samsung stock
`M115FXXS5CWK3`. Their acquisition provenance is the stock system image, rather
than the untraceable historical Android 12 build pair. The tool, canonical
contract, raw-input inventory and provenance record use the same hashes.

## Current stock inputs and outputs

The verified stock `system.img` SHA-256 is
`9136dc82d36367b09ff373af3b1adbfa75cedd1bf06f8648bf82069bc6f21b8d`.
Extract the three `/system/lib/` files read-only with `debugfs` from a legally
owned, hash-matching image. This identifies the binary source; it does not
claim Samsung's original source checkout or toolchain can be reconstructed.

| File | Raw stock SHA-256 | Output | Output SHA-256 |
| --- | --- | --- | --- |
| `libcrypto.so` | `8f92b691991bb0841228cc67a05c079a46065c4d80a43144cb3be6fb4fdc4bc3` | `liberc.so` | `11b1be41684274d65274c39e36d01c439d4cdd8f52ac096b49e32f892e36ca5f` |
| `libssl.so` | `729df965c522f88554dd278118d8514852ecf5daf97973837fa06745b94bf3ea` | `libers.so` | `a6257fbdab5dc5771ea93905bbf7375e4b1e2393b9aadcd20655d4b9fd2e149c` |
| `liberis_strongswan.so` | `38aecec124684f02afd5bea9a98f538913af7b3311d5eb7e62f34429b27bbe49` | `liberis_strongswan.so` | `61601e70a15056cb563cdb2cc8651303ffc2b8a1cd9c2fb1ca83fd64fea55dc3` |

See the [canonical contract](../devices/m11q/eris-private-crypto-contract.json)
and [stock provenance](../devices/m11q/eris-private-crypto-provenance.json).

## Reproduce privately

```sh
python3 tools/transform_eris_private_crypto.py \
  --contract devices/m11q/eris-private-crypto-contract.json \
  --input-dir /private/eris-input \
  --output-dir /private/eris-output \
  --report /private/eris-report.json
```

The output and report parents must already exist. The tool rejects mismatched
inputs and existing outputs. It changes only the length-preserving strings in
the ELF dynamic string tables: crypto/SSL SONAMEs become `liberc.so`/`libers.so`,
and SSL/strongSwan dependencies point to those private names. ELF32 ARM
identity, ordered dependencies, replacement counts and all output hashes
remain strict. Arbitrary Android 12 libraries are not accepted.

Copy the generated trio to the device tree's private `ims/proprietary/lib/arm`
staging directory. The device packaging installs them under `system_ext/lib`.
Check those three installed file hashes against the table; stock input hashes
must not be used as generated-output hashes.

## Acceptance and historical boundary

On 2026-10-12 the user reported a successful fresh CherishOS build, successful
boot after Format Data, and normal calls. The rebuilt product's three ER1
hashes match the promoted contract, and the strict stock transformation was
replayed successfully before publication. This satisfies the user's promotion
condition. It does not newly establish VoWiFi, ERIS/IPsec execution, SMS,
handover, SIM2 or emergency-call behavior. The acceptance is a user report,
not an agent-observed modem trace.

The [historical contract](../devices/m11q/eris-private-crypto-historical-contract.json)
retains the old inputs and outputs unchanged for comparison. That pair's
original acquisition provenance remains unknown; the rename operation was
reverse-derived from archived outputs. It is no longer the default or a
required rebuild input. The current tool rejects that historical contract.

No library bytes, stock image, transformed payload or private device capture
are distributed by this repository.
