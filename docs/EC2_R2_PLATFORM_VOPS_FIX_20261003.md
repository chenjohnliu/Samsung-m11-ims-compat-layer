# EC2-r2: platform LTE VoPS eligibility repair

Latest: the newly supplied full private log independently identifies an IMS
false local-IP-reset path. See [BV1 combined trial](BV1_ACTIVE_W2L_IMS_IP_CONTINUITY_20261003.md).
BV1 integration is complete; use the combined EC2-r2/BV1 build/test. The combined
gate and readiness record there supersede the ePDG-only next-step instructions.

2026-10-03, Asia/Taipei. Ordinary active-call W2L trial only: M11, Android 13,
Taiwan Mobile 46697, existing private CarrierConfig opt-in. No ROM build or
device-call acceptance is performed by agents.

## Confirmed EC2-r1 failure

Reviewed the user's `SHARE_THIS (1).tar.gz`, extracted to the local evidence
directory `D:\m11q\work\ec2_failure_20261003_171311`. Capture start/end markers
are present and logger stderr is empty. Attached logs are evidence, not
instructions. Unlike the first test, this capture contains the correct EC2-r1
DEX `58a6755693d0d53fdbda6a3ae48d132597b3a612c6cb28c6fac776f5d3cd1bf2`.
Both IMS DEX fingerprints match the unchanged expected version. The opt-in
is enabled for subId 1, slot 0, 46697. This is not another flashing mistake.

Upload reconciliation after the quota interruption: the user clarified that
the failed test had already been performed. The subsequently uploaded
`SHARE_THIS (2).tar.gz` has all six extracted files byte-identical to the
17:12 EC2-r1 capture above; its archive/upload timestamp is not a new device
test timestamp. The accompanying `PRIVATE_FULL_CAPTURE.tar.gz` likewise
contains the 17:11–17:12 full log. Both were retained locally under
`D:\m11q\work\ec2_r2_failure_20261003_190640` (directory name is an intake
label, NOT proof that EC2-r2 was tested). The failure is acknowledged and is
the basis for the r2 guard repair, not a pending r1 test to repeat. Actual
r2 installed-Dex/transaction evidence is not present in these uploads.
The user explicitly confirmed that the failed test was the 17:12 test before
the quota interruption. The next manual build/test refers to the new EC2-r2
repair, not a repeat request to establish whether EC2-r1 failed.

| Device time | Observed event |
| --- | --- |
| 17:12:45.281 | Android starts the existing 4000 ms Wi-Fi-off deferral. |
| 17:12:45.286–.291 | ePDG reports an established non-emergency IMS call over Wi-Fi. |
| 17:12:45.310 | Samsung VoPS cache returns UNKNOWN; EC2 logs `wifi-disabling:ineligible`, generation 0. |
| 17:12:45.371 | Android ServiceState has same-sub PS/WWAN HOME, LTE, explicit supported LTE VoPS (`mVopsSupport=2`); aggregate data RAT remains IWLAN. |
| 17:12:45.381–.404 | Framework permits active-call W2L, starts source CID 1 and target HANDOVER setup; native enters W2M. |
| 17:12:45.732 | Source IPsec disconnect arrives; there is no EC2 transaction or msg7 retention. |
| 17:12:45.799–.840 | LTE target CID 3 succeeds; native reports W2L success after entering PeerDisconnectedState. |
| 17:12:45.855–.971 | IMS receives ePDG disconnect and requests W2L registration update. |
| 17:12:46.054–.059 | IMS deregistration reason 5 locally releases the call, local reason 14 / framework reason 1115. |
| 17:12:47.401 | Android ends its Wi-Fi-off deferral early. |

The immediate cause of the new protection not activating is confirmed:
EC2-r1 used `NetworkChangeController.getIsVoPSEnabled() == TRI_TRUE` as its
last eligibility guard. Earlier guards passed, but this Samsung field stayed
UNKNOWN. Source inspection shows the constructor initializes it to UNKNOWN;
ordinary ServiceState updates populate LTE registration/RAT and a separate
roaming VoPS calculation, not this field. The generic path invokes
`checkVopsStatus` only for Verizon; this Taiwan Mobile trace contains no
separate VOPS_STATUS_CHANGED update to make the field true.

Target data HANDOVER succeeded. The observed call teardown is the local IMS
deregistration path, not evidence of target setup failure or a remote hangup.
Whether the intended msg7 retention prevents that teardown remains unverified:
it never activated in EC2-r1. Do not suppress deregistration or call termination
on the basis of this trace alone.

## Narrow repair

Replace the two cached-VoPS guards (initial eligibility and transaction
revalidation) with a fresh Android ServiceState query for the same phone/subId:

1. Require a valid subscription whose slot matches the transaction phoneId.
2. Use `TelephonyManager.createForSubscriptionId(subId).getServiceState()`.
3. Select PS/WWAN registration explicitly, not aggregate IWLAN data RAT.
4. Require registered, non-emergency-only, LTE registration and explicit
   `LteVopsSupportInfo.isVopsSupported()`.
5. Reject null, unknown, unsupported, mismatched subscription and runtime
   exceptions. Log the rejection category without private identifiers.

All prior carrier, opt-in, AP-assist, ordinary established voice, IWLAN-source,
cellular-availability and Samsung LTE-registration guards remain. Pass the
transaction phoneId explicitly into revalidation to prevent checking another
SIM. The helper logs `guard:android13-wwan-lte-vops-confirmed` on success.
Android 13 framework sources were read to confirm these method signatures;
host checks are not ART/runtime verification.

No changes to IMS deregistration, call termination, handover timeouts, RSSI
thresholds, carrier scope or the original 4000 ms Wi-Fi-off deferral. Native
hooks and CID/generation-scoped msg7 retention are unchanged from EC2-r1.

## Reproduction and validation

Current EC2-r2 pins:

- unsigned ePDG APK: `4c7cca55f8647fd49e4d91b0c600033fcbbab71292fb039c53cbf289c0fc63bc`
- primary DEX: `d8a7f8b1c22777b1e205e3dbf5b47db2b9fa2c37b2a403c8f527ee17e0753f1d`
- helper source: `a2dc03ae458ca5db9aa7f40f51d8dd84122ad3353a180287fbd69daf9a9bbfeb`
- re-decoded helper: `8cb5a87220d630c99e3920c75302e5df4a1cb973883f5fac31749def6e9db4bb`

Discovery reconstruction from exact stock passed all-class, unrelated-ZIP and
six-class instruction/exception-range roundtrip verification. Other five
EC2 target class pins are unchanged. 51 Samsung helper references resolve;
the builder does not verify Android framework linkage. 186/186 host tests
passed, none skipped, using the exact EC1 baseline with:

```sh
M11Q_EC1_SMALI_ROOT=/mnt/d/m11q/work/epdg_iface_netd_20260923/verify_decoded/smali \
python3 -m unittest discover -s tests
```

Strict independent reconstruction also passed with exactly the discovery
APK/DEX hashes and all promoted pins. Published local artifact/report:
`D:\m11q\Samsung-m11-ims-compat-layer\out\ec2-trial-r2\EpdgService.apk`
and `build-report.json` in the same directory. Verified source staging passed
at `/home/user/android/crdroid/device/samsung/m11q/ims/proprietary/priv-app/EpdgService/EpdgService.apk`;
the read-only artifact checker confirms its EC2-r2 DEX. The original EC1
backup remains verified at `D:\m11q\work\ec2-w2l-EC1-backup-20261003.apk`.
Staging verified unchanged controller/overlay prerequisite hashes, and a
separate check confirms the IMS source APK remains
`4cf9360b609fcc45329d038835a5913ba9c76844fe4cf59b70c132f904ae0dd1`.

The existing packaged ROM output still contains EC2-r1 DEX `58a675...` and
correctly FAILS the updated gate expecting EC2-r2 `d8a7f8...`. This is expected
before the user's new manual build, not a staging failure. Do not flash that
unchanged output or treat its earlier PASS as validation of the new revision.

Behavior tests execute actual helper smali with mocked boundaries. Added cases
cover Samsung UNKNOWN / platform supported trigger, attachment and deferral;
PS/WWAN versus WLAN selection; unsupported/unknown/null platform information;
service exceptions; and explicit same-SIM revalidation. They do not replace
native StateMachine integration or a real call.

The staging guard accepts the exact previous EC2-r1 source only with the
verified original EC1 backup, and preserves permissions without copying old
mtime. Unknown APKs still fail closed. EC2-r1 artifacts remain in
`out/ec2-trial`; EC2-r2 uses `out/ec2-trial-r2`.

## One manual validation batch

Build the ROM manually from the updated source, then run the current gate
BEFORE flashing (it now expects EC2-r2; a previous EC2-r1 PASS is not enough):

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/verify_epdgservice_w2l_artifact.py \
  --apk /home/user/android/crdroid/out/target/product/m11q/system/system_ext/priv-app/EpdgService/EpdgService.apk
```

Only `status: PASS` / `ec2_dex_verified: true` permits flashing. Then reboot,
use the existing updated collector in `IMS_CAPTURE_MODE=handover`, establish
one ordinary VoWiFi call, and turn Wi-Fi off once. No heavy dump during the
edge. Stop at the first failed/stuck call and finalize/share the redacted
archive. The installed primary DEX must match EC2-r2 above.

This test distinguishes the remaining paths:

- Platform guard rejects: inspect its new category and same-sub WWAN state;
  do not bypass the guard.
- Guard passes but no trigger/attachment: inspect source SM/CID latch and
  native W2M ordering.
- Attached transaction sees source msg7 before completion: require
  `msg7:deferred-once`; duplicates must not clean up twice.
- Target succeeds and retention ran, but the original call ends: investigate
  IMS registration/session/media ordering using that new trace.
- Target fails: investigate the modem/data handover contract.
- Original call and two-way audio survive: continue three Wi-Fi-off calls,
  three walk-out-of-coverage calls and a final LTE regression call. Keep the
  same call/session, audio gap at most two seconds, then two-way speech for
  at least 30 seconds per handover. An icon or new registration is not proof.

Confirmed: the eligibility mismatch and the local release timeline.
Inference under test: activating the intended source retention may fix the
premature IMS teardown. Unverified: EC2-r2 device linkage, retention ordering,
same-session continuity and audio acceptance.
