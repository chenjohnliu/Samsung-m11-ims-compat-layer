# Local IMS checkpoint and UI findings — 2026-10-09

User requested local commits only. **No push, Android ROM build or flash was performed.**
These commits preserve the bring-up source and experiments; they do not claim
that every historical opt-in experiment is enabled or accepted.

## WSL local commits

Root: `/home/user/android/crdroid`.

| Repo | Branch | Commit |
| --- | --- | --- |
| frameworks/base | m11q-ims-checkpoint-20261009 | `8f1bd8bc5969308e261f1ad2a8d55a8c0f0fa503` |
| frameworks/opt/net/ims | m11q-ims-checkpoint-20261009 | `f4c719f119848dbfeeca2c214cedd13cb4fd076a` |
| frameworks/opt/telephony | m11q-ims-checkpoint-20261009 | `2832747fc1e92bc34ae740b6f09957620d23d715` |
| packages/services/Telecomm | m11q-vowifi-audio-path | `f56395ffb3f9854963b87174ca403bed43b8ffc3` |
| packages/services/Telephony | m11q-ims-checkpoint-20261009 | `04cde10d1966ba35d1fb8fc2193867283465c487` |
| system/netd | m11q-ims-checkpoint-20261009 | `91016fbe38db8c2bc08f7476c173648a5124c526` |
| device/samsung/m11q | m11q-volte | `91604fa9331465d0d0457c0a0ebffa8faa44c9d5` |

All seven checkouts were clean after committing. Previously detached checkouts
now have a local checkpoint branch so their commits are not left unreferenced.
No upstream remote or manifest revision was changed. The five upstream-only
repos still need a publication destination before any later push.

The compatibility-layer main commit containing this document preserves build
contracts, transformations, bridge/audio sources, regression tests and findings.
BH1/BP1/BR1 SMS sources were already tracked; they remain in the commit ancestry.
`tools/diagnostics` now contains source-only copies of the external collectors,
packet summarizer, host helper/tests and read-only repository audit script.
The original external copies were not deleted.

Excluded: kernel build-compatibility changes, local compiler installations,
private captures/PCAPs, Samsung input binaries, generated APK/JAR/DEX files,
keys and local backups. The original audit document describes the earlier
pre-commit state, not the state after this checkpoint.

## Validation

- Python host regression suite: 277 tests, 4 skipped, no failures.
- Copied media collector: host syntax/mock/interface/collision/opt-in checks PASS.
- Seven WSL repos: whitespace checks passed before commit; clean after commit.
- Earlier SA2 full standalone Java compile and SA2/SEH host/source gates passed.
- No new on-device all-carrier acceptance is claimed; the phone still needs the
  user-built updated product and normal product verification before testing it.

## Phone number shown as Unknown

Read-only live inspection found the active subscription's legacy `number`
field empty. This is not by itself evidence of an IMS registration or call fault.

Actual Settings path:

`SimStatusDialogController.updatePhoneNumber` →
`DeviceInfoUtils.getBidiFormattedPhoneNumber` →
`TelephonyManager.getLine1Number`.

Settings intentionally displays Unknown for an empty result. An empty stored
number alone does not prove that the SIM physically lacks EF-MSISDN data;
that would require separate UICC evidence.

Android 13 also provides `SubscriptionManager.getPhoneNumber`, selecting carrier,
UICC and then IMS sources. `ImsPhone` already extracts a validated E.164 number
from subscriber-associated IMS URIs. The existing ModernVoiceContext bridge
already forwards `onSubscriberAssociatedUriChanged` when registered; this is
not a missing API to invent.

A possible follow-up is to inspect the IMS-number source (redacted), then use
the standard newer number API in this Settings display with the legacy fallback.
Whether that helps depends on a genuine number being available from the network;
do not derive one from IMSI, invent a number, or write one into the SIM/database
merely to make the UI nonempty. No number-display code or phone data was changed.

## VoWiFi versus telephone-with-Wi-Fi icon

The current crDroid SystemUI explicitly selects `R.drawable.stat_sys_vowifi`
for one active subscription in `NetworkControllerImpl`. `StatusBarImsView`
shows this VoWiFi drawable instead of the VoLTE drawable when VoWiFi is available;
it does not add a separate second telephone-with-Wi-Fi status icon.

`MobileSignalController.isVowifiAvailable` requires voice capability and IMS
registration plus IWLAN data type or Wi-Fi-calling availability. The glyph is
a ROM UI choice, not proof that an ongoing call is on IWLAN. Missing a separate
telephone glyph alone is not a handover/media failure. In-call Dialer indication
is a separate UI path and should not be conflated with the status-bar glyph.
No icon/UI code was modified, and CherishOS's exact drawable was not compared.
