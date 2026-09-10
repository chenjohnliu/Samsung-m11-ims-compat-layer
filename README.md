# Samsung Galaxy M11 IMS compatibility layer

Reproducible tooling and documentation for bringing Samsung's stock IMS stack
to Android 13 custom ROMs on the Galaxy M11 (`SM-M115F`, `m11q`).

## Status

This repository is an early **private engineering checkpoint**, not a release or
flashable package.

Confirmed on one device with CherishOS 4.12 / Android 13:

- SIM1 WWAN IMS registration;
- outgoing VoLTE establishment;
- incoming VoLTE ringing and answer;
- clear two-way speech on outgoing and incoming calls;
- outgoing and incoming teardown;
- stable IMS service and registration across an incoming call;
- outgoing SMS delivery through validated IMS-to-SGs/CS fallback;
- SELinux Enforcing throughout the validated call.

Incoming SIP delivery has reached Samsung's userspace call-session path and the
Android 13 `ImsPhoneCallTracker`. Runtime evidence then exposed a synchronous
Binder deadlock in the first modern incoming bridge: it held the bridge owner
monitor while Android synchronously re-entered the call-session facade. The
current reproducible candidate releases that monitor before notifying Android.
Runtime testing on 2026-09-07 confirmed ringing, answer, clear bidirectional
speech and teardown without an IMS process restart or VoLTE-indicator loss.

Not yet claimed: final pure IMS-SMS delivery, SIM2/DSDS, VoWiFi, IMS emergency
calls, ViLTE, inter-RAT handover, other Samsung models, other stock builds, or
general carrier support. On 2026-09-10, the Stage 1BQ3 bridge plus the BQ6
Telephony fallback passed a clean-flash SIM1 hot-swap regression: VoLTE
availability returned after physical SIM removal/reinsertion, outgoing and
incoming calls completed with clear bidirectional speech and teardown, and SMS
send/receive remained functional. The previously suspected BQ7 call-failure
regression was invalidated by a clean-flash control and BQ7 is not part of the
validated candidate. SIM2 currently exposes no
VoLTE/MMTEL support flag, so the validated scope remains SIM1-only.

See the [Stage 1 runtime baseline](docs/STAGE1_RUNTIME_BASELINE.md) for the
acceptance matrix and regression boundary.

## Proprietary-file policy

This repository intentionally contains no Samsung APK, JAR, shared library,
daemon, firmware image, signing key, or decoded stock tree. Users must extract
the exact inputs locally from firmware they are entitled to use. Hash-pinned
tools then verify and transform those inputs.

Current validated stock reference:

```text
Device:  Samsung Galaxy M11 SM-M115F
CSC:     BRI
Build:   M115FXXS5CWK3
Android: 12
```

See [the public-release SOP](docs/PUBLIC_RELEASE_SOP.md) and the
[M11 payload manifest](devices/m11q/payload-manifest.tsv). Reproducible APK and
toolchain identities are centralized in
[`devices/m11q/imsservice-build.json`](devices/m11q/imsservice-build.json).
The historical patch material is being filtered through the conservative
[`docs/PATCH_PROVENANCE.md`](docs/PATCH_PROVENANCE.md) publication boundary.

## Tools currently available

- `tools/verify_payload.py` verifies the 14 declared stock inputs and can stage
  only the explicitly permitted payload categories.
- `tools/build_imsservice.py` performs the complete local clean-stock BC1 →
  BC2 → BG1 → BH1 → BP1 rebuild, generates private compile stubs, compiles the modern
  bridge, preserves every unrelated stock ZIP entry, and emits an unsigned APK
  plus a machine-readable report. See [the builder guide](docs/IMS_APK_BUILDER.md).
- `tools/apk_entry_replace.py` rebuilds a ZIP/APK from a stock base while
  changing only explicitly allowed entries and removing only exact stale v1
  signature entries.
- `tools/verify_framework_abi.py` verifies the local Android 13
  `framework-minus-apex.jar` in exact golden-hash or ABI-compatible mode; see
  [the framework ABI guide](docs/FRAMEWORK_ABI.md).
- `tools/generate_compile_stubs.py` verifies allowlisted declarations in
  private local smali roots and emits disposable compile-only Java ABI stubs.
  It never copies implementations, fields or debug metadata.
- `tools/transform_bc1_manifest.py` performs the fail-closed, MMTEL-only BC1
  manifest transformation without embedding the surrounding stock XML; see
  [the BC1 manifest guide](docs/BC1_MANIFEST.md). The outer builder is
  responsible for stock APK, stock framework and apktool hash pinning.
- `tools/transform_bh1_sms_icc_type.py` replaces only the two Samsung SMS
  fallback calls to the removed Android 12 `IccUtils.getIccType(int)` method
  with a stock-equivalent APK-local property lookup.
- `tools/transform_bc2_native_hooks.py` validates three exact private smali
  targets and emits a three-file overlay containing only the BC2 bridge hooks.
  It never edits or copies the decoded tree; see
  [the BC2 native-hook guide](docs/BC2_NATIVE_HOOKS.md).
- `tools/transform_bg1_stats_guard.py` validates the two exact CWK3 statistics
  classes and emits a two-file overlay that degrades unavailable optional video
  accounting without fabricating a zero-byte result; see
  [the BG1 statistics guide](docs/BG1_STATS_GUARD.md).
- Synthetic unit tests contain no Samsung code or binaries.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

## Work still required before a release

- Re-run the ZIP-preserving builder from a separately fresh firmware
  extraction, rather than the current hash-verified research extraction.
- Build and flash a ROM manually, then repeat the runtime acceptance tests.
- Finalize authorship/licensing for the six project bridge sources so a clean
  public checkout has every non-proprietary source required by the builder.
- Review provenance of stock-derived text configuration and framework
  compatibility source before publication.
- Add a licence for project-authored work after the provenance boundary is
  finalized.

No ROM build is performed by the tools in this repository.
