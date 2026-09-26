# Emergency-calling architecture audit

Status: source-audited on 2026-09-26; no emergency call was placed.

> **Release warning:** Emergency calling is not validated; do not rely on this
> ROM for emergency communications.

## Scope and safety boundary

This audit separates emergency-number recognition, Android call routing,
Samsung IMS emergency registration, radio/modem fallback and Samsung Emergency
Mode compatibility. It does not claim end-to-end emergency-call support.

Never validate this work by calling a public emergency number. End-to-end
validation requires an operator or accredited lab that can provide a designated
test number, controlled network conditions and explicit authorization. The
read-only capture below does not originate a call and cannot prove completion.

## Root cause and source correction

The Android 13 `frameworks/opt/net/ims` source updated its cached emergency IMS
capability using a bitwise OR:

```java
(capabilities | ImsService.CAPABILITY_EMERGENCY_OVER_MMTEL) > 0
```

Because `CAPABILITY_EMERGENCY_OVER_MMTEL` is nonzero, that expression reports
emergency MMTEL support even when the service did not advertise it. The m11q
bridge intentionally advertises ordinary MMTEL only. If normal IMS voice is
available, the false capability can therefore send an emergency request toward
the bridge, whose call-profile and voice paths accept normal service only.

The local source correction uses a bitwise AND and adds a regression test that
checks zero capabilities, an unrelated SIP-delegate capability and the actual
emergency bit. This preserves the existing design: emergency IMS is not
advertised, so Android can select its radio fallback instead of treating the
normal Samsung IMS bridge as an emergency-capable service.

The source patch is
`patches/frameworks-opt-net-ims/0001-fix-emergency-capability-mask.patch`.
It applies to the `frameworks/opt/net/ims` repository root. Source formatting
and reverse-application checks pass. The agent did not invoke a ROM build; the
post-fix evidence below comes from the user's subsequent manual build and flash.

## Post-fix read-only runtime evidence

A no-dial capture was collected on 2026-09-26 after the user built and flashed
the corrected source. All recorded capture hashes verified. The installed
`/system/framework/ims-common.jar` SHA-256 matched the freshly built product
artifact, and the corresponding build bytecode uses `land` for
`onFeatureCapabilitiesUpdated(long)`. This confirms that the installed jar
contains the AND-mask correction rather than the old OR expression.

The captured state had one loaded TWM SIM, the other slot absent, LTE service
and ordinary IMS voice registered over IWLAN. Android reported ordinary voice
capability with VoWiFi enabled. At the same time:

- the IMS service's cached and active feature sets contained only MMTEL for
  slots 0 and 1, with no advertised emergency MMTEL feature;
- its static service-capability set was empty, so emergency-over-MMTEL was not
  advertised through that separate capability channel either;
- the resolver's device mapping still named the IMS package for
  `EMERGENCY_MMTEL`, but neither the cached service features nor active
  controller instantiated that feature. A configured package mapping is not a
  published feature;
- Android created and supplied the default `sos`/EIMS data profile and retained
  its retry rule, but there was no EIMS network request or EIMS data setup;
- the qualified access network for emergency data was EUTRAN, not IWLAN;
- the emergency-number tracker was populated, while the outgoing emergency
  call and SMS fields remained null; and
- no emergency dial, emergency call setup, IMS emergency processing or related
  exception appeared in the capture.

This confirms deployment of the source correction and the intended runtime
feature-advertisement boundary while normal VoWiFi is active. It does not
observe an actual routing decision because no call was initiated, and it does
not validate emergency-call completion.

## Evidence classification

| Area | Classification | Evidence and limit |
| --- | --- | --- |
| Bridge feature declaration | Confirmed | The public manifest contract and decoded current APK expose MMTEL, not `EMERGENCY_MMTEL_FEATURE`. |
| Bridge emergency call implementation | Confirmed absent | `querySupportedImsFeatures`, call-profile creation, voice dispatch and registration gates do not implement Samsung emergency profiles. |
| Framework capability test | Confirmed defect | OR makes the cached flag true for an absent bit; AND is the required mask test. |
| Radio emergency ABI | Confirmed available | The device declares HIDL IRadio 1.4; Android's RIL uses `emergencyDial` for emergency calls when the 1.4 path and emergency-number metadata are available. |
| Emergency-number recognition | Confirmed in captured state | The custom-ROM bugreport contains radio/database/fallback emergency-number lists. Recognition alone does not prove routing or connection. |
| EIMS data profile | Confirmed in captured state | Android created default `sos`/EIMS profiles and retry policy; the captured profiles had never been set up. |
| CS/radio fallback after this fix | Inferred | With no emergency IMS feature, framework selection should return to the radio emergency path. A post-build, no-dial trace is still required to confirm selection state. |
| Stock Samsung IMS emergency design | Confirmed statically | The pinned stock profile data contains a separate TWM emergency profile using the emergency PDN over LTE/NR/Wi-Fi. This is not runtime proof. |
| Stock TWM VoWiFi emergency transport | Unverified | The stock ePDG APN file has a TWM ordinary `imsApn` entry but no observed TWM-specific `emergencyApn` entry. The profile alone does not establish working emergency VoWiFi. |
| SIM-present emergency completion | Unverified | No authorized lab call was performed. |
| SIM-absent emergency completion | Unverified | Android has fallback emergency numbers and the bridge cannot form its normal single-active-subscription pair, but actual modem/network behavior is untested. |
| Limited-service/other-network completion | Unverified | Stock logs show emergency-only service states, not a completed call. |

## Important non-causes and boundaries

`SemEmergencyManager` is a narrow compatibility surface for Samsung Emergency
Mode/UPSM checks used during IMS startup. Its conservative `checkModeType()`
result is not an implementation of emergency calling, and current evidence does
not show that it blocks emergency call routing.

The validated Stage 3 TWM VoWiFi calls were ordinary calls. They do not validate
emergency registration, an emergency PDN, Wi-Fi emergency routing, location
delivery or fallback.

Implementing IMS emergency calling in the bridge is not a safe incremental
change. It would require explicit emergency feature publication, emergency-only
feature lifecycle, Samsung emergency-profile selection and registration,
emergency service/call-session support, EIMS acquisition, SIM-absent handling,
fallback semantics and controlled lab validation. None of those behaviors is
claimed here.

## Safe validation matrix

After the user builds, flashes and reboots a ROM containing the framework fix,
collect one consolidated read-only snapshot in each naturally available state:

| State | Safe observation | What it resolves |
| --- | --- | --- |
| SIM present, normal service | IMS feature/capability dumps, carrier config, emergency-number list, radio/IMS logs | Confirms ordinary MMTEL remains registered while emergency MMTEL remains unadvertised. |
| SIM absent | The same snapshot, without initiating a call | Confirms available fallback numbers and that no emergency IMS feature is fabricated without an active subscription. |
| Limited/emergency-only service, if it occurs naturally | The same snapshot, without forcing network state | Confirms registration and available-services reporting; it still does not prove call completion. |
| Wi-Fi calling registered | The same snapshot | Confirms normal Wi-Fi IMS does not accidentally imply emergency-over-Wi-Fi capability. |

Run the workspace helper from PowerShell:

```powershell
.\tools\collect_emergency_readonly.ps1
```

The helper performs only reads: selected properties, service dumps and existing
logs. It does not clear logs, change settings, toggle radios, restart services,
use emergency-number test mode or dial any number. Captures are private because
they may contain subscriber, phone-number, network and location-related data.

Expected decision after the capture:

- if emergency MMTEL remains false while ordinary MMTEL works, the routing fix
  has reached runtime and the remaining completion claim stays lab-only;
- if emergency MMTEL is still true, inspect the runtime service-capability mask
  and installed build identity before making further source changes;
- if ordinary IMS regresses, treat that as a framework integration regression,
  not evidence that emergency IMS should be enabled.

## Release gate

Source review and no-dial captures can verify feature advertisement, recognized
numbers, carrier policy and selected framework state. They cannot verify call
setup, media, location, callback, roaming, SIM-absent completion or public-safety
network behavior. Keep the release warning until an authorized lab validates
the complete matrix on the exact build, device, SIM/carrier and regulatory
environment.
