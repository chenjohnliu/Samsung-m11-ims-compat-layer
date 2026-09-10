# Stage 1 runtime baseline

## Verified configuration

- Device: Samsung Galaxy M11 `SM-M115F` (`m11q`)
- Target: CherishOS 4.12 / Android 13
- Stock IMS payload reference: `M115FXXS5CWK3`
- SIM scope: SIM1 WWAN
- SELinux: Enforcing
- Validation dates: 2026-09-07 through 2026-09-10

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
| Outgoing SMS IMS-to-SGs/CS fallback and delivery | PASS |
| SIM1 removal/reinsertion restores VoLTE availability | PASS |
| Post-hot-swap outgoing and incoming VoLTE | PASS |
| Post-hot-swap SMS send and receive | PASS |
| SELinux Enforcing for this scope | PASS |

The incoming trace reaches Samsung `onNewIncomingCall` and
`onImsIncomingCallEvent`, Android `ImsPhoneCallTracker` `RINGING`, Telecom's
successful incoming-call path, `onCallStarted`, active call and normal
disconnect. The VoLTE indicator remains present and `com.sec.imsservice` keeps
the same PID. The former private-listener linkage crash and incoming Binder
deadlock do not recur.

On 2026-09-08, the outgoing SMS trace reached Samsung IMS and the carrier. The
carrier returned RP cause 50, BP1 allowed Samsung to report fallback instead of
crashing in optional HQM telemetry, Android retried through `SEND_SMS`, and the
modem returned success. The user confirmed delivery and the IMS process stayed
alive. This is an outgoing SMS fallback baseline, not a pure IMS-SMS delivery
claim.

On 2026-09-10, a clean-flash Stage 1BQ3 bridge plus BQ6 Telephony fallback
restored the VoLTE indicator after physical SIM1 removal/reinsertion. A call to
188 connected before and after hot-swap. A subsequent external incoming call
rang, answered with clear bidirectional speech, and tore down normally; SMS
send and receive also passed. Earlier cold-boot call failures survived source
rollback but disappeared after formatting `/data`, so those traces are retained
as evidence of persistent-state contamination rather than a BQ code regression.
The exact contaminating IMS/Telephony data item is not identified.

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
- final pure IMS-SMS delivery and SIM2 SMS; post-hot-swap SMS receive passed,
  but its transport was not classified
- VoWiFi
- emergency calling
- video calling/ViLTE
- handover or alternate audio devices
- long-duration and repeated-call robustness
- other devices, firmware builds and carrier environments
