# Stage 3 VoWiFi source audit

Date: 2026-09-13

> Historical audit note: this document records the initial Stage 3 source and
> integration review. Its statement that no runtime success was claimed was
> correct on 2026-09-13, but has been superseded by the 2026-09-26 runtime
> validation. Outgoing VoWiFi to 188 and incoming VoWiFi with bidirectional
> audio are now confirmed for the tested M11/Taiwan Mobile setup. See
> `STAGE3_MT_VOWIFI_MEDIA.md`; later sections below remain useful as chronology
> and should not be read as the current project status.

## Outcome

The first custom-ROM VoWiFi candidate now packages the Samsung ePDG service and
native backend together with a device CarrierConfig allowlist for Taiwan's four
statically supported PLMNs. It does not add carrier branches to the IMS bridge.
Unknown carriers remain fail-closed.

No Android build was run and no runtime success was claimed by this audit at
the time it was written.

## Source state reviewed

- Public compatibility repository: `b07c19b` (`Complete Stage 2 IMS SMS
  compatibility`). The pre-existing uncommitted `README.md` update was left
  untouched.
- Device tree: `706e607` on `m11q-volte-stage1`. The pre-existing
  `AndroidProducts.mk` modification was left untouched.
- AOSP CarrierConfig: clean `android-13.0.0_r82` baseline at `bb1e0f2`.
- The current IMS APK and integration files were inspected in place. No IMS
  bridge, SMS, SIM-slot, or hot-swap source was changed.

## Confirmed gates already present

The current device source already declares the device-level capability:

- `device/samsung/m11q/overlay/frameworks/base/core/res/res/values/config.xml`
  sets `config_device_wfc_ims_available=true`.
- `device/samsung/m11q/device.mk` sets `ro.vendor.epdg.support=true`.
- `device/samsung/m11q/manifest.xml` declares Samsung radio-channel instances
  `epdgd` and `epdgd2`.
- `device/samsung/m11q/ims` packages the exact CWK3 `EpdgManager.jar` and its
  shared-library declaration.
- The Qualcomm data configuration enables IWLAN for the relevant hardware
  targets in `vendor/samsung/m11q/proprietary/vendor/etc/data/netmgr_config.xml`.

These declarations are necessary, but they do not implement the ePDG tunnel.

## Confirmed 46697 carrier evidence

The bundled CWK3 Samsung data explicitly supports the tested Taiwan Mobile
subscription:

- `mnomap.json` maps MCC/MNC `46697` to `TWM_TW`.
- `imsswitch.json` enables IMS, VoLTE, VoWiFi, and SMS over IMS for `TWM_TW`.
- `imsprofile.json` contains the `TWM Mobile VoLTE` profile with representative
  PLMN `46697`; its `nr,lte,wifi` network supplies `mmtel` and `smsip`.
- `globalsettings.json` contains TWM-specific VoWiFi behavior.
- Stock `epdg_apns_conf.xml` contains the TWM IMS APN, EAP-AKA/IPsec policy,
  `epdg.epc.mnc097.mcc466.pub.3gppnetwork.org`, `epdgenable=on`, handover
  support, and WFC menu support.
- Android carrier ID `1888` maps only to `46697` in this Android 13 carrier-ID
  database. The existing CarrierConfig asset is
  `carrier_config_carrierid_1888_台灣大哥大-Taiwan-Mobile-Telecom.xml`.
- Stock CWK3 runtime previously established ePDG and registered `mmtel` plus
  `smsip` over IWLAN/RAT 18 with this device and subscription.

This is sufficient evidence for a removable 46697 validation entry. It is not
evidence for enabling other carriers.

## Confirmed pre-change backend gap

Before the candidate was applied, stock CWK3 contained all of the following
while the device/vendor source did not package them:

- `/system/priv-app/EpdgService/EpdgService.apk` (`com.sec.epdg`);
- `/system/etc/epdg_apns_conf.xml`;
- `/system/etc/permissions/privapp-permissions-com.sec.epdg.xml`;
- `/system/bin/eris` and `/system/etc/init/init.rilepdg.rc`;
- 32-bit `liberis_strongswan.so`, `liberis_charon.so`, and
  `liberis_simaka.so`.

The EpdgService manifest supplies Samsung's `EpdgService` plus Android
`IwlanDataService`, `IwlanNetworkService`, and
`EpdgQualifiedNetworksService`. It uses shared UID `android.uid.system`, targets
API 31, and optionally uses `EpdgManager` and `imsmanager`.

The native `eris` executable is a 32-bit Android 31 binary. It directly needs
the three `liberis_*` libraries, `libsecril-client.so`, and standard platform
libraries. Its stock init service runs as `system`, has `NET_ADMIN`,
`NET_BIND_SERVICE`, and `NET_RAW`, and uses a dedicated `eris_exec` SELinux
label.

The base AOSP source has no declarations for Samsung permissions requested by
EpdgService, including `com.ipsec.client.permission.MANAGING_VPN`,
`com.sec.android.SAMSUNG_TUNTAP`, and
`com.sec.android.SAMSUNG_MODIFY_IPTABLES`, and it has no eris/ePDG SELinux
policy. These are runtime STOP conditions, not cosmetic omissions.

The stock vendor CIL confirms that eris is a dedicated tunnel domain rather
than a generic IMS helper. Its contract includes the eris control socket and
data directory, TUN creation/ioctl and relabel operations, NET_ADMIN/NET_RAW,
the multiclientd socket, rild TUN relabel interaction, hwservicemanager and
system-suspend Binder access, plus file-descriptor/UDP-socket handoff to the
system app and system server. Translating this API-31 Samsung policy into the
current split-policy tree still requires deliberate review; the exact stock
rules are evidence, not an `audit2allow` template.

The TWM stock entry uses `certi_path=none` and `is_using_certi=0`, so the
carrier-specific certificate directories are not part of the minimum 46697
validation payload. They must be revisited before enabling carriers whose
profiles require them.

## Lowest-risk complete design

The first candidate should be device-scoped and carrier-selected, with all of
the following delivered in one change:

1. Package the exact CWK3 EpdgService, eris backend, three direct native
   dependencies, TWM-capable `epdg_apns_conf.xml`, stock init contract, and
   stock privapp grants. Re-sign EpdgService with the ROM platform certificate
   because it uses `android.uid.system`.
2. Add narrowly reviewed declarations for the Samsung signature permissions
   used by this payload. Do not grant equivalent permissions to unrelated apps.
3. Add a dedicated eris domain and the minimum ePDG service policy. Do not
   reuse broad IMS policy and do not import generated `audit2allow` output.
4. In carrier ID 1888 only, set
   `carrier_wfc_ims_available_bool=true`. Preserve the stock/TWM opt-in default
   by leaving `carrier_default_wfc_ims_enabled_bool=false`; the tester must
   explicitly enable Wi-Fi Calling.
5. In the same carrier asset, set the carrier-scoped WLAN data service, WLAN
   network service, and qualified-networks service package overrides to
   `com.sec.epdg`. Android 13 gives these overrides precedence over the empty
   device resource defaults. This keeps unknown carriers fail-closed.
6. Verify `ro.telephony.iwlan_operation_mode` at runtime. With the declared
   radio HAL version the Android 13 default is inferred to be AP-assisted, but
   the effective value must be captured rather than assumed.

Do not set global Telephony WLAN service overlays to `com.sec.epdg` for the
first candidate. Carrier-scoped overrides are the safer extensible mapping and
avoid binding an unverified backend for unknown carriers.

### Proposed carrier-ID 1888 values

The following is a design record, not an applied patch:

```xml
<boolean name="carrier_wfc_ims_available_bool" value="true"/>
<boolean name="carrier_default_wfc_ims_enabled_bool" value="false"/>
<string name="carrier_data_service_wlan_package_override_string">com.sec.epdg</string>
<string name="carrier_network_service_wlan_package_override_string">com.sec.epdg</string>
<string name="carrier_qualified_networks_service_package_override_string">com.sec.epdg</string>
```

The keys belong in the existing carrier-ID 1888 asset, not a new
`carrier_config_mccmnc_46697.xml`: Android's CarrierConfig loader prefers the
known carrier-ID asset, and its tests reject an MCC/MNC asset when a carrier ID
exists.

## Applied source candidate

The device source now includes one bounded backend-integration candidate:

- exact CWK3 `EpdgService.apk`, `eris`, `epdg_apns_conf.xml`, the three direct
  `liberis_*` dependencies, and the matching system-side
  `libsecril-client.so` are staged under the ignored private payload tree;
- `ims/Android.mk` and `ims/ims.mk` package those inputs, platform-sign the
  shared-UID ePDG app, install the stock privapp grants, and retain the stock
  service contract with controlled `/system_ext` path relocation;
- a dedicated eris SELinux domain is used; Samsung IMS/ePDG may set only the
  service-specific synthetic property `ctl.start$eris`, not generic
  `ctl.start`;
- the device CarrierConfig vendor overlay contains only PLMN data entries for
  46601, 46605, 46692, and 46697, each with WFC availability, opt-in default,
  and the three carrier-scoped `com.sec.epdg` IWLAN service overrides.

The four numeric entries are data, not carrier logic. Carrier names and Samsung
MNO identifiers occur only inside the unmodified stock configuration payload.

## Runtime capture and validation SOP

Use one active 46697 subscription for the first pass. Preserve a clean WWAN
baseline capture before enabling Wi-Fi Calling.

### 1. Baseline and configuration

Capture, per active subscription:

- effective CarrierConfig values for WFC availability, default enabled state,
  all three WLAN service package overrides, WFC mode, and provisioning gates;
- `config_device_wfc_ims_available` and
  `ro.telephony.iwlan_operation_mode`;
- package/service presence for `com.sec.epdg`, and the actual bound WLAN data,
  network, and qualified-networks services;
- IMS registration technology, registered services, and current ePDG state.

Pass conditions: the Wi-Fi Calling preference appears only for carrier ID
1888/46697, starts disabled on a clean state, can be enabled by the user, and
persists across reboot. An unknown/test carrier must remain unavailable.

### 2. ePDG establishment

With cellular service present, connect stable Wi-Fi and enable Wi-Fi Calling.
Capture logcat from before the toggle through registration, including
EpdgService, WfcEpdgManager, Android data/network service binding, Samsung
registration manager, IKE/IPsec, eris, radio channel, and SELinux denials.

Pass conditions:

- `com.sec.epdg` remains alive and all three Android IWLAN services bind;
- eris starts without linker, permission, property, or SELinux failure;
- DNS/IKE/IPsec reaches the TWM ePDG and creates the tunnel/interface;
- Samsung IMS reports ePDG connected;
- IMS registration changes from LTE/RAT 13 to IWLAN/RAT 18;
- the registered service set contains both `mmtel` and `smsip`.

Preference visibility alone is a failure, not a partial VoWiFi pass.

## 2026-09-21 runtime route-ABI finding

The setting bridge is confirmed working on-device: `wifi_call_enable1` becomes
`1`, ePDG reports `SUPPORT_VOWIFI : true`, loads the IWLAN APN and policy, and
eris reaches `ERIS_OK`.  The remaining failure was therefore not the toggle or
the status icon.

When Wi-Fi server selection began, the stock ePDG process repeatedly died with
`NoSuchMethodError` for the Samsung-era
`INetworkManagementService.addLegacyRoute(int, String, String, String, int)`
ABI.  Android 13 netd still provides the matching UID-specific
`networkAddLegacyRoute` and `networkRemoveLegacyRoute` operations, but the
framework Binder facade no longer exposes them.

The selected compatibility fix restores the two old methods at the end of
`INetworkManagementService.aidl` and implements them in
`NetworkManagementService`.  The implementation accepts calls only from
`AID_SYSTEM` and forwards them from `system_server` to netd.  This preserves
the legacy per-UID routing behavior and existing Binder transaction numbering.
It also avoids giving `samsung_ims_app` direct access to the netd Binder
service, which Android 13 SELinux explicitly forbids through a core
`neverallow`.

At this stage, the device-tree `EpdgService.apk` was still the previously
verified setting-sync build (DEX SHA-256
`3931a996483d4e8c474318e549c918fde5a2a016c2329848b851fcb0fac0ba48`);
the abandoned direct-netd APK experiment was not installed into the source
tree.

## 2026-09-21 Android 13 DataProfile CID compatibility

Runtime after the framework route-ABI fix confirms that ePDG DNS resolution
now succeeds and returns four IPv4 addresses.  The next failure occurs when
Android requests the IMS data call over WLAN: `IwlanDataService` receives
`setupDataCall`, but `EpdgHandler` immediately rejects the attach request as
an `invalid cid`.  IMS has already left LTE by this point, which explains the
disappearing VoLTE icon and the absence of a replacement VoWiFi icon.  The
WLAN request eventually ends with `NO_RETRY_FAILURE`, while eris never starts.

The stock adapter derives its ePDG CID from bits 12--15 of
`DataProfile.profileId`.  Android 13 supplies profile ID zero for the current
IMS APN instead of Samsung's old encoded value, producing the invalid CID zero.
The compatibility patch preserves every valid legacy CID in the range 1--8
and falls back to CID 1 only when the derived value is zero or out of range.
This ROM advertises IWLAN only for IMS, so the fallback is intentionally
bounded and does not redirect ordinary mobile-data APNs.

The updated device-tree APK has SHA-256
`bd37096a04285203217b318171327c2fb7daa1cada1e142e2c26a0c8d2f52b96`
and DEX SHA-256
`bbee081474244c566bf0f61cba973373826372a893546e292fa35542616b8582`.

### 3. Calls and teardown

While RAT 18 is stable:

- place one outgoing call and receive one incoming call;
- verify ringing/answer, clear audio in both directions, and normal local and
  remote teardown;
- confirm the IMS and ePDG processes remain alive and registration stays on
  IWLAN after each call.

Record exact timestamps and the active subscription/slot for correlation.

### 4. Hand-back

During idle IWLAN registration, remove Wi-Fi or move out of coverage. Confirm:

- clean ePDG disconnect without process death;
- IMS returns to LTE/RAT 13 with `mmtel` and `smsip`;
- one outgoing and one incoming VoLTE call have two-way audio and clean
  teardown.

If testing removal during a call, classify it separately as inter-RAT handover;
do not turn an idle hand-back pass into an in-call handover claim.

### 5. Regression

After Wi-Fi is off, repeat the established golden checks:

- single-active SIM1 and SIM2 WWAN IMS registration;
- MO and MT VoLTE, two-way audio, and teardown;
- SMS send and receive, including Samsung-to-Android incoming acknowledgement;
- physical SIM1 hot-swap recovery;
- SELinux Enforcing with no new ePDG/IMS denial storm.

Classify every result as confirmed, inferred, or unverified. A build or boot
success does not confirm ePDG, RAT 18, calling, hand-back, or regression safety.

## Status classification

- **Confirmed:** existing device WFC/property gates; all four Taiwan PLMNs pass
  the Samsung mnomap/switch/Wi-Fi-MMTEL/ePDG-APN intersection; exact ePDG
  payload hashes and 32-bit Android 31 ELF identity; carrier-scoped source
  wiring; stock 46697 runtime success; the earlier custom runtime stayed on LTE
  with ePDG disconnected before this candidate.
- **Inferred:** Android 13 should choose AP-assisted mode from the declared
  radio HAL version when no property overrides it; carrier-scoped service
  package overrides are the lowest-risk fail-closed Android binding design.
- **Unverified:** Android 13 runtime compatibility of the stock EpdgService and
  eris libraries; whether additional narrow SELinux or Samsung framework
  permission compatibility is required; entitlement; tunnel establishment
  after integration; IWLAN calls, teardown, hand-back, and all WWAN/SMS
  regression results. Only 46697 has a stock runtime baseline; the other three
  Taiwan entries have static profile evidence only.

## 2026-09-20 runtime finding: AOSP/Samsung WFC setting split

The Enforcing runtime now reaches a stable VoLTE baseline without the earlier
EpdgService crashes. CarrierConfig reports WFC available and Android Settings
successfully writes the active subscription's `wfc_ims_enabled=1`. After an
EpdgService restart, however, Samsung initialization read its separate legacy
`wifi_call_enable` value as `0` and called `setVowifiSetting`, which wrote that
stale zero back to the Android subscription property. The resulting policy
state was `VoWifi(DISABLE)`, so DNS/IKE and eris tunnel establishment did not
begin.

This is a framework-integration mismatch, not evidence of a TWM APN/profile or
carrier allowlist failure. The same run loaded `TWM_TW`, constructed the IWLAN
APN, reported VoWiFi and ePDG support, and exposed both LTE and IWLAN in Mapcon
before the stale setting disabled the path.

The device-tree EpdgService candidate now contains a carrier-neutral bridge:

- `EpdgSubScriptionBase.getVowifiSetting()` first reads the active
  subscription's Android `wfc_ims_enabled` property and falls back to the
  Samsung legacy setting only when the Android value is absent.
- `VoWifiSettingObserver` observes the telephony subscription URI, including
  descendant rows, and routes a subscription-property change through the
  existing ePDG configuration/readiness path. Existing Samsung setting,
  preference, roaming, entitlement, and dual-SIM handling remain intact.
- No operator name, MCC/MNC, Taiwan carrier name, or forced enabled value was
  added. The user-visible per-SIM Android switch remains authoritative.

The candidate was rebuilt from the device tree's then-current APK rather than
the older September 15 work copy, preserving later compatibility fixes. A
ZIP-entry comparison confirms that only `classes.dex` changed. The final APK
decodes successfully with apktool 2.9.3.

- before APK SHA-256:
  `bf6658bd0c4354d5a0d0b05f975b17f4532f043b1dcc9f4cff5237098e1a3d49`
- candidate APK SHA-256:
  `916bf960f4598025ee17e4e46112c5966b56d485b8c8433343658347503eba73`
- candidate DEX SHA-256:
  `3931a996483d4e8c474318e549c918fde5a2a016c2329848b851fcb0fac0ba48`

No Android ROM build was run. The next flashed build must verify that toggling
Wi-Fi Calling causes the observer path to enable ePDG, followed by DNS,
IKE/IPsec, eris startup, IMS registration on IWLAN/RAT 18, a VoWiFi call, and
clean hand-back to LTE.

## 2026-09-21 runtime finding: missing eris configuration

The CID-compatible build reaches `APN_ATTACH_REQ`, resolves the ePDG FQDN,
adds all four ePDG routes, and enters `IPSecAdapterForEris.connect()` with CID
1. It then reports `IPSecService is not connected yet` for every address and
returns `ERIS_GENERIC_FAILED`. The corresponding init service remains stopped,
so IMS has already handed registration away from LTE without gaining an IWLAN
tunnel; this accounts for both status icons disappearing.

A controlled root start proves that init can find and execute the daemon. The
daemon immediately exits with `abort initialization due to invalid
configuration`. `liberis_strongswan.so` hard-codes `/system/etc/eris.conf`, but
that file is absent from the current ROM and was not present in the device-tree
package list.

The exact 287-byte file was extracted from the SM-M115F CWK3 stock system
image and restored as `ims/proprietary/etc/eris.conf`. Its SHA-256 is
`9371e5869f78d809013107b5d3a8bd40100a0f2834994ff77122c6aac3780628`.
`m11q_eris_conf` installs it at `/system/etc/eris.conf`, is included in the
product package list, and is also an explicit required module of EpdgService.
No operator-specific value or permissive SELinux rule was added.

No Android ROM build was run. On the next build, verify the generated target
files contain `SYSTEM/etc/eris.conf`; after flashing, first confirm eris stays
running and the local socket connects, then continue with IKE/IPsec and RAT 18
registration testing.

## 2026-09-21 EAP-AKA and TUN socket SELinux closure

With the stock configuration restored, eris stays running and reaches the
carrier ePDG. Under Enforcing, the ePDG sends an EAP-AKA challenge, but
`multiclientd` is denied `search` on the ERIS peer's `/proc/<pid>` directory.
The daemon consequently logs `can't connect with oem client`; ERIS reports
`get_quintuplet() FAILED: AUTH fail`, sends `AKA_AUTHENTICATION_REJECT`, and
receives `AUTHENTICATION_FAILED` from the ePDG.

A short, explicitly authorized Permissive capture confirms that removing this
denial advances the path past the earlier AKA failure. It then exposes the
next exact denials: ERIS needs `relabelfrom` on a TUN socket received with the
`rild` label, and on an already ERIS-labelled TUN socket during retries. The
phone was returned to Enforcing immediately after the capture.

The source policy now grants only the observed peer-validation and TUN
relabel operations:

- `m11q_multiclient` may search the dedicated `m11q_eris` proc directory and
  open/read/getattr its cmdline file, mirroring its existing narrow rule for
  `samsung_ims_app` peers;
- `m11q_eris` may relabel a TUN socket from the public
  `hal_telephony_server` attribute (the vendor `rild` member observed at
  runtime) or from `m11q_eris`; its existing self-domain `relabelto` rule
  remains unchanged. Platform policy intentionally does not reference the
  vendor-only concrete `rild` type.

The user also observed that toggling Wi-Fi Calling off and on did not restore
the icon after authentication failures, while toggling Wi-Fi did. The capture
shows repeated Android IWLAN setup retries remaining in Samsung's throttle
state after the IKE authentication error. This is not yet classified as an
independent observer defect: a Wi-Fi network transition resets the failed
ePDG attempt, whereas the user setting change retains the failure/throttle
state. Re-test this behavior only after the SELinux-authentication path is
closed; do not add an unconditional throttle bypass yet.

## 2026-09-21 ERIS OEM-client identity path correction

The first Enforcing retest after the proc/TUN policy update still reached the
carrier EAP-AKA challenge but failed locally before sending a SIM response:

- ERIS logged `onError: error 4` and
  `rossoneri get_quintuplet() FAILED: AUTH fail`;
- no SIM authentication request reached RIL through `multiclientd`;
- no ERIS, multiclient, RIL, or TUN SELinux denial was present;
- a short authorized Permissive comparison exposed no relevant additional
  denial, and the device was returned to Enforcing immediately.

Static inspection then identified the missing native contract. The stock
`multiclientd` binary validates each OEM client's `/proc/<pid>/cmdline` and
contains exact allowlist strings for `/system/bin/vpnclientd` and
`/system/bin/eris`. The compatibility tree had deliberately relocated ERIS to
`/system_ext/bin/eris`. Once proc access was allowed, multiclientd could read
that command line but rejected it because it did not equal the compiled stock
path. `libsecril-client.so` consequently returned error 4 before forwarding
the EAP-AKA request to the modem.

The source now restores only the ERIS executable to its stock identity:

- `m11q_eris` installs in `/system/bin` rather than `/system_ext/bin`;
- `eris.rc` launches `/system/bin/eris`;
- file contexts label `/system/bin/eris` as `m11q_eris_exec`.

The private ERIS compatibility libraries remain in `system_ext/lib`. Android
13's generated system linker configuration includes
`/system/system_ext/${LIB}` in the default system namespace search path, so
the executable relocation does not require moving or globally exposing those
libraries. No carrier profile, IMSI/NAI construction, retry policy, or new
SELinux permission was changed. No ROM build was run.

On the next flashed build, confirm `/system/bin/eris` is the running process
command line. A successful fix should add a `multiclientd` OEM request and a
modem SIM-authentication response between the EAP-AKA challenge and ERIS's
AKA response; only after that result should the independent WFC-toggle
throttle-state behavior be reconsidered.

## 2026-09-22 Samsung ePDG traffic-control ABI closure

After restoring ERIS's stock executable identity, EpdgService reached its
startup recovery path and crashed on another missing Samsung framework ABI:

`INetworkManagementService.disableEpdg(String, String)`

This cannot safely be fixed with an empty compatibility method. The same APK
also calls `enableEpdg(String, String, boolean)` during live tunnel setup, and
the stock implementation is responsible for the packet path used by the IMS
PDN. Reverse engineering the CWK3 stock Android 12 `netd` mini-debug symbols
and `OemNetdListener::modifyEpdg` implementation recovered the exact design:

- a `prio` root qdisc on the cellular interface;
- an egress `basic`/`mirred` redirect from the cellular interface to the ePDG
  tunnel interface;
- an ingress qdisc on the ePDG tunnel interface;
- an ingress `basic`/`mirred` redirect back to the cellular interface;
- idempotent qdisc cleanup for disable and stale-CID recovery.

The Android 13 source now restores the contract end to end rather than
patching the APK call sites:

- `INetworkManagementService` exposes the two Samsung-compatible methods at
  the end of the AIDL so existing transaction ordering is preserved;
- `NetworkManagementService` restricts access to AID_SYSTEM and delegates to
  the existing unstable OEM netd Binder extension;
- `IOemNetd` adds `modifyEpdg`, and `OemNetdListener` applies the recovered
  rules through `/system/bin/tc` using argument-vector execution (no shell);
- interface names are length/character validated, live setup requires both
  interfaces to exist, rule updates are serialized, and failed partial setup
  is rolled back;
- teardown is intentionally best-effort so `recoveryCheck()` can clean stale
  persisted CIDs without crashing when their interfaces are already gone.

The current product output contains a full `tc` binary with `basic` and
`mirred` actions, and the kernel configuration enables `NET_SCH_PRIO`,
`NET_SCH_INGRESS`, `NET_CLS_BASIC`, and `NET_ACT_MIRRED`. Existing platform
policy already grants netd execution of system binaries and `NET_ADMIN`; no
new permissive or device SELinux rule was added.

No Android ROM build was run. The next build should first be checked for an
`OemNetd: modifyEpdg enable=...` line and absence of `NoSuchMethodError`.
During a live IWLAN attach, `tc qdisc show dev <rmnet>` and
`tc qdisc show dev <epdg>` should expose the prio and ingress qdiscs before a
VoWiFi call is attempted.
