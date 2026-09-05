# BC1 manifest transformation

`tools/transform_bc1_manifest.py` applies the project-authored
`BC1-modern-mmtel-discovery` manifest change to a private, locally decoded
`AndroidManifest.xml`. It does not contain or reconstruct Samsung's surrounding
manifest content.

The machine-readable contract is
`devices/m11q/bc1-manifest-contract.json`. It adds exactly one
`com.sec.internal.google.GoogleModernImsService` declaration with:

- `android.permission.BIND_IMS_SERVICE`;
- `enabled`, `exported`, and `singleUser` set to `true`;
- the `android.telephony.ims.ImsService` intent action; and
- `android.telephony.ims.MMTEL_FEATURE=true` metadata.

Emergency MMTEL and RCS are deliberately excluded. They remain outside the
validated Stage 1 scope.

## Use

The destination directory must already exist. The input is never modified.

```bash
python tools/transform_bc1_manifest.py \
  --contract devices/m11q/bc1-manifest-contract.json \
  --input /private/decoded/AndroidManifest.xml \
  --output /private/work/AndroidManifest.bc1.xml
```

An existing output is rejected. `--allow-identical` permits a rerun only when
the existing output is byte-for-byte identical to the newly rendered result;
it never permits replacement of a different file.

The transformer fails closed on package drift, a missing or duplicate
`application`, namespace problems, malformed XML, and any pre-existing target
service, action, MMTEL metadata, emergency-MMTEL metadata, or RCS metadata. It
then parses and semantically validates the rendered bytes before an atomic
write.

## Responsibility boundary

This tool intentionally accepts decoded XML rather than an APK. The outer
builder/orchestrator must first verify the exact stock APK hash and apktool
version/hash recorded in `devices/m11q/imsservice-build.json`, perform the
private decode, and keep decoded and generated files outside the repository.
It must also run the later DEX stages and the ZIP-preserving APK packer. A
successful BC1 manifest transformation alone is not a release or runtime
validation.
