# BP1 optional SMS HQM telemetry guard

## Runtime evidence

The Stage 1BO Enforcing trace reached the carrier and confirmed that the
preceding SMS fixes were active:

- the SIM1 SMSC was normalized without the trailing TOA digits;
- Samsung assigned the TP message reference;
- an outgoing SIP `MESSAGE` was transmitted;
- the carrier returned SIP `202 Accepted` and a later 3GPP SMS response;
- the BH1 `IccUtils.getIccType(int)` linkage failure did not recur.

Samsung then entered `SmsUtil.sendSMSInfoToHQM()` while handling the network
acknowledgement. Its optional call to
`Telephony.Sms.getDefaultSmsPackage(Context)` threw a `NullPointerException`
because the Android 13 role service lookup returned null. That lookup is
outside Samsung's existing HQM exception handler. The resulting
`com.sec.imsservice` process death prevented the real SMS result from reaching
Android and left the UI in the Sending state.

## Narrow correction

BP1 guards only that default-SMS-package lookup with `RuntimeException`. On
failure it omits the optional HQM `CSDA` field, logs a BP1 marker, and resumes
the original acknowledgement path. It does not:

- force a success callback;
- rewrite carrier RP causes;
- suppress the SMS state machine;
- add a framework stub;
- change SELinux policy or add a carrier-specific branch.

The transform is bound to the exact CWK3 `SmsUtil.smali` hash and unique method
anchor. Any input or anchor drift fails closed. Local clean-stock generation,
final re-decode, DEX inventory and ZIP preservation checks pass.

## Runtime validation

Stage 1BP was validated on SIM1 under SELinux Enforcing on 2026-09-08. The
outgoing transaction followed this path:

1. Android selected `ImsSmsDispatcher` with IMS registration and SMS capability
   available.
2. Samsung sent the 3GPP SMS in a SIP `MESSAGE` and received SIP `202 Accepted`.
3. The carrier returned RP cause 50.
4. The BP1 guard caught the optional role-service `NullPointerException`, logged
   its marker, and allowed acknowledgement handling to continue.
5. Samsung returned `status=4 (Fallback)` to Android.
6. Android retried through `SEND_SMS`; the modem returned `mErrorCode=0` and the
   user confirmed successful delivery.

`com.sec.imsservice` remained alive with PID 2101 across the transaction. The
former HQM crash and permanent Sending state did not recur.

This validates outgoing SMS with working IMS-to-SGs/CS fallback. It does not
claim that the carrier accepted final delivery over IMS, because the captured
transaction explicitly used fallback after RP cause 50. Incoming SMS, SIM2 SMS
and pure IMS-SMS delivery remain outside this validation.
