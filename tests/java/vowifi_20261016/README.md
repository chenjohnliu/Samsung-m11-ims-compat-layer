# M11 VoWiFi pure-Java regression checks

These standalone checks exercise the Samsung M11 packed MTU decoder, IWLAN MTU
lease policy, and IMS audio transition policy without Android framework classes.
They compile only those three helper sources and these harnesses into a temporary
directory; no Android or ROM build is started.

Run inside WSL, passing the framework module roots that contain the helpers:

```sh
python3 tests/java/vowifi_20261016/run_tests.py \
  --telephony-root /path/to/frameworks/opt/telephony \
  --telecom-root /path/to/packages/services/Telecomm \
  --java-home /absolute/path/to/jdk17
```

The runner verifies each helper at its fixed source path against the SHA-256
for this checkpoint before compilation. It leaves source trees untouched and deletes its temporary class output
when it exits.
