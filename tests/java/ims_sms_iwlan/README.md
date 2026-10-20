# IMS SMS over IWLAN host regression

Run from the repository root with Python 3 and JDK 17:

```sh
python3 tests/java/ims_sms_iwlan/run_tests.py \
  --bridge-root . \
  --java-home /path/to/jdk17
```

`--bridge-root` accepts either the repository root or its `bridge/java`
directory. The runner reads the three bridge source files, extracts the actual
constructor and method bodies under test, and compiles those bodies against
small authored Android/Samsung stubs. It prints SHA-256 hashes for the exact
source files it read and the Java assertion count.

Coverage includes LTE/RAT 13 and IWLAN/RAT 18 SMS registration matching,
stale transport snapshots, phone/service/emergency/CMC filters, unsupported
technologies, independent per-technology capability state and updates,
same-pair state retention and new-pair defaults, owner/bridge availability
gates, and SMSC profile selection for the active transport.

The stubs model registration records, framework capability pairs, backend
state, and SMSC encoding. The harness does not exercise real Android APIs,
Binder, Samsung services, modem delivery, APK packaging, an Android build, or
device behavior. A passing result establishes only that the extracted source
logic satisfies these modeled host cases; it does not establish post-flash
VoWiFi SMS operation.
