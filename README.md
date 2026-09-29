# Samsung Galaxy M11 IMS compatibility layer

Project-authored tooling and documentation for adapting Samsung's stock IMS
stack to Android 13 custom ROMs on the Galaxy M11 (`SM-M115F`, `m11q`). This
repository is source-only: it does not distribute Samsung firmware or a
flashable package.

## Reference and acknowledgement

This project was developed with reference to
[`myesxc/Samsung-s20-ims-compat-layer`](https://github.com/myesxc/Samsung-s20-ims-compat-layer).
Its staged compatibility-layer and stock-APK adaptation approach informed this
work, which was then modified and independently validated for the Galaxy M11,
its pinned firmware inputs, and the runtime scope documented below.

## Current project status

Stage 3 is the current VoWiFi compatibility and validation stage. It builds on
Stage 2, which extended the original SIM1 voice bring-up to a **single active
subscription on either physical slot** and added an Android 13 IMS SMS bridge. Runtime
validation was performed on one M11 with
CherishOS 4.12 / Android 13, SELinux Enforcing, Taiwan Mobile and stock input
build `M115FXXS5CWK3`.

A separate Android 13 crDroid restoration and porting record is available in
[`docs/CRDROID_ANDROID13_IMS_RESTORATION.md`](docs/CRDROID_ANDROID13_IMS_RESTORATION.md).
Static comparison found all nine known runtime patch groups from the public
CherishOS forks in the crDroid source trees; no omitted patch from that known
set was found. The port has passed direct-LTE, outgoing VoWiFi and incoming
VoWiFi calls with bidirectional audio and normal teardown. The crDroid-specific
incoming-media fix asks Samsung `secims` to start the slot audio path only after
Telecom enters `MODE_IN_CALL`; it is gated by an m11q resource overlay and does
not change other devices by default. Cross-ROM acceptance remains incomplete:
before the handover workaround, an outgoing INVITE after IWLAN-to-LTE received
SIP 487. The published M11 CarrierConfig fix forces a fresh bearer for idle
transitions on the tested PLMN and disconnects an active VoWiFi call when Wi-Fi
is disabled. It is public in device-tree commit
[`d11cbe58`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/d11cbe58dfdf81c284788c50e5b6e37de47cf5d4).
The incoming-media integration is public in Telecom commit
[`66d3d91d`](https://github.com/chenjohnliu/android_packages_services_Telecomm/commit/66d3d91d238436c9a04cd4b653f3db02db4f901e)
and device-tree commit
[`29fc1533`](https://github.com/chenjohnliu/android_device_samsung_m11q/commit/29fc1533c06fe54ef80d3808698d33edd93caed8).
See the
[`Android 13 ROM bring-up guide`](docs/M11_ANDROID13_ROM_BRINGUP.md) for the
reproducible inputs, remaining manual port steps, and validation matrix.

The following behavior has been validated with one active SIM at a time:

- IMS registration on SIM1 and SIM2;
- outgoing and incoming VoLTE, including ringing, answer, two-way speech and
  teardown;
- SMS send and receive on SIM1 and SIM2;
- incoming SMS delivery from Samsung IMS into Android, including the corrected
  Samsung message-ID acknowledgement path;
- physical SIM1 hot-swap recovery followed by VoLTE and SMS operation.

Outgoing SMS is functionally validated, but the transport result must be stated
precisely. In the captured Taiwan Mobile transaction, Samsung IMS sent a SIP
`MESSAGE` and received SIP `202 Accepted`, followed by RP cause 50. Android then
completed the message through the modem fallback path. The newer active-SIM
SMSC E.164 normalization candidate is deterministic and structure-verified but
has not yet been validated on-device as a successful end-to-end outgoing IMS
SMS transaction. Therefore this project does **not** currently claim pure IMS
transport for outgoing SMS.

The selected Stage 1 recovery baseline remains BQ3 IMS bridge plus BQ6 generic
Telephony fallback; BQ7 is excluded. Stage 2 adds the single-active slot policy
and IMS SMS compatibility changes. See
[`docs/STAGE1_RUNTIME_BASELINE.md`](docs/STAGE1_RUNTIME_BASELINE.md) and
[`docs/IMS_APK_BUILDER.md`](docs/IMS_APK_BUILDER.md) for the evidence and build
boundaries.

Concurrent dual-SIM / DSDS operation is intentionally unsupported and
unvalidated; SIM2 support here means SIM2 works as the one active subscription,
not that two subscriptions can remain active together. Emergency calling,
ViLTE, inter-RAT handover, other Samsung models/builds and general carrier
support also remain unverified.

> **Release warning:** Emergency calling is not validated; do not rely on this
> ROM for emergency communications. See
> [`docs/EMERGENCY_CALLING_AUDIT.md`](docs/EMERGENCY_CALLING_AUDIT.md) for the
> source audit, framework routing correction and strictly no-dial validation
> boundary.

Stage 3 VoWiFi is runtime-validated on the tested M11/Taiwan Mobile combination
for an outgoing call to 188 and an incoming call from another handset. The 188
call stayed connected, played audible service audio and ended normally. After
BT1 moved the incoming-call SAE audio-interface update to the post-ESTABLISHED
state, the incoming call had bidirectional audio and no longer disconnected at
about 16 seconds. This remains a scoped result: emergency calling, inter-RAT
handover, alternate audio devices, concurrent dual-SIM operation, other
carriers and other stock builds/models remain unverified. Earlier
LTE-only/WFC-disabled and pre-BT1 captures describe investigation states, not
the current build. See
[`docs/STAGE3_MT_VOWIFI_MEDIA.md`](docs/STAGE3_MT_VOWIFI_MEDIA.md) for the fix
boundary and evidence, and
[`docs/STAGE2_VOWIFI_HANDOFF.md`](docs/STAGE2_VOWIFI_HANDOFF.md) for the
historical handoff.

## Reproducibility boundary

The public checkout contains the seven project-authored bridge Java sources,
fail-closed transformers, contracts, tests, ABI declaration fixtures and
verification tooling. The bridge inventory and expected hashes are recorded in
[`devices/m11q/imsservice-build.json`](devices/m11q/imsservice-build.json).

Therefore a fresh public checkout can reproduce the complete project-authored
logic when the user supplies legally obtained, hash-matching Samsung firmware
inputs and the documented build toolchain. The pinned IMS bridge source was
promoted only after two deterministic `PIN_DISCOVERY` runs produced identical
DEX and unsigned-APK identities. The default strict mode can regenerate and
publish that exactly pinned unsigned APK. Build reproducibility does not, by
itself, establish additional VoWiFi runtime behavior. The required private inputs are:

1. the exact stock files listed in
   [`devices/m11q/payload-manifest.tsv`](devices/m11q/payload-manifest.tsv);
2. the matching Android framework/APK decoding and build tools described in
   [`docs/IMS_APK_BUILDER.md`](docs/IMS_APK_BUILDER.md).

Stage 3 stock inputs and locally derived outputs have different handling; see
[`docs/STAGE3_PAYLOAD_INPUTS.md`](docs/STAGE3_PAYLOAD_INPUTS.md). The public
checkout automates the BT1 Samsung IMS transformation without publishing its
private input or generated output. It also provides UW1 for the pinned
`UnifiedWFC.apk` method and ER1 for the three-file ERIS private crypto closure.
SV1 and EC1 now reconstruct `sveservice.apk` and `EpdgService.apk` directly
from their exact stock APKs while preserving every unrelated APK entry. Neither
builder consumes a saved decoded tree, patched DEX, or final APK. See
[`docs/SV1_SVESERVICE_MEDIA.md`](docs/SV1_SVESERVICE_MEDIA.md),
[`docs/EC1_EPDGSERVICE_ANDROID13_COMPAT.md`](docs/EC1_EPDGSERVICE_ANDROID13_COMPAT.md),
and
[`docs/STAGE3_REMAINING_PAYLOAD_STATUS.md`](docs/STAGE3_REMAINING_PAYLOAD_STATUS.md).

Both fresh builders were run twice and produced deterministic unsigned APKs.
Their transformed class structures reproduce the historical runtime-validated
implementations, but the newly repacked unsigned APK files have not themselves
been platform-signed, flashed and separately revalidated on the phone.

Do not publish Samsung-derived implementations, decoded trees, generated smali,
or rebuilt APK/JAR/SO/ELF files. The builder fails closed if a bridge source is
missing or differs from its reviewed hash.

## Repository contents

- `tools/` — payload verification, bridge build orchestration, ABI checks and
  narrow fail-closed transformations;
- `devices/m11q/` — input manifest, transformation contracts and bridge
  inventory; no proprietary payload;
- `bridge/java/` — project-authored Stage 1 voice baseline, Stage 2
  single-active-slot and IMS SMS bridge, and Stage 3 VoWiFi lifecycle fixes;
- `bridge/abi/` — declaration-only Android 13 ABI fixtures;
- `tests/` — synthetic tests without Samsung binaries or implementations;
- `patches/` — project-authored Android source corrections kept separate from
  proprietary payloads;
- `docs/` — runtime baseline, provenance boundary and release SOP.

The repository currently provides deterministic local payload builders and
source references, but not a one-command firmware extractor or an ordered,
preflighted source patch series for every Android 13 ROM. The bring-up guide
states the exact boundary and avoids claiming that a clean checkout of an
arbitrary ROM is already reproducible.

Run the source-only validation suite:

```bash
python -m unittest discover -s tests -v
```

No Android ROM build is performed by this repository. Users build ROMs
manually after preparing their own permitted inputs.

## Licensing and proprietary inputs

See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). The Apache-2.0 license covers only project-authored
material in this repository. Samsung firmware, APKs, JARs, shared libraries,
native executables, carrier data and other stock-derived inputs are excluded
and remain governed by their own terms.

See [`docs/PUBLIC_RELEASE_SOP.md`](docs/PUBLIC_RELEASE_SOP.md) for the
private-stock-input workflow and publication gates, and
[`docs/PATCH_PROVENANCE.md`](docs/PATCH_PROVENANCE.md) for source boundaries.
The completed fresh extraction and non-ROM rebuild are recorded in
[`docs/FRESH_EXTRACTION_VALIDATION.md`](docs/FRESH_EXTRACTION_VALIDATION.md).
