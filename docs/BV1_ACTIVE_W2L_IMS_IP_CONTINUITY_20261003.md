# BV1: retain IMS registration across an address-preserving W2L handover

2026-10-03, Asia/Taipei. This supplements EC2-r2; do not spend a standalone
ROM build cycle on EC2-r2 before the combined trial is ready. Agents perform
source changes and APK assembly/verification only, never Android ROM builds.

## Evidence and corrected chronology

The user confirmed the failed call was the 17:12 EC2-r1 test before the quota
interruption. The later `SHARE_THIS (2).tar.gz` contains the same six files
byte-for-byte, not a new r2 test. The accompanying full private log supplies
additional evidence unavailable in the shared summary. Both are retained
locally under `D:\m11q\work\ec2_r2_failure_20261003_190640`; that intake label
does not identify the tested revision. No private addresses, subscriber
identifiers or raw SIP messages are reproduced in this source document.

The following line numbers refer to `private/logcat_all_private.txt` there:

| Lines | Confirmed event |
| --- | --- |
| 6137, 6150, 6242, 6330 | Framework/native WLAN-to-LTE IMS data handover succeeds. |
| 6360, 6372, 6381–6392 | `epdg_data0` becomes `rmnet_data2`; existing IPv6 local address and P-CSCF remain, IPv4 entries are added. The current P-CSCF is kept, `forceInitialRegi=false`. |
| 6375 | Native IMS reports local-IP change with `isStackedIpChanged=false`. |
| 6741–6763 | ePDG-disconnected processing requests W2L registration update. |
| 6919, 6941–6945, 6960–6963, 7006 | Re-registration starts; UA becomes REREGISTERING and REGISTER CSeq 4 is transmitted. |
| 6944, 7180–7185 | Local-IP event assigns deregistration reason 5 and local deregistration. |
| 6966–6977, 6991, 7096–7100, 7222, 7242–7244 | MMTEL deregistration locally releases the existing call, reason 14 / internal and framework 1115. |
| 8158–8170, 8253–8267, 8293–8294 | Later genuine SIP 403 response to REGISTER; UA reports deregistration with `pcscfGone=false`, manager reports already assigned reason 5. |

The source directly supports the event path:

- `PdnController$NetworkCallback.isLocalIpChanged` returns `LOCAL_IP_CHANGED=1`
  immediately if the interface names differ, before checking address continuity.
- `PdnController.onLinkPropertiesChanged` updates cached LinkProperties and
  maps result 1 to `onLocalIpChanged(..., false)`, result 2 to `(..., true)`.
- `RegisterTask` forwards that local-IP event. `NetworkEventController`
  sets reason text `local IP changed`, reason 5, and requests local deregistration.
- `RegistrationManagerHandler.notifyLocalIpChanged` already ignores the
  stacked-only event for non-RCS/MMTEL registration; ordinary local-IP changes
  retain their original behavior.

The relevant callback decoded fresh from the exact current reproducible IMS
APK has SHA-256 `aeece7782e8e4f43607cdac9c57e10d3ac0c6c7d253c87935c415f34d230b60a`,
matching the previously audited source. The accepted baseline APK is
`4cf9360b609fcc45329d038835a5913ba9c76844fe4cf59b70c132f904ae0dd1`;
its primary/bridge DEX match the fingerprints installed in this failure capture.

Confirmed: the interface-change classification, preserved addresses/P-CSCF,
local deregistration reason 5 and local call release. Inferred: preventing
this false local-IP-reset classification can remove one independently
identified teardown trigger. The later 403 is real, but avoiding reason 5 is
not proof that the normal W2L re-registration will succeed or that the same
call/media will survive. Those remain runtime questions.

## Narrow implementation boundary

BV1 adds one authored helper call at the entry to the existing callback's
`isLocalIpChanged`. Only a positively qualified transition returns the existing
`LOCAL_STACKED_IP_CHANGED=2`; rejection continues through the unchanged original
method. The original implementation remains byte-identical after the injected
entry hook. No changes to deregistration, call termination or generic IMS
registration updates are made.

Required guards:

- IMS PDN type 11; valid phone/subscription with matching slot; identified
  CarrierConfig, existing private opt-in true; SIM operator exactly 46697.
- Exactly one ordinary connected voice call on that phone. No video,
  downgraded-video or emergency calls; foreground session must match the phone
  and native InCall state. Missing state or checked/runtime exceptions reject.
- Exact `epdg_data[0-9]+` to `rmnet_data[0-9]+` interface transition.
- Nonempty filtered old main local addresses, old all/stacked addresses and
  old P-CSCF lists. Every old usable entry in each list must occur in its
  corresponding new list. Mere address intersection is insufficient.

The helper uses the native address filter, so it does not redefine usable IPs.
Added addresses are allowed; any removed/replaced old local IP or P-CSCF
rejects. Reverse transitions, alternate carriers, idle/dialing/held calls,
multiple calls, video and emergencies are not covered. It reuses native
stacked-event handling rather than suppressing all local-IP notifications.
The callback still updates its LinkProperties, and normal P-CSCF change
processing remains active.

IMS and ePDG are separate processes. BV1 cannot read EC2's in-process transient
transaction array; its scope is bounded by the same private opt-in and the
exact successful W2L interface/address shape, not a fabricated shared token.
The existing EC2-r2 source CID/generation retention remains independent.
Android's four-second Wi-Fi-off deferral, native/framework timeouts and RSSI
thresholds remain unchanged.

## Reproducible trial packaging

Keep the stable stock-to-current IMS builder/config unchanged. The new
`tools/build_imsservice_w2l_trial.py` accepts only its exact pinned current
unsigned output as baseline, applies the authored BV1 transform, and publishes
only a replaced primary DEX after independent discovery/strict verification.
Manifest, resources, bridge `classes2.dex` and every unrelated ZIP entry remain
byte-identical; APK signatures are removed for normal ROM platform signing.
It verifies all primary class inventories/instructions/metadata, native helper
member accessibility, canonical target pins and final APK/DEX pins.
Only assembly presentation differences are normalized, including equivalent
string-index width (`const-string`/`const-string/jumbo`) with exact literals and
register operands retained. These checks are not ART or real-call validation.

Stock-derived decoded source/APKs/private captures remain local; publish only
authored transformation instructions, helper and nonprivate contracts/tests.
The staging tool requires a matching strict report, unchanged framework and
overlay prerequisites, EC2-r2 ePDG, and a verified original IMS backup. It
refreshes source mtime for incremental builds while preserving permissions.

## Combined manual validation gate

When the source-staging record below confirms readiness, build manually, then
verify BOTH packaged APKs before flashing:

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/verify_ims_w2l_trial_artifacts.py \
  --epdg-apk /home/user/android/crdroid/out/target/product/m11q/system/system_ext/priv-app/EpdgService/EpdgService.apk \
  --ims-apk /home/user/android/crdroid/out/target/product/m11q/system/system_ext/priv-app/imsservice/imsservice.apk
```

Only PASS for the combined EC2-r2/BV1 gate permits flashing. A prior ePDG-only
PASS is insufficient. Reboot, then use the same handover collector, which
already captures `W2L` including the new `M11Q_W2L_IP` marker. Do not request a
heavy snapshot during transition. Test one established ordinary VoWiFi call,
then switch Wi-Fi off once. Stop and finalize the trace on first failure.

Decision path for that single combined test:

1. Verify installed ePDG and both IMS DEX fingerprints first.
2. Require EC2 platform-VoPS guard/trigger/attachment and applicable msg7
   retention. If missing, follow its existing diagnostic categories.
3. At the IMS interface transition require `M11Q_W2L_IP` retained/stacked
   classification. Rejection categories identify the missing guard.
4. If BV1 accepts but local-IP reason 5 still occurs, locate another callback
   or a later true address change. Do not blanket-disable reason 5.
5. If reason 5 disappears but registration fails/403 remains, inspect the
   normal W2L REGISTER and IMS registration/session ordering from that trace.
6. If the original call survives, verify bidirectional audio gap <=2 seconds
   and >=30 seconds subsequent conversation; continue the accepted three
   Wi-Fi-off, three walk-out and final LTE 487/5065 regression batch.

An icon change, new registration or replacement call is not acceptance.
ROM build, flashing, reboot and real-device calls remain the user's boundary.

## Verified combined source readiness

The combined EC2-r2/BV1 source is now ready for the user's manual build.
203/203 full host regression tests passed, none skipped, with the exact EC1
and freshly decoded current IMS baselines supplied. This includes actual
helper-smali branch execution and staging/version-gate negative cases; it is
not an ART verifier, native integration test or real-call acceptance.

Independent discovery and strict reconstruction produced identical pins:

- BV1 IMS primary DEX: `00f6fe5258acaa64ec03c97b9583394f46acdafeeac79ba5a532e6f245753ae1`
- BV1 unsigned IMS APK: `251f95cb892e38b8ba8025c3033332c55d8ac4bec1d0d53b8d18c8d33a870d0b`
- Preserved IMS bridge DEX: `b9d57c1a1aab37fd88a5443bde177c710897b1603481350e8037cf332ce0d325`
- EC2-r2 ePDG primary DEX: `d8a7f8b1c22777b1e205e3dbf5b47db2b9fa2c37b2a403c8f527ee17e0753f1d`
- Authored BV1 helper: `ff3ce00936d60b6b5996af08aaa0262652f090245a2d1ea60ac97fba2aab53a9`

All 5,451 primary classes passed inventory/instruction/metadata roundtrip;
27 Samsung helper member references resolved with accessibility checks using
the primary IMS plus exact stock `imsmanager.jar` dependency. That dependency
was freshly decoded for verification and is unchanged in the WSL source,
SHA-256 `ba88f7111ea5c678d597dcb0498ee9fc42611fd4f6af12b6312fad05495de78b`.
The helper uses checked foreground-session APIs; `java.lang.Exception` is
caught fail-closed, while linkage/errors are not hidden.

Artifact/report are local at
`D:\m11q\Samsung-m11-ims-compat-layer\out\bv1-trial\imsservice.apk`
and `build-report.json` there. Strict staging verified the framework/overlay,
EC2-r2 ePDG and native framework dependency before replacing only the known
current IMS source at
`/home/user/android/crdroid/device/samsung/m11q/ims/proprietary/priv-app/imsservice/imsservice.apk`.
Its APK matches the new pin, and the combined source-APK gate returns PASS.
Verified original IMS backup is `D:\m11q\work\bv1-IMS-baseline-20261003.apk`,
SHA-256 `4cf9360b609fcc45329d038835a5913ba9c76844fe4cf59b70c132f904ae0dd1`.
Source mtime is fresh for the user's incremental build; no output/intermediate
files were deleted and no ROM build was run. The unchanged collector passes
`bash -n` and already captures both new helper markers.
The existing packaged ROM output still contains EC2-r1 and correctly fails
the new combined gate before the user's new build. This expected pre-build
FAIL is not a new device test or another deployment error.

Reproduce the local trial (new output/report paths must not exist):

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/build_imsservice_w2l_trial.py \
  --base-apk /mnt/d/m11q/work/bv1-IMS-baseline-20261003.apk \
  --imsmanager-jar /home/user/android/crdroid/device/samsung/m11q/ims/proprietary/framework/imsmanager.jar \
  --apktool-jar /mnt/d/m11q/work/stage1bc1_discovery/tools/apktool_2.9.3.jar \
  --java /usr/lib/jvm/java-11-openjdk-amd64/bin/java \
  --output out/bv1-trial/recheck.apk --report out/bv1-trial/recheck.json \
  --work-dir /tmp
```

The stable `build_imsservice.py` and `imsservice-build.json` remain unchanged
by BV1; those pins describe the reproducible pre-BV1 baseline, not the trial.
Do not install this unsigned APK directly. Normal ROM platform signing remains
in charge. Host PASS certifies identity/envelope checks, not seamless calling.
