# Current device source: m11q-volte

The current `device/samsung/m11q` source directly references the maintained
[m11q-volte branch](https://github.com/chenjohnliu/android_device_samsung_m11q/tree/m11q-volte),
pinned at `a42e98add2d431b5d677b4ec6e51f5f02ca3e0e7` for reproducibility.
The older device `cherish-13-m11q-ims` branch is retained only as history.
The six platform repositories continue using their separate Cherish branches.

## Apply the device source

Use the exact shared commit above, then apply only
[`cherish-product.patch`](../platform/checkpoints/m11q-shared-20261023/cherish-product.patch).
The patch changes `AndroidProducts.mk` from the shared `lineage_m11q` product
and lunch targets to `cherish_m11q`. No separate Cherish device branch is needed.

Fingerprint, shared Samsung TSP DT2W and the current native IMS library build
definitions are already in this shared base. The earlier device fingerprint
and DT2W supplement patches are historical and must not be added again.
The matching vendor source remains [13-64 at 8aac25ba](https://github.com/chenjohnliu/proprietary_vendor_samsung_m11q/tree/8aac25babaee78b9243c2ee05aaf8180d88b3902).

The [device manifest](../platform/checkpoints/m11q-shared-20261023/manifest.json)
and [current source index](../devices/m11q/cherish-source-index.json) lock:

| Stage | Git tree |
| --- | --- |
| Shared device base | `3f4fb779d9c4d07a6357806acf1771a9a7fa5087` |
| After the Cherish product patch | `9f00b7c9c2d9f62bea9eaa3bce00efa66161f856` |

## Validation and scope

The public shared commit was fetched into an isolated bare repository. The
single patch passed apply-check, forward and reverse replay, changing only
`AndroidProducts.mk` relative to that base. The complete current source route
has 14 projects and 24 patch steps; the
[verification record](../devices/m11q/shared-device-source-validation-20261023.json)
records exact tree checks.

This device reference differs from the earlier local Cherish snapshot in the
release documentation and native SVE library packaging (`ims/Android.mk` and
`ims/compat/sve/Android.bp`). The source checks do not establish a passing new
ROM build or hardware test. The existing live Cherish/crDroid build checkouts,
their local manifests, HEADs and indexes were not switched or modified by this
reference update.

Future device updates should advance the shared branch, update the indexed
commit and trees, and revalidate the single product patch. Keep historical
checkpoints immutable; the current per-project index determines which route to use.
