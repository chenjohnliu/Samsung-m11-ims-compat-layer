# BQ1 SIM hot-swap Voice capability recovery

## Confirmed runtime defect

After SIM1 removal and reinsertion, the device returned to LTE service, the IMS
APN connected with P-CSCF addresses, and Samsung successfully registered the
normal WWAN profile with services `[smsip, mmtel]`. Android also received WWAN
IMS registration. The compatibility facade nevertheless published capability
mask 8 repeatedly: SMS was true while Voice remained false. The VoLTE indicator
therefore stayed absent. An airplane-mode cycle performed a real deregistration
and re-registration but reproduced the same SMS-only state.

The IMS process did not restart during the airplane-mode test. A cold boot
restored `Voice=true`, `SMS=true` and `isVolteEnabled=true`.

## BQ1 runtime result

BQ1 was not sufficient. A real SIM1 removal/reinsertion test showed Samsung
registering `[smsip, mmtel]` on RAT 13 and Android receiving `onRegistered`,
while the process PID remained stable. The facade nevertheless kept publishing
an empty MMTEL capability set. The first interpretation was that a late legacy
capability event cleared `nativeVoice`; BQ2 was created to test that hypothesis.

## Root cause and correction

The bridge required three conditions for Voice: normal typed registration,
Android's Voice enablement, and the legacy Samsung
`registrationFeatureCapabilityChanged()` state. SIM removal cleared the legacy
state, but Samsung did not reliably replay its positive legacy callback after
hot-swap. SMS recovered because it uses the current Samsung registration
snapshot directly.

BQ1 restores the legacy Voice state when the existing strict
`hasNormalVoiceRegistration()` predicate confirms a normal SIM1 cellular
registration. That predicate requires a VoLTE service and excludes IWLAN,
emergency and CMC profiles. `onRegistering()` and `onDeregistered()` still clear
Voice, and a subsequently delivered legacy capability callback can still
override it. BQ1 therefore does not force Voice merely because LTE or an IMS
bearer exists.

## BQ2 refinement

BQ2 retains every BQ1 gate and additionally reconciles `nativeVoice` from the
same strict Samsung registration snapshot during the existing two-second
backend health check. Reconciliation can only occur when the typed Android
registration state is already registered and Samsung currently exposes a
normal SIM1 cellular VoLTE registration. A typed registering/deregistered event
still clears both gates, so an IMS bearer or LTE service alone cannot advertise
Voice.

## BQ2 runtime result and BQ3 correction

BQ2 also remained SMS-only. The flashed bridge DEX matched the BQ2 candidate,
Samsung and Android registered normally, and no BQ2 marker appeared. This
falsifies the late-`nativeVoice` hypothesis: `nativeVoice` was already true.
The remaining false gate was the context-local `voiceEnabled`, which resets
when SIM removal recreates the feature and Android does not replay its enable
request.

BQ3 retains only Android's last explicit Voice/SMS enablement during the
current IMS process lifetime and restores it into the replacement SIM1 feature.
The clean-stock generator keeps the primary DEX identical to the
runtime-validated BP1 build.

## BQ3 + BQ6 runtime result

Runtime validation on 2026-09-10 used a clean flash to exclude persistent
IMS/Telephony state left by prior experimental APK swaps. With BQ3 plus the BQ6
generic CarrierConfig fallback, SIM1 removal/reinsertion restored the VoLTE
indicator. Outgoing VoLTE connected both before and after hot-swap. An external
incoming call then rang, answered with clear bidirectional speech, and tore down
normally, and SMS send/receive passed.

BQ6 is carrier-neutral. It applies the m11q device opt-in only after all
CarrierConfig layers are merged and accepts a completed-load proof using stable
MCC, MNC and carrier ID rather than volatile SPN/IMSI/GID fields. SIM1 must be
the default-data subscription and the only active SIM. SIM2/DSDS remains
unclaimed.
