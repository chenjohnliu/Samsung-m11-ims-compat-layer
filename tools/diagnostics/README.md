# Local diagnostic sources

Source-only copies of the collectors and host helpers used during M11 IMS,
VoLTE, VoWiFi, SMS and audio handover bring-up. Original copies remain in
`D:/m11q/tools`; future edits should be made here.

Captures, PCAPs, generated helper JARs and Samsung input binaries are not included.
These collectors may produce private subscriber identifiers and call/network
information: do not upload their raw output to a public repository.

`capture_ims_media_probe_termux.sh` is the current media collector. Audio trial
mode is opt-in and performs a one-shot stock SAE request; it is a historical
diagnostic experiment, **not** the automatic SA2 handover implementation. Do not
combine manual SAE mode with automatic handover validation.

Host-only regression check (no device actions):

```sh
bash tools/diagnostics/test_ims_media_probe.sh
```

The collectors retain their original local path defaults. Review each script's
options and paths before using it on a different machine. No script is run
automatically by committing these sources.
