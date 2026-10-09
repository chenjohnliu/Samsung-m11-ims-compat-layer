# LG2: repair the legacy IMS CID lookup

## Confirmed blocker, not a handover success claim

The LEG1 + SS1 capture in `work/leg1_w2l_20261004_230423/private` shows
ePDG finding the connected LTE IMS network but failing before tunnel setup:

- `logcat_all_private.txt:2972-2974`: `rmnet_data1` is parsed as `a1`, integer
  conversion returns `-3`, and the handler reports `invalid cid for ims`.
- Lines 3076/3089 begin L2W; lines 3130-3131 repeat the same lookup failure.
- IPsec state machines remain inactive, with null APN/IWLAN settings. Native
  IMS remains registered at LTE RAT 13; no actual WFC source is established.

The stock capture in `work/stock_w2l_20261004_1601/private` parses the same
interface as `1` and returns profile ID 2, including lines 31047-31048.
The phone's radio property was read directly: `ril.data.intfprefix=rmnet_data`.

EC1 intentionally replaced `EpdgUtils.getMobileInterfacePrefix()` with
`epdg_data` for the AP-assisted interface namespace. LEG1 selects the stock
legacy branch but retained this shared helper unchanged. The legacy parser
removes the prefix's length from the real `rmnet_data1` interface, producing
`a1`, then exits before selecting the IMS state machine. This is a concrete
compatibility-layer regression in the new legacy experiment, not evidence
that all historical crDroid VoWiFi calls were cellular calls.

## Narrow repair

`tools/legacy_epdg_prefix_compat.py` patches only that method in the exact
EC2-r2 unsigned APK. It uses Samsung's existing `isIwlanLegacyMode()` helper:

- Explicit `legacy`: read `ril.data.intfprefix`, with the original `rmnet`
  fallback. On this device, `rmnet_data1` therefore maps to profile ID 2.
- AP-assisted, unset/default, and unknown values: retain `epdg_data`.

The separate AP-assisted TelephonyAdapter namespace stays unchanged. No modem
firmware, IMS bridge, SS1 framework method, Wi-Fi deferral, RSSI threshold,
carrier scope, timeout, or call-session behavior is changed by LG2.
The boot label remains `legacy-r1`; identify LG2 by its ePDG DEX, not that label.

The builder freshly decodes the pinned input, assembles the changed DEX, and
re-decodes the result. Every other class and ZIP entry must remain identical;
the changed class must preserve the reviewed instructions across round-trip.
Discovery cannot publish a deployable APK. A second strict build must match
the promoted pins in `devices/m11q/legacy-epdg-prefix-build.json`.

LG2 DEX SHA-256:
`3cc23c6af802802859a1644d3d6187c90a4efcd575c285e0a975a0fae37d0c05`.
Unsigned APK SHA-256:
`5c9f372867afcee56da55f10851b4c30bd95452bea0720fca68e6e73ac96de27`.
Product signing changes the APK hash, so the packaged gate checks the DEX.

Delivery status: pin discovery and an independent strict rebuild both passed
with identical APK/DEX hashes. The strict build report is local at
`out/lg2-prefix/strict-build.json`. The LG2 APK has been staged into
`/home/user/android/crdroid/device/samsung/m11q/ims/proprietary/priv-app/EpdgService/EpdgService.apk`;
LEG1 `verify-source` passes. The previous source APK is preserved at
`D:/m11q/work/leg1_legacy_trial_20261004/backup-EpdgService-before-LG2.apk`.
The existing, not-yet-rebuilt product fails the new gate with
`packaged LG2 classes.dex pin mismatch`, as intended. No phone files were
replaced; the user must build/flash/reboot before runtime validation.
Final host regression: 239 tests, 0 failures/errors, 2 optional private-baseline
tests skipped. The real compiled CarrierConfig and SS1 framework checks were
enabled and passed. Collector shell syntax and tracked whitespace checks pass.

`tools/stage_legacy_epdg_prefix.py` preserves the verified EC2-r2 APK backup,
rejects unrelated source edits, and atomically updates only the source APK
with a fresh timestamp. Its `--rollback` restores that APK without changing
LEG1 configuration. Rebuilding/flashing/rebooting is still required after
either source operation; live mode flips or APK hot replacement are not used.

## User build and consolidated validation

The agent does not run Android ROM builds, flash, reboot, or place calls.
After the source APK has been staged, perform the normal manual ROM build.
Before flashing, run this updated gate in WSL:

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/legacy_iwlan_trial.py verify-product \
  --product-root /home/user/android/crdroid/out/target/product/m11q
```

It now requires LG2, BV1/bridge, SS1 framework ABI, the legacy boot properties,
and disabled AP-assisted carrier experiment. An old EC2-r2 product must fail.
PASS proves packaging identity only, not registration or call continuity.

After flashing the matching output and fully rebooting, capture one batch:

1. Start the existing handover collector while idle. Enable/connect Wi-Fi,
   wait for the baseline, and take the idle `lg2_iwlan1` snapshot.
2. The first diagnostic sequence is numeric substring `1` -> profile ID 2 ->
   IMS state machine `[1]` acquires APN `ims` -> Eris/IPsec connection -> native
   IMS RAT 18 / ePDG connected -> Android IWLAN registration. Icons alone do
   not establish this baseline.
3. If the baseline still fails, stop the batch and provide both archives;
   do not repeatedly make handover calls, reset settings, or reboot. If the
   CID error persists, check installed DEX identity. If CID succeeds but
   tunnel/registration fails, follow the first downstream error instead.
4. Once the genuine WFC baseline is confirmed, call 188 once, wait until
   connected, turn off Wi-Fi, and keep it off for at least 30 seconds before
   hanging up. Do not run heavy dumps during the call/transition. Record
   whether audio stopped and for how long; 188 does not prove two-way audio.
5. Capture a stable post-call `lg2_w2l1` snapshot and one subsequent LTE call.
   Only after same-call continuation is proven proceed to the original three
   W2L trials and real-person two-way audio / <=2-second interruption criteria.

The aggregate IWLAN/underlying LTE ServiceState contract remains a possible
later issue, not the earliest demonstrated blocker. LG2 does not assert that
modem handover, IMS session continuation, or the audio acceptance target is
already fixed. Private captures and extracted Samsung APK payloads stay local.
