# Profile-backed cross-country VoWiFi configuration — 2026-10-09

The artificial Taiwan-only coverage of the extra vendor overrides has been
removed. The generated policy now covers **93 PLMNs across 33 MCCs**, including
the existing four Taiwan entries. This means 89 additional PLMN overrides,
not 93 carriers/countries and not worldwide runtime certification.

## What determines eligibility

Derived from the currently staged M115FXXS5CWK3 Samsung resources, with their
exact hashes recorded in `devices/m11q/global-wfc-profile-policy.json`:

1. Exact MNO has IMS and VoWiFi enabled in `imsswitch.json`.
2. A normal, registration-enabled IMS profile has enabled Wi-Fi `mmtel` service.
   Emergency-only profiles do not count; missing defaults are not guessed.
3. The same MNO has an IMS APN and enabled ePDG settings in `epdg_apns_conf.xml`.
4. No unverified carrier-specific CA file is required.
5. A generic PLMN mapping exists, and every mapped SIM variant for that PLMN
   meets the same criteria. A supported parent is not extended to an unsupported
   MVNO; subset/GID/SPN-only mappings are not promoted to whole-PLMN support.

There is no MCC 466 eligibility check. Only the known `@BLOCKGC` stock suffix
is removed when comparing MNO names; unrelated identities are not reinterpreted.
Two-/three-digit numeric MNC collisions are excluded rather than guessed.

Some otherwise supported parent networks remain without a new override because
their PLMN also contains unsupported or differently selected variants. These
14 partial/filter-only candidates are recorded in the contract; their selectors
need a separate exact-match implementation before enabling them. This is an
identity/configuration limit, not a country restriction.

All other PLMNs retain the ROM's existing carrier configuration. They are not
globally forced off, nor globally forced to advertise WFC support.

## Runtime changes and unchanged behavior

The device CarrierConfig vendor overlay now adds WFC availability and Samsung
ePDG service bindings only for eligible PLMNs. New entries default WFC to off;
existing stored user choices remain authoritative. No subscription database,
native profile, APN, entitlement, provisioning flag or permanent preference is
written. Carrier-privileged configuration and native provisioning checks remain.

Original Taiwan carrier values and historical framework handover policy are
preserved. That policy is not copied to foreign carriers. A common false setting
keeps the AP-assisted experiment disabled; boot-time legacy mode and Samsung's
modem-led switching remain unchanged. SA2/SEH already accept valid operators
without a TWM allowlist; their single-active-SIM/slot-0 and call-type gates remain.
This change does not add DSDS, reverse-engineered audio behavior or retry delays.

Applied WSL file:
`/home/user/android/crdroid/device/samsung/m11q/overlay/packages/apps/CarrierConfig/res/xml/vendor.xml`.

Local device commit: `913a9c872ff4b871f5a620dd2f072474eb29a6e3` on `m11q-volte`; not pushed.

Original source backup:
`D:/m11q/work/global-wfc-source-backup-20261009/vendor.xml`.

Published reproducibility inputs are the authored historical vendor baseline,
generated overlay, input hashes and MNO/PLMN metadata. Samsung APK/JSON/APN
resources, certificates and private captures are not added to Git.
`platform/carrierconfig/.gitattributes` preserves LF bytes for pinned XML files.

## Validation

- 301 host regression tests, 4 skipped, no failures (24 new global-policy tests).
- Source/input-resource gate PASS on the active WSL source.
- Regeneration matches both generated XML and contract byte-for-byte.
- Isolated AAPT2 resource compile/link fixture passes the full compiled XML gate.
  This was not a ROM build and its test APK was not installed on the phone.
- The old installed-partition product output fails the new matrix gate as intended.
- Product verification checks actual packaged IMS/ePDG resources and every overlay
  entry/value, including service-name CDATA. The binary XML parser now preserves
  AAPT2 raw text and older typed text instead of ignoring string values.

No ROM build, flash, GitHub push or foreign-SIM runtime test was performed.

## User build / acceptance boundary

After the user's normal ROM build, run from the compatibility-layer repo:

```sh
python3 tools/global_wfc_profile_policy.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
python3 tools/legacy_seh_apn_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
python3 tools/sa2_telecom_audio_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
```

The existing `legacy_iwlan_trial.py verify-product` CLI also requires the global
matrix when this new contract is present, so its PASS can no longer accept an
old Taiwan-only overlay. Historical direct verification APIs/replay backups
remain usable for the original experiments.

All relevant gates must pass before flashing. Check the real number display
fix, then confirm TWM VoLTE/VoWiFi, W2L/L2W bidirectional audio and a subsequent
LTE call still work. Foreign entries are source-supported, not runtime-proven;
their network may still require account entitlement or supported SIM plans.

## Regenerate / check source without a ROM build

```sh
python3 tools/global_wfc_profile_policy.py generate \
  --ims-apk /home/user/android/crdroid/device/samsung/m11q/ims/proprietary/priv-app/imsservice/imsservice.apk \
  --epdg-config /home/user/android/crdroid/device/samsung/m11q/ims/proprietary/etc/epdg_apns_conf.xml \
  --base-vendor platform/carrierconfig/taiwan-legacy-baseline-vendor.xml \
  --output-dir /mnt/d/m11q/work/global-wfc-new-review
python3 tools/global_wfc_profile_policy.py verify-source \
  --android-root /home/user/android/crdroid
```

The output directory must be new. Changed Samsung resources require regeneration
and review; do not just update the input hashes to make a gate pass. Source apply
checks the exact baseline and retains a backup before atomic replacement.
