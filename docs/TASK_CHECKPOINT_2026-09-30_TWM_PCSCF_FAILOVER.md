# Task checkpoint: TWM VoWiFi P-CSCF failover

Date: 2026-09-30 (Asia/Taipei)

## Latest continuation: comparison complete; debug CC gate fixed in source

See `IMS_5065_PASS_FAIL_COMPARISON_20261001.md`. The matching private pass
archive now independently corroborates all seven calls through Telecom ACTIVE.
All 14 policy-layer snapshots confirm stable W2L disallow, no higher overrides;
all have one current IMS bearer and no pending teardown. Native UA/IPsec
cleanup ordering also matches the fail, and later pass calls use the very same
selected proxy/list as the fail. No fixed wrong P-CSCF or obvious old tunnel
residue is demonstrated; addresses/SAs/UA and broader attach epoch remain
confounded. Default internet cause-33 in the fail remains a correlation only.

Raw logcat ends at 21:58:11 with empty stderr, so the third-cycle gap is real
and its cause unknown. Five telephony service dumps also timed out at 10 s;
their slot-0 network sections exist, but header flags do not imply full dumps.
Do not infer clean retry/manager state from missing tails.

No IMS behavior fix or rollback is justified yet. Separately, source audit
found crDroid's generic Java Build.TYPE spoof defeats the intended debug-ROM
CC gate; a narrow root+real-userdebug/eng gate repair is now applied in
TelephonyShellCommand only. It is NOT a 5065 fix and sets no policy. See
`IMS_CC_DEBUG_BUILD_GATE_20261001.md`: syntax parse, 10-case host predicate
test, exact applied hash and patch/diff checks pass. The user must build/flash
the edited TeleService component in a userdebug ROM and then perform only the
root/property/CC get-value batch. No automatic builds or device writes occurred.
True handover and H1-H3 remain unvalidated. If 5065 recurs later, compare one
captured IMS-only Wi-Fi rebuild before airplane recovery; do not force blind
repeats now. Collector default outer dump timeout remains 10s; 30s is an explicit
stable-state-only option, with timeout flags instead of complete-dump claims.
Work pauses for that user-owned build/read-only result. Do not initiate another
round or enable mode B while waiting.

## Earlier continuation: seven-call cycle pass; private comparison pending

See `IMS_HANDOVER_ROUND1_20261001_BASELINE_PASS.md`. The 2026-10-01 evening
bundle confirms the round-1 jar and seven user-reported connected calls, five
with directly logged ESTABLISHED events. Captured transitions used disallowed
W2L/fresh WWAN and NOT_IN_SERVICE L2W/fresh IWLAN, not true handover. The prior
487/AAA 5065 failure remains intermittent and unresolved; H1-H3 are not passed.

Continuous logging stops at 21:58:09 before the third cycle completes. Actual
PhoneFactory/DataNetworkController dump flags are true, but all `cc` policy
queries were denied. Root/non-user gate failure cause is unverified; stock
fingerprint is not build type, and the host product is userdebug. The collector
now records unmerged policy layers without gated cc commands, build-type/root
identity, and log boundary/stderr health. Host mock/syntax/redaction checks pass.

Default internet remained connected in the new pass, unlike the cause-33
default-data failures in the earlier fail; correlation only. Next action:
obtain this pass run's existing matching PRIVATE_FULL_CAPTURE.tar.gz, compare
network/native state and logger stderr with the fail. No new build, test,
reboot, speculative source fix or rollback is requested. Pause for archive
delivery. The older pending-capture instructions below are superseded.

## Earlier continuation: read-only history capture, no new ROM build

See `IMS_5065_NEXT_DIAGNOSTICS_20261001.md`. The governor receives 487 rather
than the private 503/5065 reason, and its existing path does not initiate
recovery. This explains the lack of automatic repair, not the initial
rejection. No speculative 487 reset patch was added.

The collector now includes the actual PhoneFactory/DataNetworkController
dump via TelephonyDebugService, plus build/component identity, handover
policy and native IMS-menu prerequisites. Source confirms this dump includes
recently disconnected networks and can recover the previously missing L2W
history without another reproduction. Host mock/syntax/redaction checks pass.
Next user action: one `current_state` snapshot in manual handover mode with
the updated collector; return matching shared/private archives. No build,
flash, call, toggle or reboot is required. Pause pending that batch.

`cmd phone ims disable/enable` is not a useful experiment: Samsung inherits
empty callbacks. The stock native manual-profile IMS-PDN reset exists, but
the current product does not include its ImsSettings/Samsung Dialer UI;
device-side prerequisite availability is not yet known.

## 2026-10-01 runtime feedback: stop further handover trials

Version question resolved: the user's phone screenshot shows the installed
`telephony-common.jar` SHA-256 exactly matches the new round-1 host product
jar (`bf08f49f04497a8f3efb51711cce35a11caae9d2bfbae1e34c9388fa80e14504`).
An old installed telephony jar is ruled out. The matching private capture
also confirms the same selected P-CSCF before failure and after airplane
recovery, with new IMS addresses/security associations/user-agent after
recovery; these covary and do not isolate the root cause. No new build or
reflash is indicated for version verification. Earlier uncertainty below
is superseded by this confirmation.

The supplied baseline capture shows the stable disallowed IWLAN-to-EUTRAN
policy followed by successful NORMAL WWAN IMS setup and LTE registration,
but two calls received 487 / private AAA 5065. Airplane mode recovery restored
calling. This is a failed regression control; the fresh-bearer workaround is
not a guaranteed remedy. Round-1 patch installation and its role in the
failure are unverified. No new ROM source change or rollback was made.
See `IMS_HANDOVER_ROUND1_20261001_BASELINE_FAILURE.md` for timestamped evidence
and the requested existing private-capture subset. Do not build another
experimental revision or advance mode B before reviewing that evidence.

## Current handover round supersedes the BU1-only next steps below

The user expanded the objective to correct the handover flow: usable IMS calls
after successful transfer, no stale/pending state after rapid reversal,
automatic fresh-bearer recovery after failure/timeout, and no regression of
the validated 5065 workaround. See `IMS_HANDOVER_ACCEPTANCE.md` for full gates
and `IMS_HANDOVER_ROUND1_VALIDATION.md` for the current source changes and the
single-build validation batch.

Round 1 is installed in the WSL crDroid telephony source: DataNetwork per-attempt
callback identity, timeout source cancellation/retry termination, diagnostic
logs, and three new DataNetworkTest cases. The stable CarrierConfig overlay
and BU1 timer are unchanged. Java syntax parsing and git diff checks passed;
Android tests and device validation have not run. Native callback generation,
orphan target bearer cleanup, and 487/5065 under true handover remain unverified.

The user explicitly owns ROM build, flashing, and device validation. Work must
pause after this source/static-check round and resume only when the user
returns results. Do not continue investigation during that wait.

This file is the handoff checkpoint for continuing the investigation with
`gpt-6.1-sol`. Continue from this state; do not restart the analysis or repeat
the completed collection.

## Current objective

Fix the intermittent condition where cycling Wi-Fi leaves VoWiFi unavailable
or calls temporarily unable to start. The current experiment is deliberately
limited to Taiwan Mobile (`TWM_TW`, PLMN 46697). If runtime testing succeeds,
the user wants a later, separately reviewed change covering all supported
Taiwan carriers.

This experiment does not yet attempt active-call Wi-Fi-to-LTE seamless
handover. It addresses slow IMS re-registration after a Wi-Fi transition.

## Root-cause status

### Confirmed from the 2026-09-29 capture

- The IWLAN IMS bearer (DN-120) completed setup immediately, remained
  connected, and retained the same address fingerprint.
- Samsung IMS received the AKA challenge for the first REGISTER.
- The authenticated REGISTER path switched to TCP port 5067.
- The first user agent produced no subsequent send/result before Samsung IMS
  reported `708 TimerF Timeout` at `2026-09-29 23:27:40.237`.
- `dumpsys secims` showed P-CSCF index 0 of 2, Timer F behavior corresponding
  to 128 seconds, and a 30-second registration retry base.
- After the timeout and retry delay, the governor advanced to P-CSCF index 1;
  the second user agent registered successfully on the same IWLAN bearer.
- Decompiled stock profile data uses Timer F `128000` ms. The TWM normal IMS
  profile inherits that default and also inherits the 30-second retry base.

### Supported conclusion

The reproduced failure is not an IWLAN bearer setup failure. The first TWM
P-CSCF/TCP registration path blackholes, and Samsung IMS waits about 128
seconds before failover, then waits another 30 seconds before retrying the
second P-CSCF. This explains recovery around 158 seconds and the apparent
temporary inability to place calls after Wi-Fi cycling.

Data handover may still have separate defects, but it is not the cause
demonstrated by this capture.

## Implemented experiment: BU1

Transformation ID: `BU1-twm-pcscf-failover-trial`

- Target: normal `TWM Mobile VoLTE` profile only.
- SIP Timer F: `128000` ms to `16000` ms.
- Registration retry base: unchanged; continues to inherit 30 seconds.
- Excluded: TWM emergency profile, CMC, other carriers, eligibility policy,
  global TCP sysctls, and governor smali.
- Expected reproduced-failure recovery: approximately 16 + 30 = 46 seconds,
  instead of approximately 128 + 30 = 158 seconds.

Files added or changed for BU1:

- `tools/transform_bu1_twm_pcscf_failover.py`
- `devices/m11q/bu1-twm-pcscf-failover-trial-contract.json`
- `tests/test_transform_bu1_twm_pcscf_failover.py`
- `tools/build_imsservice.py`
- `devices/m11q/imsservice-build.json`
- `tests/test_build_imsservice.py`
- `docs/BU1_TWM_PCSCF_FAILOVER_TRIAL.md`

The three already-modified documents below predated BU1 work and belong to the
user. Preserve their changes and do not overwrite them casually:

- `docs/CRDROID_ANDROID13_IMS_RESTORATION.md`
- `docs/M11_ANDROID13_ROM_BRINGUP.md`
- `docs/PUBLIC_RELEASE_SOP.md`

## Candidate and validation state

Candidate APK:

`out/bu1-trial/imsservice-bu1-unsigned.apk`

SHA-256:

`4cf9360b609fcc45329d038835a5913ba9c76844fe4cf59b70c132f904ae0dd1`

Validated properties:

- only `res/raw/imsprofile.json` is newly changed relative to the preceding
  strict local IMS candidate;
- `classes.dex` remains
  `cd8be33628bfabeafe77e78c58bf13ba8207e0eba41718845dcf116a8594cfe2`;
- `classes2.dex` remains
  `b9d57c1a1aab37fd88a5443bde177c710897b1603481350e8037cf332ce0d325`;
- zipalign verification passed;
- final apktool re-decode passed;
- final decoded TWM normal profile has Timer F 16000 ms and no local
  `reg_retry_base_time` override;
- full Python suite passed: 139 tests, 1 skipped;
- `git diff --check` passed.

The full public builder was not rerun because the required local
`framework-minus-apex.jar` could not be found. The candidate was produced by
exact raw ZIP-entry replacement against the already validated strict APK, then
zipaligned and fully re-decoded. Do not claim a complete clean-room builder run
until that framework artifact is supplied and the strict builder succeeds.

## Repository and local payload state

Compatibility repository:

- path: `D:\m11q\Samsung-m11-ims-compat-layer`
- branch: `main`
- starting HEAD: `082b9311105349af6f490f61bff01c7b95049310`
- BU1 changes are uncommitted and unpushed.

Local crDroid device tree:

- path: `/home/user/android/crdroid/device/samsung/m11q`
- branch: `m11q-volte`
- local IMS payload was updated to the candidate hash above at
  `ims/proprietary/priv-app/imsservice/imsservice.apk`.
- `ims/proprietary/` is intentionally ignored by `ims/.gitignore`, so this APK
  replacement does not appear in `git status`.
- `ims/Android.mk` uses `LOCAL_CERTIFICATE := platform`; the user's ROM build
  will sign the payload.

No Android ROM build was run. Project instructions require the user to build
manually.

## Required next action: user runtime validation

The user must build and flash once, then collect one consolidated validation
batch:

1. Confirm LTE IMS registration and an ordinary LTE call.
2. Enable Wi-Fi and wait for VoWiFi registration.
3. If P-CSCF index 0 blackholes, record the timestamp of `708 TimerF Timeout`,
   the P-CSCF index change, and successful registration on index 1.
4. Place the 188 test call only after VoWiFi registration.
5. Repeat LTE-to-Wi-Fi registration at least three times, including one Wi-Fi
   off/on cycle after a successful VoWiFi call.
6. Capture `dumpsys secims` and Samsung IMS/logcat data covering the full batch.

Interpretation:

- Timeout near 16 seconds, followed by index-1 success after the existing
  approximately 30-second retry: BU1 loaded and the causal model is confirmed.
- Timeout still near 128 seconds: investigate Samsung IMS profile database or
  cache precedence/versioning; do not shorten another timer blindly.
- New 16-second failures on an otherwise healthy primary P-CSCF, LTE/VoWiFi
  registration regression, or call regression: revert BU1.

## After a successful runtime result

1. Consider a second TWM-only experiment reducing registration retry base from
   30 seconds to 15 seconds. Keep it as a separate causal change.
2. Inventory the exact normal IMS profiles for Taiwan carriers (expected PLMNs
   include 46601, 46605, 46692, and 46697) before generalizing.
3. Apply only to eligible normal voice profiles; continue excluding emergency
   and CMC profiles.
4. Add carrier-specific tests and obtain runtime evidence before calling the
   all-Taiwan change complete.
5. Commit/push only when the user explicitly requests it for this BU1 round.

## Safety and project constraints

- Do not run Android ROM build commands; the user builds manually.
- Preserve unrelated dirty worktree changes.
- Keep confirmed evidence, inference, and unverified hypotheses distinct.
- Do not broaden BU1 to all Taiwan carriers before the current TWM runtime
  experiment passes.
