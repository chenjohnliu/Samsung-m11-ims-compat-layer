# IMS SMS over IWLAN follow-up — 2026-10-21

This is a supplementary bridge-source fix for SMS over Wi-Fi Calling (IWLAN).
It is separate from the historical CherishOS and crDroid platform patch routes;
those checkpoint recipes remain unchanged.

## Source change

The pre-fix bridge advertised SMS capability only for LTE, tied SMS bridge
availability to the LTE enablement flag, and excluded Samsung IMS SMS
registrations on RAT 18 (IWLAN). The original private reproduction captured an
IWLAN registration with `smsip`, Android IMS SMS capability false, then a
framework modem/RIL `IMS_SEND_SMS` fallback that failed with errors 44/104.
This supports the conclusion that the Samsung bridge was bypassed on IWLAN; it
does not show a Samsung IMS SMS network rejection. The code now tracks SMS
capability independently for LTE and IWLAN, gates availability using the active
transport's flag, and selects SMS registration/SMSC profile data for the active
transport. No raw log or SMS payload is included here.

The fix is a coherent three-file change in `bridge/java/com/sec/internal/google/`:
`ModernVoiceContext.java`, `GoogleModernMmTelFeature.java`, and
`ModernSmsBridge.java`. Keep all three together because the capability setter
ABI, per-transport enablement state, registration selection and SMSC selection
must agree.

For GSI module users, compile all three changes into that module's own current,
compatible artifact while preserving its other GSI adaptations. Do not blindly
replace it with a ROM or test APK. An earlier APK-only data-app attempt failed
with a JNI error; the underlying loader cause was not established. The reported
successful validation used the rebuilt ROM.

## Validation

The source has a standalone host harness at
[`tests/java/ims_sms_iwlan/`](../tests/java/ims_sms_iwlan/). It extracts actual
methods and constructors from the three bridge files, then compiles them with
authored framework/vendor stubs. The harness covers RAT 13/LTE and RAT
18/IWLAN matching, stale transport snapshots, phone/service/emergency/CMC
filters, independent capability state, state retention, bridge gates and
SMSC selection. It does not model real Android Binder, modem delivery, APK
loading or device behavior.

The 12 existing slot-policy tests and 39 actual-source host assertions passed;
`git diff --check` also passed. These host results are separate from the phone
validation below.

On 2026-10-21 the maintainer reported that, after rebuilding and flashing
crDroid, the requested SMS send/receive tests passed along with VoLTE and VoWiFi
calls. SMS behavior remains maintainer-reported; no fresh successful-send trace
was reviewed. A subsequent read-only inspection verified the tested ROM
factory APK at `/system/system_ext/priv-app/imsservice/imsservice.apk` with SHA-256
`add55e48c9bddaa0814632fd1a6540033ca7b593ec141786ef6f6e4884ccfef7`, built
2026-10-21 07:25:25 +08:00. Its `classes.dex` hash is
`77a25da55e6c34121d17fee849e41d000b955cee8b07fccafc11ac489debc59e`; the
fixed `classes2.dex` hash is
`5922d617049149749f2115d2e8cb3ea6cc940ec02a98e3869894e8da4398ce3e`. These
identify the inspected artifact, but do not independently verify SMS behavior
from device logs. CherishOS porting is source-only at this point and needs its
own build and device validation. This report does not add evidence for Jio SMS,
earlier Jio validation, other carriers or general carrier support.

No proprietary APK, log, native payload, decoded code or signing key is part of
this public record.
