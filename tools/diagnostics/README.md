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

## Wi-Fi cycle capture privacy

`capture_ims_wifi_cycle_termux.sh` is a standalone Bash/Termux collector; its
redactor uses Termux GNU sed, with no Python dependency on the phone. It also
requires coreutils `od` to generate a per-capture address fingerprint salt.

The Wi-Fi cycle collector keeps raw logcat, dumps, runtime identity, and user
observations under `_PRIVATE_DO_NOT_SHARE/`. `PRIVATE_FULL_CAPTURE.tar.gz`
archives those original bytes before share sanitization is attempted. Neither
that directory nor that archive is safe to publish. Keep the whole capture
directory private: `SHARE_THIS/` can still contain unsanitized or partially
sanitized text after an interrupted or failed run.

Only `SHARE_THIS.tar.gz` is the intended sharing artifact. Its text files are
sanitized again before packing. Unexpected directories, symlinks, NUL-containing
files, identifier-like filenames, and sanitization failures stop publication.
The share tar is written to a temporary file and renamed only after tar succeeds;
capture directories are never reused. Use neutral snapshot labels such as
`a_baseline`, not names, phone numbers, or subscriber identifiers.

The redactor covers common labelled IMSI/ICCID/IMEI/IMPI/IMPU aliases, quoted and
array values, SIP/TEL URIs and identity/authentication headers, NAI/email values,
Taiwan mobile/landline and international formatted phone numbers, MAC, IPv4,
and full/compressed/mixed IPv6 addresses with scope identifiers. Clock and ISO
timestamps, fault codes such as 503/5065, RAT/slot/call IDs, and handover markers
remain available. Address-line fingerprints are salted within each capture;
the salt is private, so use them for comparisons within that run, not across runs.

Additional aliases cover original/calling/called/remote numbers, Wi-Fi/WLAN SSID
and BSSID, IPsec/IKE/ESP/XFRM authentication/encryption keys and PSKs, and
authorization/access/refresh/bearer tokens. Colon and equals assignments,
camelCase/underscore names, quoted/array values, and unquoted multiword SSIDs
are covered. Standalone Bearer/Basic token payloads and common XFRM algorithm
plus hex-key output are masked too. Known diagnostic fields, clocks, and markers
bound unquoted free-text values so following handover information can survive.
SIP Digest headers are removed as a whole because their parameters are sensitive.

The fake Android packaging test feeds the review fixtures through raw logcat,
summary commands, runtime properties, logger stderr, and manual observations.
It checks every final share file, explicitly including
`key_timeline_redacted.txt`, while comparing the private log bytes to the original
synthetic fixture. None of these tests invokes Android commands on a real device.

This is heuristic redaction, not a guarantee of anonymity. Unlabelled names,
free text, escaped/multiline/encoded values, unusual phone formats, and unknown
credential formats can escape filtering. Some ambiguous numeric text or header
content may be removed. Unquoted free-text boundaries are heuristic: a value that
looks like diagnostic metadata can be misinterpreted, and unknown trailing fields
may be removed. Device/build/operator details and event timing can still
identify a capture indirectly. Manually review every share archive before
publishing. This change does not sanitize other collectors, existing captures,
or Git history; `.gitignore` also does not remove already tracked data.

Host regression tests use invented fixtures and fake Android commands only:

```sh
python3 -m unittest discover -s tests -p test_ims_wifi_cycle_privacy.py -v
bash -n tools/diagnostics/capture_ims_wifi_cycle_termux.sh
```
