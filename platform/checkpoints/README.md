# Source checkpoint index

Start with the [source and patch index](../../docs/SOURCE_INDEX.md) to choose
the current Cherish full-source branches or the equivalent per-project patch
recipes. Exact commits, trees and patch hashes are in the
[machine-readable source index](../../devices/m11q/cherish-source-index.json).

| Directory | Purpose and order |
| --- | --- |
| [cherish-20261012](cherish-20261012/manifest.json) | Combined locked Cherish baseline for 14 projects |
| [cherish-20261012-ims-supplement](cherish-20261012-ims-supplement/manifest.json) | Telecom permission and IMS capability test after baseline; MMS copy is reference-only |
| [cherish-20261016-vowifi](cherish-20261016-vowifi/manifest.json) | Initial incoming Wi-Fi audio and legacy IWLAN MTU after prerequisites |
| [ims-20261010](ims-20261010/manifest.json) | Historical donor checkpoint; do not stack it on the combined Cherish baseline |

For a synchronized project, the indexed fork commit already contains its full
patch chain. Do not apply the same integration a second time. Existing dated
paths and fingerprints remain stable.
