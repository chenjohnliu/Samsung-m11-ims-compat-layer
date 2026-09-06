# BG1 optional video-statistics guard

BG1 prevents Samsung IMS cleanup from calling a network-statistics API family
that is absent from the selected Android 13 framework. It is an optional
accounting compatibility layer: it does not restore traffic accounting and it
does not repair IMS registration, dedicated bearers, SIP, or audio.

## Transformation boundary

The machine-readable contract pins exactly two CWK3 classes:

1. `NetworkStatsOnPortHandler`, which owns the optional start/stop/query family;
2. `CallStateMachine`, which forwards a measured value to the media controller.

The transformer accepts only the exact apktool 2.9.3 decoded input bytes. It
validates class and superclass access, required method identities, narrow
anchors, absence of partial prior application, and preservation of every
unrelated method.

The generated behavior probes all three framework methods with their parameter
and return types before use. An absent ABI or a narrow linkage/backend failure
marks statistics unavailable. The internal negative sentinel is never reported
as usage: the callback is suppressed, while a genuine measured zero remains a
valid result. Start, stop and query state use the same instance monitor, and
cleanup still clears local reporting and port state. No blanket `Throwable`
catch is introduced.

## Private local use

Run against a fresh, private decoded smali root using placeholder paths:

```text
python tools/transform_bg1_stats_guard.py \
  --contract devices/m11q/bg1-stats-guard-contract.json \
  --input-smali-root PRIVATE_TEMP/decoded/smali \
  --output-overlay PRIVATE_TEMP/bg1-overlay \
  --report PRIVATE_TEMP/bg1-report.json
```

The tool never edits or copies the whole decoded input tree. It emits only the
two transformed complete smali files and a privacy-safe hash report. Both
outputs default to non-overwrite; `--allow-identical` permits only an identical
repeat. The overlay is Samsung-derived build material and must not be committed
or published.

The implemented outer builder merges this overlay into its disposable decoded
tree after applying BC1 and BC2, then rebuilds only the primary DEX and
preserves the BC2 bridge DEX byte-for-byte. APK assembly and ROM signing remain
outside this transformer's scope.

## Validation scope

Synthetic tests cover success, immutable contract identity, stock byte/hash and
ABI drift, anchors, already/partly applied states, unrelated-method
preservation, exact guard semantics, conflicts, identical repeats, symlinks,
atomic rollback and report privacy.

The tool has also been exercised privately against the exact CWK3 decoded
classes used before BC1/BC2. Its two outputs match the historical BG1 generation
after blank-line normalization. The resulting one-command package is now
statically reproducible, but that source equivalence and packaging validation
do not replace on-device runtime validation.
