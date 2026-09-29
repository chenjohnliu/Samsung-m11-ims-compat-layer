# crDroid Android 13 IMS source restoration

Status snapshot: 2026-09-29. The source changes below were restored in the local
crDroid checkout at `/home/quokka/android/crdroid` and manually built/flashed by
the user. A static comparison against the nine known runtime patch groups in
the public CherishOS forks found their production changes in the crDroid source
trees; no missing patch from that known set was identified. This does not prove
that no other private or undiscovered patch exists, and it does not make the
manual port reproducible from a clean checkout.

Runtime validation remains partial. Direct LTE 188 and an outgoing VoWiFi call
worked in earlier tests. Before the handover-policy workaround, an outgoing
188 INVITE after a WFC-to-LTE transition received SIP 487. The callback cleanup
is built/flashed and clears the failed-call UI,
but does not fix that signaling failure. The M11/Taiwan Mobile idle-transition
policy now forces a fresh WWAN IMS bearer and was confirmed on PLMN 46697; it
deliberately drops an active VoWiFi call when Wi-Fi is turned off. Separately,
the same BT1 APK that passed the CherishOS test initially left incoming VoWiFi
silent on crDroid. Runtime ordering showed BT1 selecting SAE before Telecom
entered `MODE_IN_CALL`. A gated crDroid Telecom callback now repeats Samsung's
slot-aware audio-path start immediately after that mode transition. The user
validated outgoing 188 and incoming VoWiFi calls with audible media and normal
teardown. These results remain scoped to the tested build and do not establish
complete cross-ROM support. CherishOS 4.12 results remain separate.

The stable carrier-policy fix is public in device-tree commit
[`d11cbe58`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/d11cbe58dfdf81c284788c50e5b6e37de47cf5d4)
on branch `m11q-volte`. The native active-W2L experiment was fully reverted;
the published CarrierConfig rule is the current workaround.

## Purpose and portability boundary

This record separates the ROM-independent Samsung IMS compatibility APIs from
the Android framework, Telephony, netd, product, and SELinux integration needed
by a particular ROM. The target of this restoration is crDroid 13 / Android 13
on `m11q`. The runtime notes below are a partial result, not full acceptance or
evidence of general cross-ROM support.

The intent for the next compatibility-layer update is to turn the source map
below into a reviewed, reproducible patch series. Keep common Samsung API
compatibility separate from ROM-specific build dependencies and device/carrier
configuration. Do not transfer CherishOS runtime claims to another ROM until
that ROM independently passes its build, boot, registration, and call gates.

## Public source provenance

The public repositories were checked on 2026-09-28. Five of the account's
public repositories are direct forks of CherishOS Android 13 (`tiramisu`) repos.
Each first custom IMS commit is based directly on the corresponding CherishOS
branch head.

| Repository | Branch / head | CherishOS base | IMS commits restored |
|---|---|---|---|
| [`android_frameworks_base`](https://github.com/chenjohnliu/android_frameworks_base) | `m11q-volte` / `73178bfc7d1e` | `bd837f94b5e8` | [`e9346dd4`](https://github.com/chenjohnliu/android_frameworks_base/commit/e9346dd40f6095d85c8ac90f46e935ab7c60e240), [`15a303b8`](https://github.com/chenjohnliu/android_frameworks_base/commit/15a303b8fa069ff03b6aa9a0964067b152742fac), [`73178bfc`](https://github.com/chenjohnliu/android_frameworks_base/commit/73178bfc7d1e81b64b02d2b24c14ef24a8a1ecdf) |
| [`android_frameworks_opt_net_ims`](https://github.com/chenjohnliu/android_frameworks_opt_net_ims) | `m11q-emergency-capability-mask` / `1b1a3226` | `ddd67c647e3f` | [`1b1a3226`](https://github.com/chenjohnliu/android_frameworks_opt_net_ims/commit/1b1a32269a62de0e82e3ede53bf2c44751307f18) |
| [`android_frameworks_opt_telephony`](https://github.com/chenjohnliu/android_frameworks_opt_telephony) | `m11q-volte` / `6c209a7d` | `d8ea3f40256b` | [`6c209a7d`](https://github.com/chenjohnliu/android_frameworks_opt_telephony/commit/6c209a7d4fb239e8c8826d1c303f26dd6417dd5a) |
| [`android_packages_services_Telephony`](https://github.com/chenjohnliu/android_packages_services_Telephony) | `m11q-volte` / `26d0551a` | `abbe1d49d26b` | [`cf338879`](https://github.com/chenjohnliu/android_packages_services_Telephony/commit/cf338879ae9ae3a946a84d4678c245c51c98e753), [`afedb3ad`](https://github.com/chenjohnliu/android_packages_services_Telephony/commit/afedb3add75f2f5120f598942f91d8f4ba07d382), [`26d0551a`](https://github.com/chenjohnliu/android_packages_services_Telephony/commit/26d0551acfa76e1fbcbc63e1114327e578badef7) |
| [`android_system_netd`](https://github.com/chenjohnliu/android_system_netd) | `m11q-volte` / `8e455b91` | `0a1e4b250e79` | [`8e455b91`](https://github.com/chenjohnliu/android_system_netd/commit/8e455b91f8aa5b52771fbcf0250a7181f16ec43e) |

The `android_frameworks_base:m11q-volte` branch also contains microG and Play
Integrity changes between the Samsung API commit and the ePDG commits. Those
commits are unrelated to IMS and were not restored.

### Static coverage check against the public fork patches

The 2026-09-29 read-only comparison covered the nine public production commits
listed above. The corresponding production hunks were already present in the
crDroid trees:

- all 34 files from `frameworks/base:e9346dd4` matched; the public
  `SemSystemProperties.java` blob was retained;
- `frameworks/base:15a303b8` matched;
- the AIDL and Java portions of `frameworks/base:73178bfc` matched. Its
  `Android.bp` context differs, but the required
  `oemnetd_aidl_interface-java` dependency is present;
- the production emergency MMTEL capability-mask change from
  `frameworks/opt/net/ims:1b1a3226` is present. Its test-file hunk was not
  imported, so this is a test-coverage omission rather than a runtime patch
  omission;
- `frameworks/opt/telephony:6c209a7d` and the cumulative
  `packages/services/Telephony` changes from `cf338879`, `afedb3ad`, and
  `26d0551a` matched;
- `system/netd:8e455b91` matched.

The later incoming-media fix is outside that nine-commit restoration set. It
is published as Telecom commit
[`66d3d91d`](https://github.com/chenjohnliu/android_packages_services_Telecomm/commit/66d3d91d238436c9a04cd4b653f3db02db4f901e)
plus m11q device integration commit
[`29fc1533`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/29fc1533c06fe54ef80d3808698d33edd93caed8).

The M11 device tree at `97206c0e` already descends from its IMS integration
history through `bac4e173`. Public device-tree commit `9aebafe` updates the
payload-verifier hash and its README instructions; `d11cbe58` adds the stable
fresh-bearer policy described below. This check rules out a missed patch among
the nine listed CherishOS framework commits for this crDroid snapshot; it does
not certify arbitrary ROM revisions or the runtime media path.

## Restored changes in crDroid

The active source checkouts were official crDroid/Lineage Android 13 revisions,
not the user's framework forks. The user-owned M11 device tree was already
checked out at `m11q-volte` head `97206c0e` and contains its IMS integration.

| crDroid checkout baseline | Restored source change | Port note |
|---|---|---|
| `frameworks/base` `a6b06469a8ca` | Samsung IMS compatibility APIs from `e9346dd4`; IPv6-before-address setup from `15a303b8`; Samsung ePDG framework Binder APIs from `73178bfc` | `SemSystemProperties.java` is byte-for-byte the public commit blob (`18cf0172f291d52fd1690df15c6fb2a82230bfe1`). ePDG methods were reconciled with the crDroid source context. Added `oemnetd_aidl_interface-java` to `services/core/Android.bp`, where crDroid had a different dependency list. Existing unrelated SQLite/MMS/Telephony build fixes were preserved. |
| `frameworks/opt/net/ims` `a819e6b` | Emergency MMTEL capability mask from `1b1a3226` | Production expression changed from a bitwise OR test to the intended bitwise AND test. The upstream test-file hunk was not imported, and no tests were run. |
| `frameworks/opt/telephony` `5fd790282c` | GID2 subscriber API implementation from `6c209a7d` | Must accompany the `IPhoneSubInfo` AIDL declaration from `e9346dd4`. |
| `packages/services/Telephony` `051cbcadb` | Cumulative SIM1/SIM2 carrier fallback series from `cf338879`, `afedb3ad`, and `26d0551a` | The M11 overlay already sets `config_allow_sim1_volte_carrier_default_fallback=true`; the fallback remains bounded by the source's active-subscription and carrier-configuration checks. |
| `system/netd` `967c3417` | ePDG tunnel and traffic-rule operations from `8e455b91` | Adds the `IOemNetd` AIDL and netd implementation. Framework `NetworkManagementService` calls are paired with this implementation. |
| `device/samsung/m11q` `97206c0e` | Existing device integration | Already present; no device-tree patch was reapplied. The functional history includes the IMS packaging, audio, SELinux, SVE, ERIS, EpdgService/UnifiedWFC, and carrier-overlay commits through `bac4e173`. |

### Required patch pairings

- `IPhoneSubInfo.aidl` / `PhoneSubInfoController` must be ported together for
  Samsung GID2 callers.
- Framework `INetworkManagementService` and `NetworkManagementService` ePDG
  methods must be paired with `system/netd`'s `IOemNetd` methods and generated
  AIDL dependency.
- The IPv6 configuration change is needed before the legacy ePDG service
  assigns IPv6 addresses to `rmnet_data*` or `epdg_data*` interfaces.
- The Telephony fallback code uses the M11 resource overlay. Do not turn it
  into an unconditional carrier default on other devices or carriers.

## Behavior and limits of the compatibility layer

The `e9346dd4` framework change supplies Samsung API shapes needed for linkage
and basic service operation; it does not implement Samsung's complete framework.
Examples include pass-through IMS call-control, unsupported GBA results, and
null/false results for unavailable Samsung services. GBA-dependent carriers,
UICC/STK number rewriting, and Samsung-only Wi-Fi behavior therefore remain
outside the supported behavior unless a later port implements and validates
them.

The ePDG/netd change creates and manages `epdg_data*` tunnel interfaces and
traffic-control/firewall rules. Kernel TUN support, `/system/bin/tc`, qdisc and
iptables behavior, service startup, and SELinux permissions still require
crDroid device validation. Source applicability alone does not establish a
working VoWiFi tunnel.

## crDroid runtime findings (2026-09-28)

Tests on the flashed crDroid build:

- The new same-build A/B log confirms that a direct-LTE 188 call works. The
  trace shows a fresh WWAN IMS bearer on `rmnet_data1`, successful LTE IMS
  registration, and a complete call setup (`100`, `183`, PRACK, `UPDATE`,
  `180`, `200`, ACK) followed by a normal BYE/200 exchange.
- An outgoing VoWiFi call to a friend's phone worked.
- After Wi-Fi was enabled until the VoWiFi icon appeared, disabling Wi-Fi and
  waiting for VoLTE before dialing 188 reproduces the failure. The new A/B log
  also captures a second 188 attempt failing after the transition.

The unpatched baseline trace showed `INVITE` -> `100 Trying` -> `183 Session
Progress` -> `487 Request Terminated`; Android mapped the failure to reason 339
(`CODE_SIP_REQUEST_CANCELLED`) and left the call in `DIALING` until the user
manually hung up. A later trace from the callback-patched build confirms the
same signaling failure and records the transition in detail:

- At 21:50:02, Wi-Fi was disabled and the IMS data network handed over from
  IWLAN to LTE. The WWAN IMS bearer came up on `rmnet_data1` with the same IPv6
  address and P-CSCF addresses. The handover completed successfully.
- The TWM VoLTE IMS profile then registered on LTE: an initial `REGISTER` got
  `401`, the authenticated `REGISTER` got `200`, and Samsung IMS entered
  `RegisteredState` with `smsip` and `mmtel` services before the call attempt.
- At 21:50:13, the phone sent the 188 `INVITE` over the LTE interface to the
  P-CSCF. It received `100`, then `183`, then `487` from the wire about 33 ms
  after the `183`. No handset-originated `CANCEL` or `BYE` appears in this
  transaction. The response's private reason text includes
  `SIP;cause=503` and `PO: AAA: result_code=0 exp_result_code=5065`. The meaning
  of `5065` and the specific carrier IMS element that ended the request cannot
  be determined from the handset log alone.
- These observations confirm successful IMS data handover and LTE IMS
  registration before the failure. They place the observed failure after the
  INVITE reaches the carrier IMS path; they do not prove the precise network
  policy or server-side cause.

The same-build A/B trace provides a direct-LTE control and narrows the
association to the WFC-to-LTE continuity path:

- In the first call, LTE came up with a fresh IMS bearer on `rmnet_data1`; the
  188 call connected and ended normally.
- After Wi-Fi was enabled, the IMS network handed over from IWLAN to WWAN with
  `RESULT_SUCCESS`. The WWAN bearer used `rmnet_data2` and retained the IPv6
  address previously used on IWLAN. LTE IMS then registered successfully
  (`401` challenge followed by `200`, RAT 13, `smsip` and `mmtel`).
- The post-handover call reached `100` and `183`, then received the same
  `487`/`PO: AAA ... 5065` response. No handset `CANCEL` or `BYE` preceded it.
- The visible parts of the two INVITEs match in call target, method, transport,
  codec/call type, and message size. Their bearer interface, local address and
  port, and selected P-CSCF differ. The SIP body is encoded in this log, so the
  full headers, access-network fields, authorization, and SDP cannot be
  compared; equal message size does not prove identical SIP requests.

This A/B result strongly associates the failure with the handover continuity
path, while leaving the failing component unresolved. A UE/Samsung IMS state
that was not fully switched to LTE and a carrier-side P-CSCF/AAA binding that
did not follow the retained bearer are both plausible. The private `5065` code
does not identify which side is responsible. No further client source change
is justified by this trace alone.

The follow-up airplane-mode reset trace confirms the discriminator:

- At 22:33, airplane mode caused all data networks, including the old IMS
  network, to be torn down. Turning airplane mode off caused a new EUTRAN IMS
  `SETUP_DATA_CALL`, rather than a handover. The phone received a new WWAN IMS
  bearer on `rmnet_data1`, new IP addresses, and a new IMS registration handle.
- IMS registered on LTE again (`REGISTER` 401 challenge followed by 200, RAT
  13, `smsip` and `mmtel`). It selected the same P-CSCF as the failed
  post-handover call, so the successful retry does not depend on switching to a
  different P-CSCF.
- The next 188 call completed: `100`, `183`, PRACK, further progress, `180`,
  `200`, ACK, and Telecom `ACTIVE`; the call later ended with a normal BYE/200.
  This attempt did not receive the previous `487`/`PO: AAA ... 5065` response.

Together, the direct-LTE success, post-WFC handover failure, and fresh-WWAN
success after airplane-mode reset strongly associate the failure with state
carried across the IWLAN-to-WWAN IMS handover. They do not distinguish stale
UE/modem/Samsung IMS state from carrier-side session binding. Because the same
P-CSCF succeeds after a fresh PDN setup, a single bad P-CSCF node is not a
sufficient explanation.

### Applied handover-policy workaround

The AOSP CarrierConfig documentation says handover rules are checked in array
order and that a matching disallowed rule tears down the source data network;
when the preferred access network changes, the framework sets up a new network
on the target transport ([CarrierConfigManager policy](https://android.googlesource.com/platform/frameworks/base/+/d177e28634437784d4a9fd625ccc3c9d28c7093e/telephony/java/android/telephony/CarrierConfigManager.java),
[DataNetworkController behavior](https://android.googlesource.com/platform/frameworks/opt/telephony/+/577eda9b9e/src/java/com/android/internal/telephony/data/DataNetworkController.java)).
The runtime dump showed a catch-all rule allowing IWLAN-to-EUTRAN handover.
The first device test placed this rule before that catch-all for M11/TWM:

`source=IWLAN, target=EUTRAN, type=disallowed, capabilities=IMS`

The user built, flashed, and confirmed that the rule fixes the failed idle
WFC-to-LTE transition: Android tears down the IWLAN IMS network and creates a
fresh WWAN IMS bearer instead of carrying the failing handover state forward.
The expected tradeoff was also confirmed: disabling Wi-Fi during an active
VoWiFi call disconnects that call because the policy deliberately prevents
make-before-break IMS handover.

After the TWM validation, the rule and the existing catch-all allow fallback
were moved into `overlay/packages/apps/CarrierConfig/res/xml/vendor.xml` for
the four PLMNs with
complete bundled Samsung VoWiFi profiles: 46601, 46605, 46692, and 46697. The
temporary carrier-ID 1888 copy was removed to avoid duplicate policy sources.
This stable change was published as device-tree commit
[`d11cbe58`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/d11cbe58dfdf81c284788c50e5b6e37de47cf5d4)
on branch `m11q-volte`. The attempted native active-W2L experiment was fully
reverted, so the overlay policy is the active implementation. Only 46697 has
runtime validation; the other three entries still require their own
registration, idle transition, call, and active-call interruption checks.

The separate call-state cleanup gap was addressed in
`frameworks/opt/telephony/src/java/com/android/internal/telephony/imsphone/ImsPhoneCallTracker.java`.
The failure callback arrived at 21:50:14.047; the Dialer reached `DISCONNECTED`
at 21:50:14.563 without a manual hang-up. The user confirmed that the patched
build now ends the failed call instead of remaining stuck. This change fixes
the stale call UI state; it does not explain or prevent the carrier-side 487.

The airplane-mode reset experiment confirmed that a fresh WWAN IMS setup
restores 188 on this build. The carrier overlay's IWLAN-to-EUTRAN disallow rule
was then tested for an idle WFC-to-LTE transition on PLMN 46697 and confirmed to
trigger teardown plus a fresh WWAN setup without toggling airplane mode. The
expected limitation was also observed: turning Wi-Fi off during an active
VoWiFi call drops that call. The other configured PLMNs have not had separate
runtime validation. Keep fresh log excerpts redacted; full SIP bodies and
subscriber identifiers are not needed.

## Verification state

- The selected production hunks are present in the local crDroid source trees.
- `git diff --check` passed in all five modified repositories.
- The public `SemSystemProperties.java` blob was verified identical.
- The user built/flashed the restored crDroid source and performed the partial
  runtime checks listed above, including a successful validation of the
  Telephony call-state cleanup change. The user runs ROM builds manually.
- Direct LTE and a call after airplane-mode IMS reset succeed. Before applying
  the carrier policy, the allowed WFC-to-LTE handover path reproduced the SIP
  487. On PLMN 46697, the idle-transition disallow policy restores calling by
  forcing a fresh bearer; active WFC calls are intentionally interrupted when
  Wi-Fi is disabled. The exact UE-versus-carrier continuity cause remains
  unresolved.
- Incoming VoWiFi media now works on the tested crDroid build. The missing
  precondition was the ordering between Samsung's SAE request and Telecom's
  `MODE_IN_CALL` transition; the m11q-gated post-mode callback supplies the
  required ordering. Outgoing 188 remained audible and ended normally, and an
  incoming call completed with bidirectional audio and normal teardown.
- No ROM build or tests were run by the assistant.
- The crDroid Telecom integration is published as `66d3d91d`; its m11q overlay
  and SELinux integration are published as `29fc1533`. The stable device-tree
  CarrierConfig workaround remains published separately as `d11cbe58`.

## Follow-up for the compatibility-layer update

1. Convert the reviewed changes into ordered, source-only patch files grouped
   by Android repository, with baseline revisions and prerequisites recorded.
2. Keep Samsung API shims separate from ROM-specific product, `Android.bp`,
   SELinux, carrier configuration, and Telephony call-state cleanup changes.
3. Add an apply/preflight workflow that reports unsupported baselines and
   context drift without partially modifying a tree.
4. Validate the applied IWLAN-to-EUTRAN IMS disallow policy on 46601, 46605,
   and 46692. PLMN 46697 is the only one with runtime validation so far. Confirm
   fresh WWAN IMS setup after an idle transition and record the expected
   active-VoWiFi-call interruption tradeoff for each carrier.
5. Validate the patch series on a clean crDroid 13 tree, then repeat the same
   build/runtime gates on each additional ROM before claiming portability.
   Keep CherishOS results as a separate historical baseline and record each
   ROM's source revisions, build, carrier state, and per-stage IMS result.
