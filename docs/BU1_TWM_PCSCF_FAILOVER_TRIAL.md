# BU1 TWM P-CSCF Failover Trial

## Scope

BU1 is a runtime experiment for the normal `TWM Mobile VoLTE` IMS profile
(`TWM_TW`, representative PLMN `46697`). It changes SIP Timer F from 128000
ms to 16000 ms. It does not change the inherited 30-second registration retry
base, emergency profiles, CMC profiles, carrier eligibility, or any other
carrier profile.

The experiment is intentionally TWM-only. Do not extend it to the other Taiwan
operators until device-side validation shows that the shorter transaction timer
improves recovery without causing registration regressions.

## Evidence and hypothesis

The 2026-09-29 Wi-Fi-cycle capture showed that the IWLAN IMS bearer completed
setup and remained connected. The first normal IMS registration received the
AKA challenge, changed to TCP port 5067, and then produced no transmitted
authenticated REGISTER or response before Samsung IMS reported `708 TimerF
Timeout` about 128 seconds later. The registration governor then waited its
30-second base retry interval, advanced from P-CSCF index 0 to index 1, and
registered successfully on the same bearer.

This supports a slow P-CSCF failover failure mode rather than an IWLAN bearer
setup failure. BU1 reduces only the first timeout so the hypothesis can be
tested without also changing governor backoff behavior.

## Expected device behavior

If P-CSCF index 0 blackholes in the same way, the `708 TimerF Timeout` should
occur near 16 seconds rather than near 128 seconds. With the preserved
30-second retry base, registration through P-CSCF index 1 should recover in
roughly 46 seconds rather than roughly 158 seconds.

If the timeout remains near 128 seconds, the runtime profile override was not
loaded, or a cached profile database took precedence. If 16-second failures
appear on a healthy primary P-CSCF, or otherwise stable IMS registration
regresses, revert BU1.

## Validation batch

1. Build and flash the ROM containing the BU1 candidate. Do not reuse an old
   system image.
2. Confirm LTE IMS and an ordinary LTE call still work.
3. Enable Wi-Fi and wait for VoWiFi registration. Record the P-CSCF index,
   registration error timestamp, successful registration timestamp, and active
   RAT from `dumpsys secims` and Samsung IMS logs.
4. Place a 188 test call only after VoWiFi is registered.
5. Repeat LTE-to-Wi-Fi transition and registration at least three times. Include
   one Wi-Fi off/on cycle after a successful VoWiFi call.
6. Capture one consolidated log bundle covering the complete batch.

Success means the reproduced blackhole times out near 16 seconds, advances to
the second P-CSCF, and registers after the existing retry interval, while LTE,
VoWiFi calling, emergency-profile selection, and ordinary stable registration
show no new regression.

After runtime validation, a separate experiment may reduce the registration
retry base to 15 seconds. Applying the policy to all Taiwan carriers is a later
change and requires carrier-specific profile inventory plus validation.

## Reproducibility

The public transform is `tools/transform_bu1_twm_pcscf_failover.py`, governed
by `devices/m11q/bu1-twm-pcscf-failover-trial-contract.json`. The pinned
unsigned candidate SHA-256 is
`4cf9360b609fcc45329d038835a5913ba9c76844fe4cf59b70c132f904ae0dd1`.
Its two DEX entries are unchanged from the preceding strict IMS candidate; the
only newly replaced payload entry is `res/raw/imsprofile.json`.
