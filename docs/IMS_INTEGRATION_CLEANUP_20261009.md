# IMS integration cleanup — 2026-10-09

Follow-up source scope: [single active SIM in either slot](IMS_SINGLE_SIM_EITHER_SLOT_20261009.md).
The slot-0 wording below records this cleanup's earlier checkpoint, not the
latest eligibility. Opt-in removal and stock timer restoration remain active.

## Device finding and immediate correction

The connected m11q's Telecom APK SHA256 was
`884850bea06b547224b3a61659784d5e6ee5495c90087ab3df97d67d44cfc1c9`,
identical to the current product output. The carrier-neutral SA2 patch was
present, but root readback of `persist.sys.m11_ims_audio_port` was empty.
That version requires `stock1`, so its audio adapter was disabled. No SA2
execution logs were present in the available failed-call period. This explains
why the known audio fix did not execute; audibility after correction still
requires a new call test.

With no current call, the property was set to `stock1` and read back. No APK
install, Wi-Fi change, reboot, call placement or audio request was performed.
This is compatibility for the currently flashed **old** opt-in APK, not a new
requirement for the integrated source revision.

## Active-policy inventory

- SA2: removed the entire opt-in property check, not merely changed its default.
  Existing `stock1`, `off`, or empty property values no longer affect new code.
  The m11q/legacy, single-active-SIM slot-0, foreground ordinary active audio
  call, exact Samsung counts, normal registration and generation checks remain.
  Stock STOP/mode/SAE/INFORM and CPVE sequencing is unchanged.
- SEH APN bridge: enabled in product source and root device readback (`true`).
  Its read-only product configuration is not a manual test prerequisite.
- Modem-led IWLAN: `legacy` is already the product default; Wi-Fi deferral,
  Samsung weak-signal hysteresis and re-entry timers are unchanged.
- EC2/BV1 AP-assisted experiments: their carrier-config switch remains false,
  including the global default. They are not enabled by this cleanup.
- BU1 TWM Timer F: at the user's explicit choice, remove the 16-second override.
  The resource now matches CWK3 stock byte-for-byte, inheriting 128 seconds from
  the default profile. All retry, emergency/CMC and other-carrier profiles are
  unchanged. This can lengthen recovery from a blackholed P-CSCF.
- Global WFC eligibility and ordinary user WFC preference/provisioning checks
  remain unchanged: 93 profile-backed PLMNs. No blanket all-SIM WFC forcing.

Historical `trial` filenames, backup IDs, `ro.m11q.ims_trial=legacy-r1` identity
and SELinux type names are retained for reproducibility/rollback compatibility;
they do not constitute an extra manual activation step. Diagnostic
`--handover-check` selects a read-only capture workflow, not an IMS feature flag.
The explicitly invoked manual `--start-sae` remains a diagnostic only; never
use it for integrated handover acceptance.

## Source and artifact delivery

Telecom source is applied in `/home/user/android/crdroid/packages/services/Telecomm`.
Verified prior helpers are backed up under
`D:/m11q/work/sa2-integrated-revision-20261009`; original source rollback remains
under `D:/m11q/work/sa2-telecom-audio-port-20261009/active-source-backup`.

`tools/stock_ims_timer_policy.py` inverts only the exact BU1 resource insertion,
then requires stock profile SHA256
`eac62efba558d45826fd2951bf5087c65d005cbd2587a0d817891e525e11f937`.
The resulting unsigned LG3 APK SHA256 is
`544f4c9974d3a41e2ce541f02e9ab9bda2fc6307609d719fad31656421c17582`.
Only `res/raw/imsprofile.json` changes; both DEX files and 687 other ZIP entries
are unchanged. The LG3 assembly recipe also restores the stock resource, so a
future reconstruction cannot silently reactivate BU1. Historical earlier
BU1/BV1 intermediate artifacts retain their historical identity; use the final
LG3 output, not those intermediate APKs, for the active product.

`legacy_seh_apn_trial.py refresh-assets --apk` accepts only this pinned upgrade
and checks that no other ZIP entry changes. Active source and original rollback
state are preserved, with the prior APK at
`D:/m11q/work/seh1-stock-timer-revision-20261009`.
Global WFC resource pins were regenerated/reviewed for the restored stock
profile; the approved PLMNs and vendor XML remain identical.

The new SA2 product verifier rejects the old opt-in APK. LG3/global-profile
gates reject an APK containing the old timer resource, even if its DEX matches.
These are code/resource identity checks, not proof of audible runtime behavior.

## User boundary

Non-build validation: 314 Python tests pass (4 optional private-fixture skips),
54 JVM transition/ownership/stock-order assertions pass, the actual audio adapter
compiles standalone against existing Android 13 framework/libart APIs, and
collector shell/mock tests pass. Both active source hash gates pass. The global
WFC regeneration reproduces the reviewed contract and unchanged vendor XML.
Single-pass final LG3 ZIP recipe replay reproduces the restored APK hash exactly
using the previously verified unchanged primary DEX; no smali reassembly or ROM
build was needed for the resource-only rollback.

No Android ROM build or flash is performed by the agent. After the user's
manual build, run the three checks before flashing:

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/sa2_telecom_audio_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
python3 tools/legacy_seh_apn_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
python3 tools/global_wfc_profile_policy.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
```

Use collector v7 without `--start-sae`. Test LTE→Wi-Fi→LTE on the same call,
listen at least 30 seconds after each transition, then test a fresh LTE call.
188 covers received audio; a person-to-person call checks both directions.
Foreign-carrier and dual-active-SIM handover acceptance are not asserted.
