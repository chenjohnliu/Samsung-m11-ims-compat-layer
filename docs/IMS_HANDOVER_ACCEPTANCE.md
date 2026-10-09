# IMS handover completion criteria and work plan

## Active objective — supersedes the earlier H1-H3 scope

Updated 2026-10-01 (Asia/Taipei), at the user's explicit request: preserve an
already established ordinary VoWiFi call when walking out of Wi-Fi coverage
or losing Wi-Fi, automatically moving that same call to VoLTE. This iteration
is **W2L only**. L2W continuity, rapid reversals, generalized recovery and
Taiwan-wide handover rollout are not completion requirements for this iteration.
The initial validation carrier remains Taiwan Mobile (46697).

The user performs builds, flashing, reboots and device tests. Pause at those
boundaries. The earlier CC debug-gate repair should accompany the functional
experiment in one build; do not require a separate gate-only build milestone.

Acceptance requires correlated evidence of all of the following:

1. The original ordinary voice call is established over IWLAN before the edge.
2. An automatic weak-Wi-Fi or Wi-Fi-loss event selects LTE, and the framework
   attempts a real HANDOVER setup, rather than teardown plus NORMAL setup.
3. The LTE target succeeds before ordinary source teardown; the Samsung IMS
   handover path preserves the original call rather than deregistering and
   initiating a replacement call. If a lower-layer loss occurs earlier, record
   that ordering instead of labeling a fresh registration as continuity.
4. The same Telecom/native call session stays active, and the user confirms
   two-way audio continues without redialing. A brief audio gap must be reported,
   not hidden behind the word seamless. A VoLTE icon or RESULT_SUCCESS alone
   is insufficient.

Validate gradual signal loss and explicit Wi-Fi-off separately, with working
LTE coverage. Do not place emergency calls. Collect continuous logs across the
edge; avoid heavy TelephonyDebugService dumps while timing the transition.

Current source-level evidence: the decoded Samsung AP-assist provider forwards
START_HANDOVER to EpdgHandler.handleHandoverStart(), which sends message 1 to
the source CID's state machine. ConnectedState enters W2MInProgressState
without the legacy isW2LRecommended() guard on this entry. Target success is
forwarded as HANDOVER_SUCCESS, distinct from ordinary source detachment. This
is an existing candidate continuity path, not proof that the modem or carrier
will preserve the call. Do not force the legacy W2L trigger in AP-assist mode.

The previously captured pass and fail cycles used the stable disallow policy;
neither establishes active-call handover success. After the user exported the
current controller and overlay, a guarded active-call W2L candidate was
prepared. WSL access recovered on 2026-10-02; the candidate is now applied to
the actual source, with matching hashes, 34 host helper cases and a full-file
Java syntax parse. No ROM build or device continuity validation was run.
See `IMS_ACTIVE_W2L_EXPERIMENT_20261002.md` for exact scope, validation status,
source hashes and the consolidated manual build/test handoff.

The remaining text records the **historical**, broader plan. Its H1-H3 tests
and work order must not be used to expand the active objective above.

Accepted objective (2026-09-30, Asia/Taipei): handover succeeds and calls work;
rapid reversal leaves no stale state; failures automatically rebuild a bearer.

The initial device/carrier validation target is Samsung M11 on crDroid Android
13 with Taiwan Mobile (46697). Taiwan-wide rollout remains part of the later
rollout work and cannot be described as validated using only a TWM result.

## Completion gates

| Gate | Required behavior | Evidence that proves it |
| --- | --- | --- |
| H1: Successful handover and usable calls | Both LTE-to-IWLAN and IWLAN-to-LTE transfer the IMS bearer successfully. Following the transfer, outgoing and incoming calls connect and have two-way audio. An ongoing ordinary voice call survives the transfer. | Correlated source/target setup, successful transfer, IMS access registration, SIP call establishment, Telecom ACTIVE, and user-confirmed two-way audio. Repeat 10 idle transitions per direction plus 3 active-call transitions per direction with no failed call or stale dialing state. |
| H2: Rapid reversal | Reversals at 1, 3, and 5 seconds during setup, handover, or registration converge to the last available/preferred transport. Previous requests, replies, timeouts, and retry entries cannot change the current bearer or registration afterward. | Per-attempt callback correlation and deterministic delayed-response tests; 5 reversal sequences at each interval on device, successful call after convergence, and no subsequent transport flip/retry storm during a 60-second stable window. |
| H3: Automatic fresh-bearer recovery | If handover fails or times out, obsolete work is cancelled, the system selects the current preferred usable transport, and a fresh IMS bearer is created when continuity cannot recover. Registration and a subsequent call recover without airplane mode, reboot, or user toggling. | Tests for target setup failure, source notification timeout, target response timeout, late success, and preference reversal; device trace showing new normal SETUP_DATA_CALL/bearer, IMS registration, and a working call after recovery. |

During a healthy H1 transition, teardown followed by fresh setup is not proof
of continuity. For H3, dropping a call after the source and target become
unusable is permitted, but automatic subsequent recovery remains mandatory.
Emergency and CMC behavior must remain excluded from new ordinary-call
recovery logic. Routine validation must not place emergency calls.

Initial performance targets: after the final network preference stabilizes,
healthy registration should converge within 15 seconds; after handover failure
is reported, fresh-bearer recovery should finish within 60 seconds when the
network accepts setup/registration. These are experimental targets, not
measured guarantees; carrier-directed throttling must be logged and respected.

Neither a VoWiFi icon nor RESULT_SUCCESS alone passes any gate. Source tests
also cannot establish carrier compatibility or active-call media continuity.

## Current evidence and gaps

- The stable overlay disallows IWLAN-to-LTE IMS handover for 46601, 46605,
  46692, and 46697, forcing a new bearer. Therefore H1 is not achieved.
- Earlier allowed handover completed data transfer and LTE IMS registration,
  but subsequent calls received carrier 487 / AAA 5065. The same P-CSCF worked
  after fresh bearer setup. The underlying stale UE/modem/carrier binding is
  still unresolved.
- The installed BU1 APK contains the expected F:16000 resource and unchanged
  DEX entries. The 2026-09-30 event history had three approximately 8-second
  IWLAN registrations and one registration interrupted by rapid switching.
  It had no Timer F timeout proving the runtime timer value.
- Source audit found that DataNetwork handover timeout does not notify the
  source data service via cancelHandover. Handover responses also lack an
  individual attempt identity, so a response from a timed-out attempt could
  be handled in a later HandoverState. This is a source-level hazard, not yet
  a demonstrated explanation for the reported icon delay or AAA 5065.

## Work order

1. Repair and test DataNetwork callback-attempt identity and timeout cleanup.
2. Audit Samsung ePDG W2L/L2W request, abort, completion, and callback contracts
   against the Android data-service contract.
3. Correlate transport preference, bearer identity, Samsung IMS registration,
   and SIP call outcome in one capture. Resolve the 487/5065 continuity defect.
4. Prepare a TWM-only handover experiment with automatic fresh-bearer fallback;
   keep a recoverable stable policy and avoid changing BU1 timers concurrently.
5. Ask the user to build/flash once and run the consolidated H1-H3 batch.
6. Evaluate each gate independently and revise the fix where evidence fails.
7. Roll out to the other supported Taiwan carrier profiles after appropriate
   carrier validation; do not infer runtime success from profile eligibility.

The user performs Android ROM builds. Agents may edit source and perform
non-build checks. Completion remains unproven until H1-H3 pass on device.
