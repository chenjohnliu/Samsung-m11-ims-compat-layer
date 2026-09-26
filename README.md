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

Stage 3 is the current VoWiFi investigation. It builds on Stage 2, which
extended the original SIM1 voice bring-up to a **single active subscription on
either physical slot** and added an Android 13 IMS SMS bridge. Runtime
validation was performed on one M11 with
CherishOS 4.12 / Android 13, SELinux Enforcing, Taiwan Mobile and stock input
build `M115FXXS5CWK3`.

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
private input or generated output. Other private Stage 3 payload adaptations
remain governed by their documented source/provenance boundaries.

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
- `docs/` — runtime baseline, provenance boundary and release SOP.

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
