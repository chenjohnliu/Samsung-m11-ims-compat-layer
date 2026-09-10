# Samsung Galaxy M11 IMS compatibility layer

Project-authored tooling and documentation for adapting Samsung's stock IMS
stack to Android 13 custom ROMs on the Galaxy M11 (`SM-M115F`, `m11q`). This
repository is source-only: it does not distribute Samsung firmware or a
flashable package.

## Public-release status

The Stage 1 runtime baseline is verified on one device with CherishOS 4.12 /
Android 13, SELinux Enforcing, SIM1 WWAN and stock build `M115FXXS5CWK3`:

- IMS registration;
- outgoing and incoming VoLTE, including ringing, answer, two-way speech and teardown;
- SMS send/receive using the validated IMS-to-SGs/CS fallback path;
- physical SIM1 hot-swap recovery followed by VoLTE and SMS operation.

The verified source checkpoints are compatibility layer `8a3dc34`, device tree
`510d965`, and Telephony `afedb3add`. The verified ROM pre-release was
`20260910-13-rc1`. BQ3 IMS bridge plus BQ6 generic Telephony fallback is the
selected candidate; BQ7 is excluded. A prior cold-boot failure was attributed
to dirty `/data` persistent-state contamination, not a source regression; the
exact contaminating item was not isolated.

This is not a claim of universal carrier or device support. SIM2/DSDS, VoWiFi,
emergency calling, ViLTE, inter-RAT handover, other Samsung models/builds and
general carrier support are unverified and intentionally out of scope.

## Reproducibility boundary

The public checkout contains the fail-closed transformers, contracts, tests,
ABI declaration fixtures and verification tooling. It does not contain the
seven bridge Java implementation files or Samsung-derived compile inputs. The
bridge inventory and expected hashes are recorded in
[`devices/m11q/imsservice-build.json`](devices/m11q/imsservice-build.json).

Therefore a fresh public checkout can reproduce and test the safe transformation
logic, but cannot honestly regenerate the complete verified APK without a
separately obtained bridge-source bundle and the user's legally obtained,
hash-matching Samsung firmware inputs. The required restricted bundle is:

1. the seven bridge Java files listed in `imsservice-build.json`, matching the
   recorded hashes and with provenance/licence evidence;
2. the exact stock files listed in
   [`devices/m11q/payload-manifest.tsv`](devices/m11q/payload-manifest.tsv);
3. the matching Android framework/APK decoding and build tools described in
   [`docs/IMS_APK_BUILDER.md`](docs/IMS_APK_BUILDER.md).

Until the bridge-source provenance is cleared, do not publish that bundle,
Samsung-derived implementations, decoded trees, generated smali, or rebuilt
APK/JAR/SO/ELF files. The builder must fail closed when the restricted bridge
source is absent or its hashes do not match.

## Repository contents

- `tools/` — payload verification, bridge build orchestration, ABI checks and
  narrow fail-closed transformations;
- `devices/m11q/` — input manifest, transformation contracts and bridge
  inventory; no proprietary payload;
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

See [`LICENSE`](LICENSE). The Apache-2.0 license covers only project-authored
material in this repository. Samsung firmware, APKs, JARs, shared libraries,
native executables, carrier data and other stock-derived inputs are excluded
and remain governed by their own terms.

See [`docs/PUBLIC_RELEASE_SOP.md`](docs/PUBLIC_RELEASE_SOP.md) for the
restricted-input workflow and publication gates, and
[`docs/PATCH_PROVENANCE.md`](docs/PATCH_PROVENANCE.md) for source boundaries.
