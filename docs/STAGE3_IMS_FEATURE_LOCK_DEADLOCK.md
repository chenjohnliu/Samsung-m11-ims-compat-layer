# Stage 3 ImsFeature lock-order correction

## Runtime finding

Clean-boot ANR traces showed an AB/BA lock inversion between Android's
`ImsFeature` lock and the bridge's `ModernVoiceContext` monitor:

```text
MmTelFeature.setListener()
  -> holds ImsFeature.mLock
  -> GoogleModernMmTelFeature.onFeatureReady()
  -> waits for ModernVoiceContext

ModernVoiceContext.ensureBackend()/publish()
  -> holds ModernVoiceContext
  -> ImsFeature.setFeatureState()/notifyCapabilitiesStatusChanged()
  -> waits for ImsFeature.mLock
```

This blocked `com.android.phone` while opening the MMTEL connection. A Settings
`isVoNrEnabled()` query then waited behind the phone main thread and surfaced as
a downstream Mobile Network Settings ANR.

## Correction

- `onFeatureReady()` and `onFeatureRemoved()` now enqueue context work on the
  bridge's main handler and return without acquiring `ModernVoiceContext`.
- Feature state and capability publication captures one immutable snapshot
  under the context monitor, then calls the Android framework from a handler
  runnable after releasing that monitor.
- A monotonically increasing publication sequence suppresses queued snapshots
  superseded before dispatch.
- SMS capability is included in the snapshot, so framework publication does
  not read back into context-owned state.
- Voice-message and capability-error callbacks likewise execute outside the
  context monitor.

Incoming-call publication remains outside the context monitor as required by
the independently runtime-validated Stage 1BJ fix.

## Scope

The change does not alter carrier matching, registration qualification,
service IDs, call-session ownership, IMS SMS routing, or VoWiFi configuration.
It requires a rebuilt APK and device validation; source and deterministic APK
checks are not a runtime pass.
