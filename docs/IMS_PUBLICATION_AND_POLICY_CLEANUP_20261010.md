# IMS publication and narrow policy cleanup — 2026-10-10

Later user-build finding: the published icon checkpoint had an incorrect
registration-constant import package. See the
[import-only correction and checkpoint replay instructions](SYSTEMUI_IMS_IMPORT_BUILD_FIX_20261010.md).
The successful host tests below did not validate those original Android imports.

This checkpoint supersedes the older local-only publication status. Changes are
committed separately by purpose; historical experiments remain documentation,
not instructions to enable them.

## Only the requested policy removal

`global-stock-profile-v2` removes the old `ims.handoverPolicy` arrays from the
four `46601`, `46605`, `46692`, and `46697` carrier entries. These arrays blocked
framework IWLAN-to-EUTRAN IMS handover. The immutable historical baseline still
contains them so older generations remain reproducible; the generated active
overlay and live WSL source no longer do.

The 93 profile-backed PLMNs, availability/provisioning rules, legacy IWLAN mode,
Android Wi-Fi shutdown deferral, Samsung weak-signal behavior and timers remain
unchanged. The AP-assisted experimental handover flag remains false. Stock
Timer F is 128 seconds. Existing phone-number, IMS-registration icon and stock
Telecom audio compatibility fixes are retained, not removed by this cleanup.

Generated vendor XML SHA-256:
`0f3f343f34e2b9658716e56f961cbc9a80196b76a7dd5e7d5de8d0eaf406423f`.

## Source publication locations

| Component | GitHub publication | Source commit |
| --- | --- | --- |
| device/samsung/m11q | chenjohnliu/android_device_samsung_m11q, m11q-volte | `0f1da5855d27841d53743cd878ecd2d09679a941` |
| packages/services/Telecomm | chenjohnliu/android_packages_services_Telecomm, m11q-vowifi-audio-path | `8e1a9a333a5692343f8bede5a2fe2dcac0d44489` |
| frameworks/base | This repository's patch checkpoint | `ccfc0c8da6c4f64300ca27f0b78e263167f8e38b` |
| frameworks/opt/net/ims | This repository's patch checkpoint | `f4c719f119848dbfeeca2c214cedd13cb4fd076a` |
| frameworks/opt/telephony | This repository's patch checkpoint | `96372ce211432ce3e4764a167633457dc049ef5c` |
| packages/services/Telephony | This repository's patch checkpoint | `04cde10d1966ba35d1fb8fc2193867283465c487` |
| system/netd | This repository's patch checkpoint | `91016fbe38db8c2bc08f7476c173648a5124c526` |

The five upstream-only repositories have no personal remote. Their eight
commits are published in [the patch checkpoint](../platform/checkpoints/ims-20261010/manifest.json),
not pushed to crDroid/LineageOS upstream. The manifest pins each base commit,
source HEAD, complete tree and patch SHA-256. Applying each series to an
isolated Git index reproduced its source HEAD tree exactly. This is complete
source publication via patches, not a claim that five new GitHub forks exist.

For a fresh clean checkout at the corresponding manifest `base_commit`, apply
that component's numbered patches in order with `git am`, then check
`git rev-parse HEAD^{tree}` against its `head_tree`. Do not replay onto the
existing modified WSL checkouts: they already contain these changes.

The full WSL inventory examined 1,214 checkouts with zero collection errors.
Seven unpublished IMS source heads are covered above. Unrelated kernel build
changes and the local `clang-latest` toolchain are intentionally not committed
or published. Private captures, IPsec keys, Samsung input binaries, generated
APKs/JARs, signing material and backups remain excluded.

## Validation and next build

- Global WFC v2 source gate: PASS, 93 approved PLMNs.
- SEH1/LG3 source gate: PASS; current Java source matches the compatibility repo.
- SA2 source gate: PASS; existing audio behavior retained.
- Targeted policy/bridge/audio/build-tool/capture/OTA host tests: 107 PASS.
- SystemUI tests including extracted actual Java callback bodies: 6 PASS.
- Full host regression suite: 337 tests, 4 skipped, no failures.
- Eight patches: SHA-256 checked and five full source trees replay-verified.
- Source whitespace checks: PASS.

No Android ROM build, flash or new runtime validation was performed. The prior
[hotspot handover acceptance](CRDROID_HOTSPOT_HANDOVER_PASS_20261010.md) applies
to its recorded phone binaries, not to this later source-only policy/icon
checkpoint. The previously verified 20261009 OTA is unchanged and does not
contain these latest changes.

After the next user build, run the normal global WFC, SEH and SA2 product gates
before flashing. In one test batch, check VoWiFi incoming/outgoing audio,
same-call W2L/L2W, a fresh LTE call afterward, phone-number display and icon
clearing with Wi-Fi off. SIM2 and foreign-carrier runtime acceptance remain
separate unverified scopes; single active SIM support is not dual-active IMS.
