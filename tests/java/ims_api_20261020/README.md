# IMS API host regression checks

Run the modeled host checks against a local Android source tree and JDK 17:

```sh
python3 tests/java/ims_api_20261020/run_tests.py \
  --source-root /path/to/android/source \
  --java-home /path/to/jdk17
```

`--source-root` must contain `frameworks/base` and
`frameworks/opt/telephony` (the runner also accepts corresponding underscore
paths used by source overlays). `--java-home` is the JDK directory containing
`bin/java` and `bin/javac`. The runner does not assume a machine-specific path.

The runner reads the selected source tree each time. It extracts both
`semGetDataServiceState` overloads and four TelephonyManager methods
(`getSubscriberIdForUiccAppType`, `semGetCallState`, `semGetIsimImpu`, and
`semGetDataState`), plus `PhoneSubInfoController.getSubscriberIdForUiccAppType`.
It compiles those actual method bodies with minimal test stubs. It also compiles
the actual `SemCapabilities.java` from the selected tree with minimal Parcel
stubs and tests static factory behavior, independent builders, feature values,
and parcel round-trip behavior. SHA-256 hashes of the three source files are
included in the JSON result so a run can be tied to its inputs.

The tests cover explicit non-default subscription IDs, pinned and default
subscription behavior, null service-state fallback, location-access
renunciation flags, subscriber-service forwarding including UICC app type and
op package/attribution, legacy data-state remapping, null and service errors,
SecurityException propagation, controller subscription mismatch and
permission/package rejection before UICC access, and SemCapabilities builder
freshness.

These are modeled host checks, not Android framework integration tests. Binder,
real permission enforcement, `com.android.phone`, UICC hardware, the modem,
and radio behavior are stubbed or outside the harness. The controller's
permission helper is modeled only to check that the port calls it before card
data access. A passing run demonstrates behavior of the extracted method
bodies in these models; it does not establish device behavior. The runner does
not build Android, contact a device, or copy Samsung product source into this
test directory. Generated Java files and class files live in a temporary
directory and are removed after each run.
