# Stage 2 VoWiFi handoff

Date: 2026-09-13

## Scope

This note hands the VoWiFi follow-up to a separate task. The current task did
not change CarrierConfig, Settings, Samsung IMS profiles or ePDG behavior.

## Confirmed evidence

### Stock CWK3

- The same M11 and TWM SIM displayed the VoWiFi icon while Wi-Fi was connected.
- Samsung IMS established an ePDG tunnel and registered IMS over IWLAN/RAT 18.
- The registered service set included `mmtel` and `smsip`.
- This confirms that the device, stock vendor IMS stack and tested subscription
  can support VoWiFi. It does not establish support for every carrier.

### Current Android 13 custom ROM

- Wi-Fi was connected, but Samsung IMS reported no ePDG connection.
- IMS remained registered over LTE/RAT 13 rather than IWLAN.
- CarrierConfig reported `carrier_wfc_ims_available_bool=false` and
  `carrier_default_wfc_ims_enabled_bool=false` for the active subscriptions.
- The AOSP Wi-Fi Calling preference was therefore unavailable; this was not
  merely a visible-menu problem with working VoWiFi underneath.
- Samsung configuration still contains VoWiFi/ePDG-related implementation and
  icon support.

## Interpretation

The missing UI is currently explained by the Android carrier-availability
gate, while the runtime transport confirms that the custom ROM has not entered
VoWiFi. Stock runtime evidence rules out a blanket claim that the M11 lacks
VoWiFi support.

Enabling only MCC/MNC 46697 would be a useful controlled validation but is not
an acceptable final multi-carrier design. Conversely, enabling Wi-Fi Calling
unconditionally for every SIM may expose a non-functional option for carriers
whose Samsung profile, entitlement, APN or ePDG policy does not support it.

## Recommended design

1. Enable the M11 device-level WFC capability independently of any one carrier.
2. Inventory the bundled Samsung CSC/IMS profiles for carriers that declare
   Wi-Fi/ePDG `mmtel` service.
3. Add carrier-scoped Android CarrierConfig entries for that supported set,
   starting with 46697 because it has a stock runtime baseline.
4. Keep unknown carriers fail-closed until profile or runtime evidence exists.
5. Keep the carrier mapping data-driven and extensible; do not hard-code TWM as
   the only supported carrier in IMS bridge source.
6. Do not force the Settings preference visible without also satisfying the
   Android platform and Samsung IMS/ePDG gates.

## Runtime validation gates

For each carrier added to the supported set:

1. Confirm the Wi-Fi Calling preference appears and its state persists.
2. Confirm ePDG connects and IMS registers over IWLAN/RAT 18.
3. Place and receive a call with clear two-way audio and clean teardown.
4. Verify hand-back to LTE/VoLTE after Wi-Fi is removed.
5. Recheck LTE VoLTE and IMS SMS so WFC changes do not regress the completed
   Stage 2 behavior.
6. Record unsupported or entitlement-blocked carriers without weakening the
   default fail-closed policy.

## Status classification

- Confirmed: stock VoWiFi works for the tested M11/TWM combination; current
  custom CarrierConfig disables WFC availability; current custom IMS remained
  on LTE with ePDG disconnected.
- Inferred: adding correct device and carrier declarations is the minimum path
  to expose the AOSP setting and begin custom-ROM ePDG validation.
- Unverified: the exact source overlay location, behavior for other carriers,
  entitlement requirements, and custom-ROM IWLAN call stability.

No VoWiFi source fix or runtime claim is included in the current Stage 2 SMS
candidate.
