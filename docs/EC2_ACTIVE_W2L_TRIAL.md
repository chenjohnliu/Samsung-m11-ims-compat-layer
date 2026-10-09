# EC2 ordinary-call VoWiFi to VoLTE trial

Prepared 2026-10-03, Asia/Taipei. This implements the user's accepted W2L
plan for M11/crDroid Android 13 and Taiwan Mobile (46697). The same established
ordinary voice call must survive, with no redial, at most two seconds of audio
interruption, and at least 30 seconds of subsequent two-way conversation.
Walking out of coverage and manually disabling Wi-Fi are separate test cases.

## Source and runtime status

Current combined trial: [EC2-r2 + BV1 IMS continuity](BV1_ACTIVE_W2L_IMS_IP_CONTINUITY_20261003.md)
is staged and passed 203 host tests plus strict independent APK reconstruction.
The full private 17:12 log identified a second, independent IMS local-IP-reset
classification path. Use the combined two-APK gate there before flashing;
the ePDG-only commands below are historical tooling/acceptance context.

Latest update: the 17:12 capture contains the correctly deployed EC2-r1, but
the call still drops. Its new protection never activated: Samsung's cached
VoPS remained UNKNOWN while Android reported explicit supported PS/WWAN LTE
VoPS. Target data HANDOVER succeeded, then IMS locally released the call.
EC2-r2 replaces only that cached-VoPS eligibility/revalidation guard with
same-sub Android PS/WWAN LTE VoPS confirmation. Its initial 186 host tests passed. See
[confirmed failure, narrow repair and next validation](EC2_R2_PLATFORM_VOPS_FIX_20261003.md).
**Rebuild and pass the current packaged-APK gate before flashing; the previous
EC2-r1 PASS does not verify EC2-r2.** Call continuity remains unverified.

Historical 16:39 update: the first test packaged EC1 due to the staging tool
preserving old mtime; that separate deployment bug is repaired. See
[first deployment miss](EC2_FIRST_TEST_DEPLOYMENT_MISS_20261003.md).

Implementation, pinned APK reproduction and source staging passed on
2026-10-03. The verified trial APK is now in the user's WSL crDroid device
source. The next action is the user's manual ROM build, flash and test batch
below. No ROM build, flash or runtime acceptance has been performed by agents.

The preceding controller-only experiment still dropped the call on Wi-Fi-off.
That observation does not identify which native event caused termination. The
old October 1 captures are not failure captures for this version.

## Implementation boundary

Android's original Wi-Fi-off deferral remains intact. The default carrier
value is 4000 ms; the IMS registration callback can finish shutdown earlier
after a non-WLAN registration. EC2 does not extend that time or bypass it.

EC2 layers on the exact-stock EC1 ePDG transform. A standard
`android.net.wifi.WIFI_STATE_CHANGED` DISABLING notification requests an IMS
LTE qualified network while the Wi-Fi link still exists. Eligibility is
limited to the opt-in 46697 subscription, AP-assist mode, established ordinary
voice, an IWLAN IMS source, and available LTE with explicit VoPS support.
WWAN packet-service registration and an identified CarrierConfig are required;
an unknown subscription, null helper or ambiguous eligibility fails closed.
EC2-r2 obtains explicit VoPS support from Android's same-sub PS/WWAN LTE
registration, not the Samsung cache or aggregate IWLAN data RAT. Unsupported,
unknown, missing, emergency-only or wrong-sub platform state still rejects.
The existing private `m11q_active_call_w2l_handover_bool` CarrierConfig key
also gates the controller exception. The temporary network preference does
not change the user's permanent Wi-Fi calling mode.

The source SM and positive IMS CID are latched when publishing the request,
before native W2M entry. Both general and APN-specific qualified-network
publication pin only the IMS entry before dispatch, not by publishing an
IWLAN result and then correcting it. Matching framework cancellation can
clear a pending request before native entry. Source msg7 retention starts only
after that exact SM/CID enters W2M; unrelated requests cannot attach.

Existing weak-Wi-Fi W2L requests use the same qualified-network path and
unchanged Samsung RSSI thresholds/hysteresis. The AP-assist path does not
invoke the unsupported legacy W2L trigger.

The source IPsec disconnect event is retained only during the matching IMS
W2L transaction. Completion, failure, cancellation, existing timeout, and
call-end leave that retention through the existing state-machine cleanup.
Setup failure and reset retain their existing treatment. Framework
`DataNetwork` source-event deferral is retained. No speculative pre-handover
event-order patch is applied without a new trace proving that ordering.

Only one matching source msg7 is deferred through the existing StateMachine
queue; repeats are consumed during retention. Existing success notification
and source detach run before W2M exit clears the trial. Exit then replays the
deferred message in the existing destination state. Failures and native
watchdog expiry exit normally; framework cancellation retains its original
HANDOVER_FAIL notification. Call-end and shutdown cancellation send the same
CID-scoped native HANDOVER_FAIL before clearing the trial. Setup failure
(msg6) and reset (msg8) are never suppressed. Cleanup is generation-checked,
idempotent and restores normal qualified-network computation outside the lock.
DISABLED clears the shutdown request but does not abandon an attached W2M;
ENABLED cancels only a still-pending shutdown, not a weak-signal transaction.

The framework's configured handover watchdog is distinct from the four-second
Wi-Fi-off delay. Source inspection found a 300000 ms default framework
watchdog and a 160000 ms native watchdog. EC2 does not invent a replacement
timeout; call-end and framework cancellation must release native retention
directly. A read-only device check found the handover DeviceConfig value
unset, so the audited framework uses its default. Modem behavior still
requires the new device capture.

The IMS bridge source audit passed the Wi-Fi deferral contract: it supplies
VOICE capability with IWLAN registration, preserves registration attributes,
and Android maps that registration to the WLAN transport callback. LTE
registration subsequently maps to WWAN. No bridge change is supported by the
current source evidence. The narrow capability-publication window immediately
after registration remains a runtime observation point, not a demonstrated
cause of the established-call failure.

## Reproducible artifacts

`tools/build_epdgservice_w2l_trial.py` decodes the exact stock APK, applies
EC1 then EC2, assembles the APK, replaces only `classes.dex` and removes old
APK signatures, then re-decodes and verifies every existing and added class.
Unrelated APK entries remain byte-identical. Input hashes and output pins
fail closed. Discovery mode publishes a report only; strict mode requires
promoted APK and DEX pins before publishing an artifact.

Raw transformed text and canonical re-decoded text have separate strict pins.
Every modified/added class is also checked instruction-by-instruction across
assembly, including register operands, branch destinations, switch entries and
exception ranges. Only label names, field/method presentation order, debug
directives, branch widths and switch-payload alignment are normalized. This
does not constitute Android ART verification or modem/IMS runtime validation.

Rebuild the unsigned trial locally from the user-supplied stock input:

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/build_epdgservice_w2l_trial.py \
  --stock-apk /mnt/d/m11q/stock_analysis/artifacts/system/priv-app/EpdgService/EpdgService.apk \
  --apktool-jar /mnt/d/m11q/work/stage1bc1_discovery/tools/apktool_2.9.3.jar \
  --java /usr/lib/jvm/java-11-openjdk-amd64/bin/java \
  --output out/ec2-trial-r2/recheck.apk --report out/ec2-trial-r2/recheck.json \
  --work-dir /mnt/d/m11q/work
```

The output/report must not already exist. This is APK assembly only, not an
Android ROM build. Stock, decoded trees, APKs and private reports remain local
and must not be published with the source-only transformation.

The unchanged stable builder remains `tools/build_epdgservice.py`.
The trial builder's output is unsigned; the existing ROM prebuilt module
handles signing as usual. It must not be installed directly as a signed app.

`tools/stage_epdgservice_w2l_trial.py` requires a matching strict report, the
known controller/overlay source hashes and either the known EC1 APK, exact
previous EC2-r1 APK (with original backup), or current EC2-r2 output.
It preserves a verified EC1 backup before replacing the
source-tree APK atomically. Unknown changes stop before replacement.

## Manual build and one validation batch

After the source-staging result is recorded below, perform the normal manual
ROM build, flash and reboot. Use the current source tree with the existing
IMS and CC debug-gate changes. Agents do not perform these operations.

After building and BEFORE flashing, verify the packaged APK (not only source):

```sh
cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
python3 tools/verify_epdgservice_w2l_artifact.py \
  --apk /home/user/android/crdroid/out/target/product/m11q/system/system_ext/priv-app/EpdgService/EpdgService.apk
```

Proceed only on `status: PASS` / `ec2_dex_verified: true`. A failed gate means
stop before flashing and report its output. Signing/container changes do not
change the expected DEX pin.

Copy the updated `D:\m11q\tools\capture_ims_wifi_cycle_termux.sh` to Termux and
run:

```sh
IMS_CAPTURE_MODE=handover bash capture_ims_wifi_cycle_termux.sh
```

Capture a stable baseline before dialing. During the edge, collect continuous
logs only; do not request a phase snapshot or TelephonyDebugService dump.
The collector fingerprints the installed telephony-common.jar, ePDG APK and
IMS APK, and records the layered experiment CarrierConfig in stable phases.
It also records each APK's primary DEX hash and the IMS bridge's `classes2.dex`:
ROM signing changes the whole APK hash, so compare DEX pins below. A missing fingerprint
means extraction failed, not that the installed version was verified.

1. On strong Wi-Fi, establish an ordinary non-emergency voice call. Speak in
   both directions, switch Wi-Fi off once, and check the original call/session
   continues. Measure any audio gap. Continue two-way conversation for 30 seconds,
   hang up normally, then collect a stable phase such as `off_1`.
2. Repeat until three consecutive Wi-Fi-off calls succeed.
3. Restore strong Wi-Fi while idle. Establish another ordinary VoWiFi call
   and walk out of Wi-Fi coverage without toggling Wi-Fi. Apply the same
   audio/session checks and repeat for three consecutive successes.
4. Make one final LTE call to check the prior 487/5065 regression, then enter
   `stop` to finalize the capture.

Stop after the first dropped or stuck call, retain that trace, and finalize
the collector. Do not replace the failed trace with repeated reset/toggle
cycles. Keep private captures private unless explicitly sharing them for
investigation. The redacted `SHARE_THIS.tar.gz` is the initial review artifact.

Required timeline:

`DISABLING/weak signal -> LTE qualified network -> source START_HANDOVER ->
source IPsec state -> target HANDOVER result -> IMS access/session update ->
Wi-Fi shutdown`

Target failure directs the next investigation to the modem/data/carrier
handover contract. Successful target setup followed by call termination
directs it to IMS session/registration/media ordering. No handover start
directs it to the installed flags, eligibility and trigger. An icon change,
new IMS registration or replacement call is not continuity evidence.

Reverse continuity, rapid reversals, alternate carriers, emergency and video
handover are outside this trial. Do not place emergency test calls.

## Historical EC2-r1 host output and source staging (2026-10-03)

The following records the original revision, not the current build pins.
Current EC2-r2 pins and validation are in
[the r2 repair record](EC2_R2_PLATFORM_VOPS_FIX_20261003.md).

- ePDG unsigned APK: `f75ae702513d3a0d183f3b109f49f98679e16b9aec5caafb0d766b89a4b3120e`.
- ePDG `classes.dex`: `58a6755693d0d53fdbda6a3ae48d132597b3a612c6cb28c6fac776f5d3cd1bf2`.
- Current unchanged IMS `classes.dex`: `cd8be33628bfabeafe77e78c58bf13ba8207e0eba41718845dcf116a8594cfe2`.
- Current unchanged IMS bridge `classes2.dex`: `b9d57c1a1aab37fd88a5443bde177c710897b1603481350e8037cf332ce0d325`.
- Strict artifact/report: `D:\m11q\Samsung-m11-ims-compat-layer\out\ec2-trial\EpdgService.apk`
  and `build-report.json` in that directory. Discovery and strict reconstruction
  used fresh stock decoding and produced identical final APK/DEX hashes.
- Host test run: 44/44 passed using
  `M11Q_EC1_SMALI_ROOT=/mnt/d/m11q/work/epdg_iface_netd_20260923/verify_decoded/smali`
  and `python3 -m unittest discover -s tests -p 'test_*epdgservice*.py' -v`.
  Tests execute the shipped helper's actual smali instructions with mocked
  Android/native boundaries. This is not an emulator, ART verifier, complete
  native StateMachine integration test or device-call acceptance.
- Full compatibility-layer regression: 176/176 passed with that same exact
  baseline environment and `python3 -m unittest discover -s tests`; none skipped.
- All re-decoded classes and unrelated ZIP entries verified; six EC2 classes
  passed instruction/exception round-trip checks; 52 helper Samsung references
  resolved to accessible native members. Android framework linkage still needs
  device verification. The capture script passed `bash -n`.
- Applied target:
  `/home/user/android/crdroid/device/samsung/m11q/ims/proprietary/priv-app/EpdgService/EpdgService.apk`.
  Its hash matches the unsigned EC2 pin above. Existing ROM signing remains in
  charge; do not install the unsigned APK directly.
  Re-running the staging guard returned `already_staged=true` and verified the
  same backup and source prerequisites without replacing anything again.
- Verified original backup: `D:\m11q\work\ec2-w2l-EC1-backup-20261003.apk`,
  SHA-256 `5eb14c66f5a6917de214d823f34b7dd453f6b22a64b91d74c733c89e23e23f98`.
- Existing framework prerequisite remains unchanged:
  `DataNetworkController.java` SHA-256
  `6b8bf4490598d642be784beb55551c0af5f71c47c213134b2a5504918ae6895b`.
  Existing device `vendor.xml` remains unchanged, SHA-256
  `8b21b2d5511586e938da2ca03d0c7e2004384f519edabac6a44519151dfda4dd`.
  Existing IMS APK remains unchanged, SHA-256
  `4cf9360b609fcc45329d038835a5913ba9c76844fe4cf59b70c132f904ae0dd1`.

Confirmed from the later EC2-r1 capture: installed revision, Android deferral,
target HANDOVER success, and protection rejected by cached VoPS UNKNOWN.
Inference under test for EC2-r2: activating the early trigger and source msg7
retention may prevent premature IMS teardown. Unverified: EC2-r2 device
linkage/retention, unchanged call/session identity and audio continuity.
Do not label this trial a working seamless handover until the batch passes.
