# Stage 1 runtime baseline

## Verified configuration

- Device: Samsung Galaxy M11 `SM-M115F` (`m11q`)
- Target: CherishOS 4.12 / Android 13
- Stock IMS payload reference: `M115FXXS5CWK3`
- SIM scope: SIM1 WWAN
- SELinux: Enforcing
- Validation date: 2026-09-07

## Acceptance result

| Capability | Result |
| --- | --- |
| IMS registration and Android MmTel Voice | PASS |
| Outgoing call establishment | PASS |
| Outgoing bidirectional speech | PASS |
| Outgoing teardown | PASS |
| Incoming SIP/session delivery | PASS |
| Android Telephony ringing and Telecom ingress | PASS |
| Dialer ringing and answer | PASS |
| Incoming bidirectional speech | PASS |
| Incoming teardown | PASS |
| IMS process stability across incoming call | PASS |
| SELinux Enforcing for this scope | PASS |

The incoming trace reaches Samsung `onNewIncomingCall` and
`onImsIncomingCallEvent`, Android `ImsPhoneCallTracker` `RINGING`, Telecom's
successful incoming-call path, `onCallStarted`, active call and normal
disconnect. The VoLTE indicator remains present and `com.sec.imsservice` keeps
the same PID. The former private-listener linkage crash and incoming Binder
deadlock do not recur.

Golden capture names retained privately by the tester:

- `volte_capture_20260907_092745_friend_call_me`
- `volte_capture_20260907_093116_I_call_friend`
- `IMS_Test.zip`

## Regression boundary

Do not reopen basic IMS registration, IMS APN, outgoing call control or
incoming call control without contrary runtime evidence from a new build.
Compare future changes against both golden captures.

## Not validated

- SIM2/DSDS; SIM2 currently exposes no VoLTE/MMTEL support flag
- IMS SMS
- VoWiFi
- emergency calling
- video calling/ViLTE
- handover or alternate audio devices
- long-duration and repeated-call robustness
- other devices, firmware builds and carrier environments
