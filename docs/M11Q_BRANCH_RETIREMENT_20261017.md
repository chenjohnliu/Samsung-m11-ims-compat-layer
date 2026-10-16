# M11Q branch retirement, 2026-10-17

Four historical donor branches were retired after their exact tips were
preserved as archive tags in the same repositories. Three other donor branches
remain for distinct source or release-history reasons. All seven
`cherish-13-m11q-ims` commits remain at the pins in the
[source index](SOURCE_INDEX.md); this housekeeping does not change Android
source trees or provide new device validation.

## Retired branches

| Repository | Removed branch | Archive tag | Preserved commit |
| --- | --- | --- | --- |
| [android_frameworks_opt_net_ims](https://github.com/chenjohnliu/android_frameworks_opt_net_ims) | `m11q-emergency-capability-mask` | `archive/m11q-emergency-capability-mask-20261017` | [1b1a32269a62de0e82e3ede53bf2c44751307f18](https://github.com/chenjohnliu/android_frameworks_opt_net_ims/commit/1b1a32269a62de0e82e3ede53bf2c44751307f18) |
| [android_frameworks_opt_telephony](https://github.com/chenjohnliu/android_frameworks_opt_telephony) | `m11q-volte` | `archive/m11q-volte-20261017` | [6c209a7d4fb239e8c8826d1c303f26dd6417dd5a](https://github.com/chenjohnliu/android_frameworks_opt_telephony/commit/6c209a7d4fb239e8c8826d1c303f26dd6417dd5a) |
| [android_packages_services_Telephony](https://github.com/chenjohnliu/android_packages_services_Telephony) | `m11q-volte` | `archive/m11q-volte-20261017` | [26d0551acfa76e1fbcbc63e1114327e578badef7](https://github.com/chenjohnliu/android_packages_services_Telephony/commit/26d0551acfa76e1fbcbc63e1114327e578badef7) |
| [android_system_netd](https://github.com/chenjohnliu/android_system_netd) | `m11q-volte` | `archive/m11q-volte-20261017` | [8e455b91f8aa5b52771fbcf0250a7181f16ec43e](https://github.com/chenjohnliu/android_system_netd/commit/8e455b91f8aa5b52771fbcf0250a7181f16ec43e) |

The IMS framework donor and the synchronized Cherish commit have identical
complete trees (`7debdb23edb288a03ae7ec5550b0ced2711be7b8`), as do the netd pair
(`ba89c15b79d86144876f596de94cd579221d152e`). Telephony framework and phone
service donor changes are represented by the adapted source patches indexed
for Cherish; their old and new commits are not claimed to be identical or
related by a merge. In particular, the subscriber GID2 API and its framework
companion, and the phone service's single-active-SIM fallback, remain in the
current patch recipe. Archive tags preserve the original implementations and
their ancestry independently of those adaptations.

At the time of removal, none of these four refs was a default or protected
branch, an open PR head/base in the fork, or a release target. Each archive tag
was checked against the original full commit SHA before removal. Branch
deletions used an expected-head lease so a concurrent new commit would stop
the operation. The tags and all seven current Cherish pins were checked again
afterward. No repository, upstream branch, release or existing release tag
was deleted.

## Branches retained

| Repository and branch | Observed tip | Reason |
| --- | --- | --- |
| `android_frameworks_base:m11q-volte` | `73178bfc7d1e81b64b02d2b24c14ef24a8a1ecdf` | Contains additional microG / Play Integrity history outside the IMS checkpoint. It is not a redundant copy of the Cherish IMS branch. |
| `android_packages_services_Telecomm:m11q-vowifi-audio-path` | `8e1a9a333a5692343f8bede5a2fe2dcac0d44489` | The historical crDroid restoration instructions still use this LineageOS-derived donor history, including the earlier `66d3d91d238436c9a04cd4b653f3db02db4f901e` pin. Cherish has an adapted implementation; complete donor equivalence was not established. |
| `android_device_samsung_m11q:m11q-volte` | `47722f9924a85c73c319eeaae652b46d188de74a` | Still the repository default and the `target_commitish` of release `20261010-13-CrDroid`. It also includes release-history documentation absent from the indexed Cherish tree. The actual release tag remains its fixed source identity. |

These are historical donor or release branches, not the current Cherish build
route. Keeping them does not mean their entire contents should be imported
into `cherish-13-m11q-ims`.

## Reference updates and recovery

- [ROM bring-up](M11_ANDROID13_ROM_BRINGUP.md) directs current Cherish integration
  to the seven indexed pins and fetches the four retired donors by archive tag
  in its historical replay example.
- [The machine-readable index](../devices/m11q/cherish-source-index.json) keeps
  each original donor branch name and recorded SHA as provenance and adds the
  archive tag, commit and retirement date. Original checkpoint manifests,
  patch hashes and historical commit pins remain unchanged.
- References to retained branches remain valid. Dated audits that merely
  describe an old branch name are historical evidence, not fetch dependencies.

To recover one of the removed branch names in its original repository, use
the corresponding row above, fetch the archive tag, verify its commit, and
create the branch from that exact commit. For example, in a clone of
`android_frameworks_opt_telephony`:

```sh
git fetch origin refs/tags/archive/m11q-volte-20261017
git rev-parse FETCH_HEAD
# Require: 6c209a7d4fb239e8c8826d1c303f26dd6417dd5a
git push origin 6c209a7d4fb239e8c8826d1c303f26dd6417dd5a:refs/heads/m11q-volte
```

Offline source-index validation and the source-index / Cherish handoff tests
passed. No ROM build, flash or call test was performed for this reference-only
cleanup.
