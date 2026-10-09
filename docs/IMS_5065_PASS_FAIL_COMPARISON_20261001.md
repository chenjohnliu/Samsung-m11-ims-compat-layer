# 5065 pass/fail comparison: ordinary rebuild can succeed or fail

Date: 2026-10-01 (Asia/Taipei). No carrier-policy or IMS/handover behavior change
was made on the basis of this comparison. A separate debug CC access gate
source fix is applied; it is not a 5065 remedy. H1-H3 remain unvalidated.

## Inputs and privacy

Matching pass private archive supplied by the user:
`C:\Users\user\Downloads\PRIVATE_FULL_CAPTURE.tar.gz`, SHA-256
`[private archive checksum omitted]`.
Extracted under `D:\m11q\work\ims_wifi_cycle_pass_20261001_761f3ef4\private`.
Phase names, timestamps, and retained calls match the shared pass run.

Fail comparison case:
`D:\m11q\work\ims_handover_round1_regression_20261001\private`.
See the earlier baseline failure/pass reports for their shared archive hashes
and installed round-1 telephony jar confirmation. Raw identities, IP addresses,
SIP subscriber identities and security keys remain outside Git and this report.

## Stronger confirmation of this run's pass

The final pass `cycle3_volte_after_call/telecom.txt` retains all seven outgoing
calls. Each has SET_ACTIVE followed by local user termination. In particular,
the two calls outside continuous logcat coverage are independently corroborated:

- Third Wi-Fi call: Wi-Fi call property at 21:58:25.192, SET_ACTIVE at
  21:58:25.812 (line 375), local termination at 21:58:30.926.
- Third LTE call: SET_ACTIVE at 22:00:55.270 (line 407), local termination
  at 22:01:01.056.

Thus all seven connected calls have system evidence, not just user-entered
results. Two-way audio and incoming-call tests are still not documented.

All 14 slot-0 CarrierConfig snapshots contain the IMS W2L disallow rule in
`mConfigFromDefaultApp`, with carrier-app, persistent and runtime override
layers null. The defaults have catch-all allow, but are overridden by that
default-app array. This supports the effective stable policy seen in DNC's
W2L decisions; no mode-B override was active.

All 14 DNC snapshots show one current IMS network on the intended transport,
alongside the same default internet DN-100-C, and an empty pending-teardown
list. Earlier IMS networks appear in the explicitly historical, disconnected
list, not as additional current bearers. The first snapshot's retained history
starts at 21:47 and shows the preceding L2W as teardown/fresh setup as well.
No attempt/callback/timeout marker identifies entry into the patched handover
state in the retained pass history. This does not reconstruct the fail run's
missing earlier DNC history.

## Native comparisons: what does not distinguish failure

The pass cycle-1 W2L at approximately 21:53:52 and the failed W2L at 12:35:04
both delete the old UA and four old IPsec SAs, receive native
`EVENT_DISCONNECTED error=ERIS_OK`, reach ePDG DisconnectedState, then establish
a NORMAL LTE IMS bearer on CID 2/rmnet_data1 and register a new UA.
Evidence: pass raw log lines 29091-32074; fail raw log lines 1253-4415.
The pass's earlier baseline W2L instead created CID 3/rmnet_data2; these are
distinct transitions and must not be conflated.

The pass LTE baseline has a different selected IPv6 proxy, but later pass LTE
epochs use the exact same four-entry P-CSCF list and index-0 selected endpoint
as the failed epoch. They still establish calls. A fixed wrong selected proxy
is therefore disfavored, not a sufficient explanation for 5065.
Evidence: pass baseline secims line 133, pass cycle-1 LTE secims line 141,
fail baseline secims line 61.

Both pass and failed LTE snapshots have one registered UA and four active SAs;
sampled XFRM error counters are zero. No extra active old UA/tunnel is visible.
Pass LTE address triples differ from the failed epoch. The failed epoch keeps
the same addresses/UA/SAs through both rejected calls; airplane recovery
rotates all and succeeds. These variables covary, so none is isolated as causal.
The configured subscriber SIP identity is unchanged between runs.

The actual call divergence occurs after provisional SIP progress:

- Pass: INVITE, 100, 183, then 180/200 and ESTABLISHED.
- Fail: INVITE, 100, 183, then 487 with Reason cause 503 and private AAA
  expected result 5065; retry repeats it on the same IMS epoch.

Local cleanup/registration success does not prove carrier-side access/session
ownership is correct. The logs still lack plaintext Contact/security/access
headers and SDP needed to demonstrate a particular binding mismatch.

Default internet remains connected throughout the pass. In the fail it was
rejected with cause 33 before airplane recovery. This strengthens a broader
epoch/attach-state correlation, but does not prove internet APN failure causes
IMS call rejection. CID/interface numbers differ and are not themselves faults.

## Diagnostic coverage defects, separate from IMS behavior

Pass raw logcat ends at 21:58:11.047; the filtered timeline's last event is
21:58:09.152. Logger stderr is empty. Missing third-cycle live events are not
caused only by redaction/filtering. No specific logger exit/kill cause is
established; do not call it an IMS/phone crash.

Five TelephonyDebugService snapshots have an explicit 10000 ms activity dump
timeout: cycle-1 LTE after call, and all four third-cycle snapshots. Header
presence is not complete dump coverage. In these files the slot-0 current,
pending and historical network sections are present, but later portions may
be missing. Treat absence of later manager/retry logs as unknown, not clean.

The collector now explicitly flags outer and inner dump timeouts. It retains
the 10-second outer default; a stable-state-only diagnostic may opt into
`IMS_CAPTURE_DUMP_TIMEOUT_SECONDS=30`. Native dumpsys supports `-t` seconds,
but this does not extend ActivityManager's separate 5-second TransferPipe
client timeout. Broad phone dumps run on the phone main thread and can perturb
timing: do not enable 30 seconds during handover/rapid-switch measurements,
and do not keep lengthening the timeout after another truncation.
Host-only syntax, redaction and mocked timeout/invalid-option checks pass.

## Separate source-level cause of denied CC test commands

Local crDroid `PixelPropsUtils.java` sets generic Build.TYPE to `user` and TAGS
to `release-keys` (lines 209-211) and applies them before all package filters
(line 278). Instrumentation calls this from newApplication before onCreate
(lines 1247/1265). PhoneApp initializes telephony from onCreate, while
TelephonyShellCommand is created later for a shell command. TelephonyUtils's
IS_USER is initialized from that mutable Build.TYPE, not the underlying system
property. Thus a real userdebug ROM can look like user to the phone's CC gate.

This directly supports the denial mechanism in the source; the precise runtime
initialization/flashed base-framework match is not independently proven. The
root collector reports uid=0 and no spoof reflection-failure log was found.
Do not infer runtime build type from the stock fingerprint or native vendor
components' own `build_type: user` debug strings.

The narrowly scoped correction uses `SystemProperties` for `ro.build.type`
only at the CC gate, allows explicit userdebug/eng values and still requires
root UID. Missing/unknown/user values deny. It does not change TelephonyUtils
globally, disable the spoof, modify carrier arrays, or execute any override.
The source fix is applied and host predicate/static checks pass. See
`IMS_CC_DEBUG_BUILD_GATE_20261001.md` for artifacts and user-owned build/flash
plus read-only validation. No actual override or device command was executed.

## Decision and next validation boundary

Do not revert callback guards or add speculative delays/reset-on-all-487.
The failed recorded path bypasses true framework handover, and matching local
cleanup/proxy configurations also work in the pass. The carrier code's exact
internal meaning and initial rejection cause remain unverified.

Before resuming a true-handover trial, validate the corrected debug-gate build
with the read-only root/property/CC batch in its source report. This distinguishes
the real build property from the spoofed Java Build.TYPE and verifies that the
reversible CC route is available. The check itself changes no overrides, build
type, radio or IMS settings. No repeated cycle batch is requested at this point.

If the 5065 state later recurs, the useful controlled recovery comparison is:
capture failure and an unchanged-state retry, then one user-performed Wi-Fi
on/off IMS-bearer rebuild without airplane mode, capture the resulting epoch
and retry once; only then use airplane recovery if still broken. End all calls
before switching, and record registration/results. A working fresh IMS epoch
would support recoverability without radio reset; continuing failure would
make broader attach/session state more plausible, not prove its cause. Failure
to create a fresh epoch would focus attention on cleanup. This is a proposed
future conditional experiment, not an executed test or evidence for H3's
automatic recovery. Do not ask for repeated blind cycles simply to provoke it.
