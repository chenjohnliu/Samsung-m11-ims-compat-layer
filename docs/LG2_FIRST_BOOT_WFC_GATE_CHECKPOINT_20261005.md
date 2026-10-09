# LG2 first-boot WFC gate checkpoint — 2026-10-05

## Scope and stopping point

User requested inspection of missing VoWiFi after flashing, confirmed the Android
Wi-Fi calling switch was on, then explicitly approved a reversible experiment to
mirror that preference into Samsung's internal switch. No ROM build, flash,
reboot, phone call, APK replacement, or source implementation was performed in
this experiment. User requested a conclusion before quota exhaustion.

## Confirmed observations

- Installed ePDG classes.dex matches LG2:
  `3cc23c6af802802859a1644d3d6187c90a4efcd575c285e0a975a0fae37d0c05`.
  IMS BV1 / bridge and SS1 framework also matched their expected versions in the
  preceding read-only inspection. This is not an old-APK explanation.
- Before the experiment, active subscription 1, slot 0 had Android
  `wfc_ims_enabled=1`, but Samsung `wifi_call_enable1=0`; there was no active
  ePDG Android service. Both call states were idle.
- At 07:13:17 local time, ONLY `wifi_call_enable1` was changed from 0 to 1.
  Samsung WfcEpdgManager received the setting notification, transitioned from
  Disconnected to Connecting, started/bound ePDG, and entered Connected.
  This Connected state denotes the service binding, not a connected IMS tunnel.
- DNS resolution succeeded and Eris started. LG2 now correctly parsed
  `rmnet_data1` as suffix 1 and returned profile ID 2. The earlier prefix / invalid
  CID failure was not reproduced in this attempt.
- IMS tunnel setup still did not complete: IPsec state machine 1 entered
  HandoverConnectingState while its IwlanSetting/APN was null, then timed out
  around 07:13:38. Native IMS remained registered on LTE RAT 13;
  `mIsEpdgConnected=false` and `isOnWfc=false` persisted.
- RILD reported `LoadApnProfile(): SecLoadApnProfFromDB failed`. Read-only
  carrier queries showed four numeric 46697 rows (default/supl and MMS), no IMS
  row for that numeric. `telephony.db` existed under
  `/data/user_de/0/com.android.providers.telephony/databases`, but not under
  `/data/data/com.android.providers.telephony/databases`.
  These are leads, not proof of the exact failing lookup or required remedy.
- A narrower failure was subsequently identified and checked directly in the
  controlled log: at 07:13:18.878 ePDG sent HANDOVER SUSPEND for CID 2;
  at 07:13:18.879 vendor RIL reported
  `RIL_LoadApnProfFromDB: sehRadioService[0]->mSehRadioIndication == NULL`,
  followed by the profile-load failure and
  `TryHandoverCall: Failed to load apn profile` (log lines 32959–32965).
  The missing Samsung vendor radio indication callback is therefore the most
  specific demonstrated upstream blocker in this attempt. Do not misclassify
  the temporary null IwlanSetting as the initiating failure: stock also has a
  temporary null state before its APN attach notification supplies settings.
- Crash buffer was empty during the experiment; Eris was running. There is no
  evidence here of a new ePDG Java crash.
- At 07:16:08, the experimental Samsung setting was restored to its original 0.
  Android `wfc_ims_enabled=1` was explicitly rechecked and unchanged. The ePDG
  service record was still present in the immediate post-restore snapshot; do
  not claim restoration instantly returned every runtime service to its exact
  pre-experiment state. No extra service stop or reboot was forced.
- Continuous log capture was stopped after recording restoration.

## Conclusions / inference boundaries

The Android-versus-Samsung switch split is a demonstrated ePDG startup blocker,
not user error. Mirroring it permits startup but is insufficient for true VoWiFi.
There is a separate downstream legacy APN/profile initialization blocker before
successful IMS tunnel establishment. The failing boundary is now narrowed to
the Samsung vendor radio APN-profile handoff, which explicitly finds its
indication callback null. Why that callback is not initialized remains to be
traced. Missing carrier IMS rows and database path/schema observations must not
supersede the more specific callback failure without additional evidence.

LG2's prefix repair reached its intended parsing checkpoint on this phone, but
does not establish end-to-end WFC success. No true VoWiFi-to-VoLTE call continuity
acceptance result was obtained in this experiment. Icons and data RAT changes
must not be used as substitutes.

## Resume here

1. Trace Samsung vendor radio service / indication callback registration on
   stock versus crDroid and identify who should initialize
   `sehRadioService[0]->mSehRadioIndication`. Follow the RILD APN-profile handoff
   and stock APN_ATTACH_REQ path. Only then investigate remaining provider
   contract details. Do not blindly copy databases, insert APNs, hard-code a
   CID/profile ID, or bypass ePDG's null guard.
2. Design a permanent preference bridge that follows the active Android user
   choice and handles slot/subscription readiness. Do not force WFC enabled or
   equate a capability-enable callback with user preference without checking
   its lifecycle semantics.
3. Implement only with appropriate user authorization, run non-ROM-build tests,
   and consolidate build/flash validation for the user.
4. Require real native IWLAN IMS registration and a connected IPsec tunnel
   before asking the user to repeat handover calls. Then validate original call
   session preservation and bidirectional audio, not icons.

## Private evidence (local only)

`D:\m11q\work\lg2_wfc_gate_sync_20261005\` contains:

- `live_logcat_private.txt` — includes buffered earlier logs; relevant controlled
  experiment begins 07:13:17, not the start of the file.
- `after_sync_secims_private.txt`, `settled_secims_private.txt`.
- `apn_and_crash_private.txt`, `apn_rows_private.txt`.
- `reverted_secims_private.txt`.

`ims_apn_schema_private.txt` is an unsuccessful quoting/query attempt, not a
valid schema result. Do not rely on it. Earlier boot evidence is in
`D:\m11q\work\lg2_boot_status_20261005_0703\`.

Do not publish raw private logs, subscriber identifiers, or proprietary APKs.
