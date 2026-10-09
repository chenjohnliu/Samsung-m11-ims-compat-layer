# SIM phone-number display fix — 2026-10-09

## Confirmed cause

Read-only inspection of the connected phone's active subscription (subId 1,
slot 0) found:

| Android number source | Result |
| --- | --- |
| Legacy `number` | Empty |
| `phone_number_source_carrier` | Empty |
| `phone_number_source_ims` | Present, valid E.164 format |

No actual subscriber number is recorded in this document. No database, SIM,
phone setting or IMS registration data was modified.

Both Settings `PhoneNumberPreferenceController` and
`SimStatusDialogController.updatePhoneNumber` use SettingsLib `DeviceInfoUtils`.
Its old implementation only called `TelephonyManager.getLine1Number`, which
does not select the separate IMS-number source. Thus the existing valid IMS
number was available to Android but not used by these display paths.

## Minimal fix

`DeviceInfoUtils.getFormattedPhoneNumber` now uses Android 13's standard
`SubscriptionManager.getPhoneNumber(subId)` selection (carrier → UICC → IMS).
An empty result, unavailable subscription service or denied modern permission
falls back to the existing subscription-specific line-1 API. If neither is
available, the UI continues to show Unknown instead of inventing a number.
Invalid and DEFAULT subscription IDs are rejected to avoid querying a different
SIM. Multi-number display reuses the same formatter and selection path.

Settings already declares READ_PRIVILEGED_PHONE_STATE. No new permission,
public API, modem request, IMS callback, permanent override or SIM write is added.
The existing IMS URI callback bridge remains unchanged.

Applied source and tests in `/home/user/android/crdroid/frameworks/base`:

Local commit: `9ab7378926a37c4df25d5adc49694ac6e70534ab` on
`m11q-ims-checkpoint-20261009`. No push.

- `packages/SettingsLib/src/com/android/settingslib/DeviceInfoUtils.java`
- `packages/SettingsLib/tests/robotests/src/com/android/settingslib/DeviceInfoUtilsTest.java`

Replay patch: `platform/settingslib/phone-number-sources.patch` (paths relative
to frameworks/base). Use `git apply --check` first on the matching baseline.
For the already-patched current source, `git apply --reverse --check` confirms
the patch is present; do not apply it twice.

## Validation and delivery boundary

- 16 host source-selection/fallback assertions PASS, including IMS-only source,
  correct per-subscription fallback, no number, missing services, permission
  denial, service unavailability and invalid/default subscription IDs.
- Complete production DeviceInfoUtils compiles against the real public
  Android 33 API jar with existing JDK 11. Only R/annotation compile stubs used.
- Single/multiple display wiring checks PASS.
- Existing compatibility-layer host suite: 277 tests, 4 skipped, no failures.
- 11 additional Robolectric regression tests included. The Android Robolectric
  target was not run; host checks do not replace on-device UI acceptance.
- No Android ROM build, flash or device binary replacement was performed.

Repeat host validation without a ROM build:

```sh
python3 tools/test_phone_number_display.py \
  --android-root /home/user/android/crdroid
```

After the user's normal build and flash, reopen About phone and SIM status.
Confirm the real line number matches the subscriber's number. Check again after
reboot/IMS registration and with Wi-Fi disabled. Absence before first IMS
registration is expected if the SIM/carrier do not supply another source.
SIM removal/swap must not display another subscription's number.

This is a display fix. It does not change call audio, handover, SMS, IMS identity
or the status-bar VoWiFi glyph.
