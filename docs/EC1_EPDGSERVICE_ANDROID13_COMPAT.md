# EC1 EpdgService Android 13 compatibility closure

EC1 reconstructs the M11 ePDG compatibility changes from the exact CWK3
`EpdgService.apk`. No saved decoded tree, patched DEX, or final APK is an input.
The stock APK identity, stock DEX identity, seven target-class identities,
method inventory, output-class identities, deterministic rebuilt DEX, and
unsigned APK are all pinned.

The project-authored transform covers these reviewed behaviors:

- configure an existing ePDG interface instead of returning before address
  setup, and apply the IPv6 link address before enabling IPv6;
- suppress the unavailable Android 12 QNS handover-super call;
- isolate the ePDG interface namespace and bound invalid decoded CIDs to the
  known single-context fallback;
- read the per-subscription Android WFC setting before the Samsung legacy
  settings fallback;
- tolerate a temporarily unavailable Wi-Fi service;
- observe subscription-table changes so a WFC toggle or SIM state change is
  re-evaluated.

The contract is
[`devices/m11q/epdgservice-compat-contract.json`](../devices/m11q/epdgservice-compat-contract.json).
[`tools/transform_epdgservice_compat.py`](../tools/transform_epdgservice_compat.py)
rejects a wrong class, superclass, method set, input hash, missing/duplicate
anchor, partial application, repeated application, output-hash drift, or any
change to an unrelated method in a target class.

## Fresh stock rebuild

Use apktool 2.9.3 and the Java runtime whose hashes are enforced by the
builder. The pinned validation runtime is OpenJDK 11.0.32.1
(`11.0.32.1+1-post-1ubuntu1-26.04-Ubuntu`):

```bash
python tools/build_epdgservice.py \
  --stock-apk /path/to/hash-matching/EpdgService.apk \
  --apktool-jar /path/to/apktool_2.9.3.jar \
  --java /path/to/pinned/java \
  --output /private/output/EpdgService-unsigned.apk \
  --report /private/output/EpdgService-report.json
```

The builder decodes the stock APK in a disposable directory, applies EC1,
rebuilds only to obtain `classes.dex`, then repacks from the original stock APK.
It replaces only `classes.dex`, removes only the three exact v1 signature
entries, and verifies that every other ZIP entry is byte-identical. It then
re-decodes the result and verifies the complete class inventory, every EC1
target hash, and every unrelated class hash.

One apktool round-trip normalization is explicitly pinned: an explicit `false`
static boolean default is represented without the redundant initializer. The
builder proves that exact one-line semantic normalization and rejects any other
unrelated-class change.

The reproducible unsigned output pins are:

- `classes.dex`: `845ffb5b45fa3c077776c0d51bbd51dc2aa5b2fb84b087001a2561b4ee33acee`
- unsigned APK: `5eb14c66f5a6917de214d823f34b7dd453f6b22a64b91d74c733c89e23e23f98`

The new DEX is not byte-identical to the historical runtime-tested DEX because
the latter came from an earlier apktool rebuild history. Structural equivalence
is established by exact target-class hashes, unchanged unrelated methods and
classes, the pinned harmless boolean-default normalization, and preservation of
all unrelated stock APK entries. The historical implementation was runtime
validated as part of the working VoWiFi stack; the newly reconstructed unsigned
APK is deterministic and structure-verified, but is not separately claimed as
on-device validated until it is signed, integrated, and tested by the ROM
maintainer.

Samsung APK, DEX, decoded smali, and generated reports containing private paths
must remain outside Git history.
