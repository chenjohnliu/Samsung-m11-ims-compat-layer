# Restore the intended root/debug CarrierConfig test gate

Date: 2026-10-01 (Asia/Taipei). This is a diagnostic/test-entry repair, not an
IMS calling, 5065, or handover-continuity fix. No CC override is executed.

Scope update: the user now requests an active-call W2L continuity experiment.
Combine this gate repair with the functional handover changes in the next
manual build. The gate-only validation below is historical guidance, not a
required separate build/flash stage. Do not pause functional implementation
merely to collect another stable-policy call cycle.

## Source evidence

Local crDroid applies generic PixelProps `Build.TYPE=user` before package
filtering, through Instrumentation's application initialization. The phone
process normally initializes TelephonyUtils later, whose IS_USER flag reads
that mutable Java Build.TYPE. Consequently a real userdebug ROM can reject
root `cmd phone cc` as though it were user. The host product's system property
is userdebug; root captures returned Permission denied. The exact running
base-framework/initialization state is still not directly measured.

See `IMS_5065_PASS_FAIL_COMPARISON_20261001.md` for the pass/fail evidence and
the separate source-level spoof/access analysis. Do not use the stock Samsung
fingerprint to infer real build type.

## Narrow change

WSL source repository:
`/home/user/android/crdroid/packages/services/Telephony`.

Only `src/com/android/phone/TelephonyShellCommand.java` is newly changed:

- Keep the root Binder UID requirement.
- Read `ro.build.type` through SystemProperties, not spoofable Build.TYPE.
- Allow only explicit `userdebug` or `eng` values. User, absent, unknown, null
  or other values fail closed; non-root callers always fail.
- Apply this predicate only to the existing CC command gate. Do not change
  TelephonyUtils globally, PixelProps spoofing, other phone commands, carrier
  arrays, or IMS/data-network paths. Get/set/clear operations continue to share
  the same gate, just as before.

Artifacts are under `D:\m11q\work\cc_debug_build_gate_20261001`:
baseline, candidate/applied source, `cc_debug_build_gate.patch`, predicate host
test and static-validation results. Existing dirty `res/values/config.xml`
and `CarrierConfigLoader.java` changes are preserved. Nothing was committed,
pushed, built as an Android ROM, flashed, or executed against a phone.

Applied source SHA-256:
`53ba39e969d5729d2ba62277929ace9387cdc7b392e0dbd35feb33e4fcade997`.
Final patch SHA-256:
`8b09f4f1e9a7f9bb8bfc4c4063489098cb2ca4ad079dcbb1e20855ef91d10836`.

Non-build validation passed: full-file `JavacTask.parse()` syntax-only check,
10-case host UID/build-type truth matrix, exact candidate/applied source and
predicate matching, `git diff --check`, and reverse patch applicability.
The host harness tests the extracted predicate with a ROOT_UID constant stub;
it is not an Android integration/unit-test run or a full Android compile.
See the local artifact `VALIDATION.md` for detailed results and baseline hash.

## User-owned validation batch

This change is in the TeleService phone application, not telephony-common.jar.
The previously confirmed jar hash alone cannot identify this new gate revision.
Include the edited Telephony service source in the next manual **userdebug**
ROM build, flash normally and reboot. Agents do not run the ROM build.

Then run only this read-only batch in Termux:

```sh
su -c 'id -u; getprop ro.build.type; cmd phone cc get-value -s 0 iwlan_handover_policy_string_array'
```

Expected: UID `0`, build type `userdebug` (or deliberately built `eng`), and
the existing policy array beginning with the IMS IWLAN-to-EUTRAN disallow rule.
Do not run set/clear commands or change the stable policy in this validation.

Decision:

- Root + debug type + readable existing array: test gate works; return output
  before choosing a reversible true-handover experiment. This does not pass H1-H3.
  If the policy differs from the prior pass run, record it and do not overwrite it.
- Real property `user`, missing or unknown: denial is correct; do not spoof
  the property or relax the production gate. Confirm the manual build target.
- UID not 0: resolve root invocation; build type alone is insufficient.
- UID 0 + actual debug property but still denied: compare installed
  com.android.phone APK with the new product and actual running process before
  changing another gate. Do not blindly rebuild or mutate policy.

No additional Wi-Fi cycles, calls, airplane resets or forced 5065 reproduction
are required for this entry-point check. Work pauses for the user's build and
results. The underlying intermittent 5065 and true handover remain unresolved.
