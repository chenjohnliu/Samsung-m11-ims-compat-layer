# Stage 3 incoming VoWiFi media start

## Result

On 2026-09-26, an incoming Taiwan Mobile VoWiFi call on the M11 completed with
bidirectional audio and remained connected. The same caller/receiver test had
previously produced silence in both directions and a network-driven disconnect
about 15–17 seconds after answer. Outgoing VoWiFi to 188 remained audible and
could be ended normally.

This validates the ordinary, non-CMC incoming voice path on IWLAN for the
tested device, firmware input, Android 13 ROM and subscription. It does not
validate emergency calling, ViLTE, handover, alternate audio routes, concurrent
dual-SIM operation, other carriers, or other devices/builds.

## Root cause and rejected placement

Samsung's native audio session was not ready when the earlier incoming-call
hook selected the SAE interface. The request was therefore queued before the
call reached the native ESTABLISHED state; signaling could answer the call, but
media never became usable and the call timed out.

Moving the same operation earlier in answer handling did not solve the fault.
The validated placement is immediately after
`CallStateMachine.notifyOnEstablished()` in `ImsInCall.enter_InCall()`.

## BT1 boundary

`tools/transform_bt1_mt_vowifi_media.py` applies one fail-closed change to a
hash-pinned `ImsInCall.smali` input. The new SAE update runs only when all of
the following are true:

- the previous state is Samsung's incoming-call state;
- registration is present and reports IWLAN / RAT 18;
- CMC type is zero;
- call type is ordinary voice (`1`).

The transformer verifies the class, superclass, exact input hash, unique
method and ESTABLISHED anchor. It also proves that unrelated methods are byte
unchanged and rejects partial or repeated application. The public repository
contains only this project-authored transform, its contract and synthetic
tests; it does not contain the Samsung input, decoded tree, transformed smali,
or APK.

## Reproducibility and runtime identity

Two clean pin-discovery runs produced identical public-builder output:

- `classes.dex`:
  `cd8be33628bfabeafe77e78c58bf13ba8207e0eba41718845dcf116a8594cfe2`;
- `classes2.dex`:
  `b9d57c1a1aab37fd88a5443bde177c710897b1603481350e8037cf332ce0d325`;
- aligned unsigned APK:
  `832ad6fca643791a19776be14cb11ad6d1395bfe3d128e058dc4442e703990a9`.

The locally integrated APK used for the successful device test had SHA-256
`2c95f0af40720cefe13c20884722004daa8eb0d35c2a2eeaed44197103a524b3` and
primary DEX SHA-256
`ad4d3cc7045e0cc4ee5b87ffd438cad5c030627182010bea2f7767d97a33df4d`.
These values are evidence identifiers only; the private artifact is not
published. Packaging histories differ, so the public builder claims semantic
and structural reproduction of BT1, not byte identity with that ROM input.

## Settings behavior retained

BT1 does not change Android's default Wi-Fi Calling preference or Samsung's
SIM-identity reset behavior. Removing and reinserting a SIM may therefore turn
the user setting off, matching the existing Samsung logic. That behavior is
intentionally left unchanged.
