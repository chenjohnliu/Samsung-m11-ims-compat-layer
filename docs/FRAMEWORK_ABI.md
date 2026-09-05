# Android framework ABI gate

The project-authored Android 13 bridge compiles against system and hidden IMS
interfaces that are not fully represented by the public SDK `android.jar`.
`framework-minus-apex.jar` is therefore a user-supplied local Android build
artifact. It is never committed to this repository.

Run the strict golden check with the framework JAR produced by the validated
CherishOS 4.12 tree:

```bash
python tools/verify_framework_abi.py /path/to/framework-minus-apex.jar \
  --mode golden --javap /path/to/javap --report out/framework-abi.json
```

Golden mode requires both the exact JAR SHA-256 in
`devices/m11q/imsservice-build.json` and exact normalized `javap` output for the
two checked-in Binder interfaces.

For an independently built Android 13 tree, compatible mode permits a different
whole-JAR hash but still requires both ABI fixtures to match exactly:

```bash
python tools/verify_framework_abi.py /path/to/framework-minus-apex.jar \
  --mode compatible --javap /path/to/javap
```

A compatible-mode result whose whole-JAR hash differs is classified as
`compatible-abi-only`; it is not a golden or runtime-validated target. Line
endings and trailing whitespace are normalized. Method ordering, signatures
and all other content must match exactly. Missing fixtures, invalid
configuration, a failed `javap`, or either ABI difference is a hard failure.

Fixture paths in the build manifest are relative to the explicitly declared
`abi_fixture_root`. Individual fixture paths must be canonical, root-relative
paths and cannot contain `..` traversal.

The fixtures are normalized `javap` signature listings generated from the two
Android 13 AOSP Binder interfaces named in the build manifest. The underlying
AOSP interface definitions are Apache-2.0 licensed. The generated listings
contain no implementation bodies or Samsung classes; they are kept only as the
minimum compatibility gate needed to compile the project-authored bridge.
