# BC2 native-hook transformation

BC2 connects the locally built modern MmTel bridge to three narrowly scoped
locations in Samsung's IMS service. The public repository stores the hook
logic and ABI identities, but never stores decoded Samsung smali or a patched
APK.

## What the transformer changes

The machine-readable contract permits exactly these operations:

1. add two accessors to `GoogleImsService`: a ready-instance accessor and an
   incoming-call binder identity accessor;
2. pass the constructor listener in `ImsCallSessionImpl` through
   `ModernCallRelay.constructionListener` before assigning it;
3. offer an incoming callback in `ImsNotifier` to
   `ModernVoiceContext.onIncoming`, falling back to the legacy listener when
   the bridge does not consume it and skipping a null legacy listener.

No BC1 discovery skeleton is required or deleted. The current one-shot design
adds the BC1 service declaration at the manifest layer only.

## Isolation and fail-closed behavior

The input must be a private apktool-decoded smali root produced by the future
outer hash-pinning workflow. The transformer reads exactly three regular files
at fixed safe relative paths. It checks each class/superclass, required field,
target method, anchor occurrence, pre-application state and available local
registers before producing anything.

Output is a new overlay tree containing exactly three complete transformed
smali files. The decoded input is never changed and unrelated input files are
not copied. The JSON report contains only the transformation ID, relative
target paths, public hook IDs and input/output SHA-256 values. Both overlay and
report default to non-overwrite; `--allow-identical` accepts only a byte-for-byte
identical repeat.

Example using placeholder private paths:

```text
python tools/transform_bc2_native_hooks.py \
  --contract devices/m11q/bc2-native-hooks-contract.json \
  --input-smali-root PRIVATE_TEMP/decoded/smali \
  --output-overlay PRIVATE_TEMP/bc2-overlay \
  --report PRIVATE_TEMP/bc2-report.json
```

The outer builder will copy the three overlay files into its own disposable
decoded working tree before apktool assembly. The overlay and report remain
private build artifacts and must never be committed.

## Validation scope

Synthetic tests cover success, class/method/descriptor/anchor/register drift,
duplicate anchors, already and partly applied states, hooks outside allowlisted
methods, preservation of unrelated method bytes, compatibility of the two new
service methods with the compile-stub contract, output conflicts, identical
repeats, symlinks, rollback and report privacy.

The transformer has also been exercised privately against the decoded CWK3
BC1 tree. Its three hook effects match the historical runtime-validated BC2
semantics. This source-level check does not validate a newly packaged APK: the
future ZIP-preserving candidate still requires manual ROM build, flash and
on-device acceptance testing.
