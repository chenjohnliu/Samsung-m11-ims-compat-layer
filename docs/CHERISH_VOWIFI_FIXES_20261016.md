# CherishOS initial VoWiFi audio and legacy MTU corrections

The 2026-10-16 supplement fixes two separate paths on m11q: initial incoming
Wi-Fi call audio startup and MTU handling for the modem-led legacy IWLAN path.
The maintainer built and flashed these sources manually. Incoming calls on a
tested home Wi-Fi network completed with speech in both directions; a later
call also exercised handset, speaker and return to handset. This is a source
supplement to the earlier acceptance, not a new downloadable ROM release.

## Changes and scope

- **Initial incoming audio:** extend the existing opt-in, single-active-SIM
  Samsung Telecom hook to eligible initial Wi-Fi incoming calls. Follow the
  observed startup sequence using call state 32, audio mode 3 and delayed-media
  notification 7. Track the owning call and clear its initial-call parameters
  when ownership or eligibility ends. Preserve the existing LTE/Wi-Fi handover
  sequences and Bluetooth path.
- **Legacy MTU:** on m11q legacy IWLAN only, decode recognized packed IPv4/IPv6
  MTUs in old HIDL scalar responses. Preserve ordinary scalar values and leave
  the newer typed responses unchanged. For an eligible dedicated IMS network
  with one active subscription and an actual MMTEL IWLAN registration callback,
  cap the source MTU at 1400. Preserve an already lower kernel MTU. A lease
  tracks interface identity and external changes so restoration cannot overwrite
  a replacement interface or a newer modem/kernel value. Default-data and
  emergency networks are excluded from this cap.

These patches do not replace the audio HAL or change codecs, add fixed startup
delays, or change the historical APK producer contracts.

## Application order

The [source index](SOURCE_INDEX.md) also links complete Telephony and Telecom
fork branches that contain these corrections and their prerequisites. Their
fixed commits and full Git trees match the patch route below. If using those
indexed fork commits, skip the entire patch chain for those two projects.

Start with the locked [combined checkpoint](CHERISH_SOURCE_CHECKPOINT.md), then
the two new patches in the [2026-10-12 IMS supplement](CHERISH_LOCAL_IMS_PATCHES_20261012.md).
Its MMS copy is already in the combined checkpoint and must not be applied again.
Apply this supplement once after those prerequisites. In particular, Telecom
requires the earlier `secims-permission.patch` before the new audio patch.

The [manifest](../platform/checkpoints/cherish-20261016-vowifi/manifest.json)
records source bases, prerequisite and result trees, patch hashes, changed paths,
and before/after file hashes. Isolated replay and reverse replay passed for both
projects; the resulting affected files matched the maintainer's tested sources.
The earlier checkpoint and its pins remain unchanged.

From a Linux/WSL shell, set these paths to your checkouts. Both checks must pass
before applying either patch:

```sh
CHERISH_SOURCE_ROOT=/absolute/path/to/cherish
COMPAT_ROOT=/absolute/path/to/Samsung-m11-ims-compat-layer
VOWIFI_SUPPLEMENT="$COMPAT_ROOT/platform/checkpoints/cherish-20261016-vowifi"

git -C "$CHERISH_SOURCE_ROOT/packages/services/Telecomm" apply --check "$VOWIFI_SUPPLEMENT/packages__services__Telecomm/initial-wifi-audio.patch"
git -C "$CHERISH_SOURCE_ROOT/frameworks/opt/telephony" apply --check "$VOWIFI_SUPPLEMENT/frameworks__opt__telephony/legacy-iwlan-mtu.patch"

git -C "$CHERISH_SOURCE_ROOT/packages/services/Telecomm" apply "$VOWIFI_SUPPLEMENT/packages__services__Telecomm/initial-wifi-audio.patch"
git -C "$CHERISH_SOURCE_ROOT/frameworks/opt/telephony" apply "$VOWIFI_SUPPLEMENT/frameworks__opt__telephony/legacy-iwlan-mtu.patch"
```

Run the [three standalone Java regression harnesses](../tests/java/vowifi_20261016/README.md)
against the patched module roots. They cover the packed decoder, MTU lease policy
and audio transition policy; all three passed with JDK 17. They do not compile
Android framework integration or replace device testing. No Android build was
run by the agent.

## Device evidence and remaining work

A controlled sequence on the same home Wi-Fi network compared a temporary
source MTU of 1400, the original 1500, and a reduced source MTU again. The reduced
MTU calls worked; the 1500 call disconnected during answer negotiation. The
successful audio capture included the initial Wi-Fi startup sequence and SAE
channel/input/output activity. This supports addressing MTU and initial audio
as separate issues, rather than attributing both to a speaker route change.

With the permanent source changes installed, a call near the AP lasted about
81 seconds, retained its Wi-Fi calling icon, and passed handset → speaker →
handset audio checks. That call used two nearby phones operated by the maintainer;
a separate outgoing call to a remote person confirmed normal two-way speech.
An outgoing service-announcement test then stayed connected for about 112 seconds,
with audible downlink, the icon retained, and sampled source MTU 1400 throughout.
Its sampled Wi-Fi stayed connected, interface/XFRM error deltas stayed zero, and
no explicit W2L/CPVE marker was captured. A service announcement does not verify
uplink. Its WLAN packet capture hit the record cap before hangup, so packet
coverage was incomplete even though the state samplers continued.

The remote-person outgoing call was also the call where the status-bar VoWiFi
icon was noticed missing after hangup; it later returned by itself. Call-time
coverage was incomplete and that symptom was not reproduced in the service
test. Its cause remains unresolved. The latest changes have not received a new
complete VoLTE, both-direction handover, both-slot, conference, call-waiting,
subscription-loss or long-duration regression batch. Earlier acceptance does
not substitute for those regressions on this source revision.

Stock CWK3 also had home-network incoming-call failures in earlier tests, but
the available stock captures do not establish that their cause was this port's
MTU decoding or that these patches fix stock. Stock already decoded its packed
MTU fields. No raw captures, subscriber details or Samsung binaries are included
in this supplement.
