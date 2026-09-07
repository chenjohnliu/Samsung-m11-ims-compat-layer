# Stage 1BJ incoming Binder deadlock

## Runtime finding

The Stage 1BI runtime test confirmed this complete path on SIM1 WWAN VoLTE:

```text
SIP INVITE
  -> Samsung incoming session
  -> 183 / 180 Ringing on the network side
  -> getPendingCallSession()
  -> Android ImsPhoneCallTracker.processIncomingCall()
```

The IMS process did not crash, IMS registration stayed up and the remote caller
eventually cancelled the unanswered call. Android never published a ringing
connection to Telecom.

An Android ANR trace later captured the exact lock cycle:

- Samsung's ServiceModule thread held the `ModernVoiceContext` monitor while
  blocked in synchronous `IImsMmTelListener.onIncomingCall()`;
- Android Telephony synchronously re-entered the supplied
  `ModernCallSession` while processing that callback;
- `ModernCallSession.check()` waited for the same owner monitor.

This is a compatibility-layer deadlock, not an IMS APN, SIP delivery, carrier
registration, Dialer-ringtone or SELinux failure.

## Fix

`ModernVoiceContext.incoming()` now performs identity checks, pending-session
lookup, wrapping and publication inside a synchronized block. It captures the
feature, wrapper and extras, exits the monitor, and only then calls
`notifyIncomingCallSession()`.

The session ownership check remains synchronized. Removing that check would
weaken epoch and closed-session safety without fixing the general rule: no
cross-process callback may be made while holding the bridge owner monitor.

## Runtime verification

The local clean-stock builder compiles and structurally verifies the fixed
candidate. A manual ROM build and real external call on 2026-09-07 completed
the runtime milestone:

```text
incoming INVITE
  -> processIncomingCall returns
  -> Telecom receives a ringing connection
  -> Dialer rings
  -> answer and active call
  -> clear bidirectional speech
  -> normal disconnect
```

`com.sec.imsservice` retained the same PID before and after the call, IMS
registration and the VoLTE indicator remained present, and the former linkage
crash and deadlock did not recur. The separate outgoing real-party call also
passed establishment, clear bidirectional speech and teardown.

This is the Stage 1 golden baseline for SIM1 WWAN VoLTE only. SIM2/DSDS, IMS
SMS, VoWiFi, emergency calling, ViLTE and extended regression testing remain
unverified.
