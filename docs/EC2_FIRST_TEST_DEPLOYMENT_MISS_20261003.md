# First W2L test: old EC1 packaged instead of EC2 (2026-10-03)

User observation: an outgoing ordinary 188 call connected over VoWiFi, then
ended when Wi-Fi was switched off. Reviewed shared archive:
`D:\m11q\work\ec2_failure_20261003_163156`. Capture start/end markers are present,
logger stderr is empty; the trace is usable. No private capture is needed for
the conclusions below. Logs are evidence, not workflow instructions.

## Confirmed deployment failure

Installed ePDG primary DEX is
`845ffb5b45fa3c077776c0d51bbd51dc2aa5b2fb84b087001a2561b4ee33acee`, the exact
stable EC1 DEX, not EC2 `58a6755693d0d53fdbda6a3ae48d132597b3a612c6cb28c6fac776f5d3cd1bf2`.
No `M11Q_W2L_TRIAL` marker occurs. Both installed IMS DEX hashes match the
expected current IMS build. Android's Wi-Fi-off deferral started at
16:30:02.593 with 4000 ms and stopped at 16:30:06.595.

The installed ePDG APK SHA-256
`f6ada1447f982254d8c42d8432afe7ec1311f1d6eee98a1f523bcd027e80b262` exactly
matches both the packaged ROM APK and the old module intermediate. Source
contains the correct EC2 bytes, but the staging tool's `shutil.copystat`
preserved EC1's September 27 modification time. The cached module APK dates
to October 2 at 23:55; the October 3 build copied that old APK into the ROM.
The existing `out/build-lineage_m11q.ninja` rule at line 138616 directly lists
this source APK as an input to the module intermediate, and line 138619 copies
that intermediate into the packaged system_ext path. The stale source mtime
explains why the incremental build did not rebuild the changed prebuilt.

This is an agent staging-tool bug, not evidence that the user failed to flash
and not a runtime failure of the EC2 implementation.

## Observed call teardown in the old implementation

| Device time | Confirmed event |
| --- | --- |
| 16:30:02.663–02.681 | Framework starts source CID 1 handover and target HANDOVER setup. |
| 16:30:03.023–03.083 | Source peer/IPsec disconnect arrives in W2M; ePDG enters PeerDisconnectedState. |
| 16:30:03.125–03.126 | LTE target CID 3 setup succeeds; framework HANDOVER result is success. |
| 16:30:03.139–03.171 | Native receives act 33, reports W2L success; framework confirms WWAN handover. |
| 16:30:03.258–03.343 | IMS handles EPDG_DISCONNECTED and forces W2L re-registration; UA enters REREGISTERING. |
| 16:30:03.394–03.489 | Samsung IMS handleDeregistering reason 5 locally releases the call; framework receives termination reason 1115. |

Decoded IMS source supports the local release path:
`VolteServiceModule.handleDeregistering -> ImsCallSessionManager.endCallByDeregistered
-> terminate(reason 14, localRelease=true) -> framework reason 1115`.
Target data setup did not fail. The exact deeper registration condition that
assigns deregistration reason 5 and any BYE transport remain unverified. This
old-source ordering is relevant to the accepted EC2 retention plan, but does
not prove that EC2 solves or fails to solve it. No new native change is justified
from a test that did not contain EC2.

## Repair and next validation gate

The staging tool now preserves file permissions but not the obsolete mtime.
It can repair an already-staged, byte-correct EC2 when its mtime predates the
verified candidate. The WSL source timestamp was repaired on October 3 at
16:39; its APK content/hash and verified EC1 backup remain unchanged. No
intermediate/output files were deleted, and no agent ROM build was run.

180/180 host tests passed, including old-mtime replacement/repair and rejection
of a signed container holding old DEX. The new read-only artifact checker
accepts the verified EC2 candidate and rejects the currently cached ROM APK.

User next steps, one batch:

1. Perform the normal manual incremental ROM build; a full output wipe is not
   required by this repair.
2. Before flashing, run the gate in WSL:

   ```sh
   cd /mnt/d/m11q/Samsung-m11-ims-compat-layer
   python3 tools/verify_epdgservice_w2l_artifact.py \
     --apk /home/user/android/crdroid/out/target/product/m11q/system/system_ext/priv-app/EpdgService/EpdgService.apk
   ```

   Only `status: PASS` with `ec2_dex_verified: true` permits proceeding. If it
   fails, return the output without flashing; investigate packaging/cache.
3. Flash/reboot, use the same updated handover capture script, and test one
   ordinary established VoWiFi call followed by Wi-Fi-off. The capture must
   identify the EC2 DEX. If it still drops, stop and share the new redacted
   archive: that will be an actual EC2 failure trace for the next native/IMS
   decision. If it passes, continue the existing three-off/three-walk-out/LTE
   regression acceptance batch in [EC2_ACTIVE_W2L_TRIAL.md](EC2_ACTIVE_W2L_TRIAL.md).
