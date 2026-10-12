# CherishOS Android 13 source checkpoint — 2026-10-12

This checkpoint records the source changes applied to the newly synchronized
CherishOS Android 13 M11 tree. It closes the known platform-source omissions
found during the user's manual build, including the MMS implementation paired
with the framework API change. On 2026-10-12 the user reported a successful
ROM build, boot after Format Data, and normal calls. This is user-reported
voice acceptance; VoWiFi, SMS, handover and ERIS/IPsec were not newly verified.

This is the validated baseline snapshot. The later
[IMS source supplement](CHERISH_LOCAL_IMS_PATCHES_20261012.md) adds the missing
Telecom permission declaration and emergency capability regression test.
Apply those two patches once after this checkpoint. Its separate MMS patch
is a reference copy of the companion already included here. The supplement
has source verification, but no subsequent user build or runtime acceptance.

The authoritative patch list is
[`platform/checkpoints/cherish-20261012/manifest.json`](../platform/checkpoints/cherish-20261012/manifest.json).
Each project has an exact base commit, a patch SHA-256, and the expected Git
tree after applying the patch. The revision-locked baseline manifest records
the synchronized projects; it does not record dirty working-tree changes.

## Included source changes

| Project | Purpose |
| --- | --- |
| `frameworks/base` | Samsung compatibility APIs, MMS calling-user API, phone-number fallback, and registration-derived VoWiFi icon with the correct `ims.stub` imports |
| `frameworks/opt/net/ims` | Samsung IMS interface compatibility |
| `frameworks/opt/telephony` | Telephony integration and the four SEH bridge source classes |
| `packages/services/Telephony` | Phone service integration |
| `system/netd` | Samsung OEM network interface compatibility |
| `packages/services/Telecomm` | Samsung incoming-call audio callback, call-audio hooks, two SA2 helpers, and the default-disabled resource gate |
| `packages/services/Mms` | Four `MmsService` signatures matching the modified `IMms` API |
| `hardware/qcom-caf/msm8953/audio` | Remove the unused AIDL power-library link dependency from the HIDL power HAL |
| `hardware/qcom-caf/msm8953/display` | Replace two loops with one error query, preserving the original first-error behavior |
| `vendor/qcom/opensource/commonsys-intf/display` | Use a `size_t` page-alignment mask, including values above 4 GiB |
| `device/cherish/sepolicy` | Remove the duplicate camera-property declaration while retaining the selected QVA declaration |
| `device/samsung/m11q` | Select the existing Cherish product and lunch targets |
| `vendor/cherish` | Optional Vanilla Jelly selection and the user's retained OTA survival customization |
| `build/make` | Optional corresponding OTA survival generator change |

The baseline manifest includes the pinned Jelly source and excludes Calendar.
The two optional customization projects record the user's build configuration;
they are not IMS runtime fixes. Apply their patches together when reproducing
that configuration.

MMS is included because the framework patch changes the `IMms` Binder API.
Updating its callers and broker without updating `MmsService` leaves four
overrides incompatible and prevents compilation. This patch adds the same
`callingUser` parameter to those declarations; all thirteen implementation
bodies remain unchanged. It is a required API companion, not evidence that
MMS itself enables VoLTE.

## Replay on a fresh source tree

Use the exact base commits in the checkpoint. Do not apply this checkpoint on
top of the historical `ims-20261010` series or run the separate SystemUI and
SA2 renderers afterward: their relevant source changes are already included.
Do not replace entire Cherish projects with donor repositories.

First run the verifier from a checkout of this compatibility repository:

```sh
python3 tools/replay_cherish_source_checkpoint.py --source-root /path/to/cherish
```

The verifier replays each patch through temporary Git indexes and compares
the complete resulting trees. It also reverses the patches and checks the
baseline trees. It leaves the source working tree and real Git index alone.
A pass proves source replay against the locked bases; it does not prove that
the current dirty working tree contains those changes or that Android builds.

For application, first ensure **every destination project is clean** with
`git status --porcelain`. Then apply each manifest entry's patch with `git
apply --check` followed by `git apply`, from that entry's project directory.
Resolve the patch filename relative to the checkpoint directory, not the
Android source root. Stop on a base mismatch, a nonempty status, or an apply
failure. The combined patch includes new Java files as well as tracked-file
edits.

## Remaining acceptance boundary

The public device, vendor and kernel pins in the
[handoff inventory](../devices/m11q/cherish-android13-handoff.json) remain
required. The device overlay enables the otherwise disabled SA2 resource.
Product naming and optional app/OTA selections are recorded in separate
manifest entries with their own roles, rather than being described as IMS fixes.

Samsung private payloads must be produced separately from legally owned raw
stock inputs. This checkpoint contains no APK, DEX, native library, firmware,
signing key or device log. The CWK3 ER1 trio now defines the public strict
contract after the user's accepted fresh build and calls; see
[ER1 provenance](ER1_ERIS_PRIVATE_CRYPTO.md). Historical APK contracts still
retain their exact pins. The newly built IMS candidate was content-checked but
has different primary-DEX and whole-APK hashes, so complete strict APK
reproduction is not claimed by the source checkpoint.

When switching from another ROM, back up needed internal-storage files before
Format Data in TWRP: it erases apps, settings and internal storage. In this
run, Wipe alone left a Keystore/FBE failure and returned to recovery with
`enablefilecrypto_failed`; the user reported boot success after Format Data.
This install result is separate from the source/MMS fixes.

Additional runtime tests must be labelled separately: IMS registration,
outgoing/incoming VoLTE with two-way audio and teardown, SMS, VoWiFi and
handover. The user's normal-call report does not automatically pass that
entire matrix. Android ROM builds remain user-performed.

Publication validation: all 14 project patches replayed and reversed to their
exact trees, with real source indexes and worktrees preserved. The public CLI
was run against the locked source tree. All 49 raw stock-input rows and the
strict ER1 transformation passed verification. The full host tool suite ran
354 tests successfully, with 5 optional environment-dependent tests skipped.
