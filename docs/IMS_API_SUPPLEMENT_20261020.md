# IMS API compatibility supplement — 2026-10-20

This supplement adds the Jio PANI crash fix and a separate group of preventive
framework compatibility changes. The [Jio case](cases/JIO_M115F.md) records the
maintainer-relayed VoLTE and VoWiFi success. Only the original
`semGetDataServiceState` change was in that tested Cherish artifact. The later
preventive changes and their crDroid port have no new ROM-build/device receipt.

## Changes

| Patch | Behavior | Validation scope |
| --- | --- | --- |
| `data-service-state.patch` | Adds both hidden `TelephonyManager.semGetDataServiceState` overloads, returning the requested subscription's real data registration state; missing state is out-of-service | Cherish host/replay checks, completed OTA identity, tester-reported Jio VoLTE/VoWiFi success; crDroid source/host checks only |
| `ims-api-prevention.patch` | Adds call-state, ISIM IMPU and explicit-subscription data-state adapters, plus the client/AIDL side of UICC-application IMSI lookup | Source/host and standalone AIDL checks; not newly device-tested |
| `uicc-app-imsi.patch` | Adds the subscriber-info service implementation selecting the requested subscription and UICC application, preserving package and subscriber-identifier permission checks | Source/host checks and unchanged existing Binder transaction IDs; not newly device-tested |
| `sem-capabilities-factory.patch` | Corrects `SemCapabilities.getBuilder()` to a static factory returning a fresh builder | Actual-source host compilation/factory checks; not newly device-tested |

The UICC client/AIDL and service patches are a pair across `frameworks/base`
and `frameworks/opt/telephony`. Apply them in the same source integration batch.
Appending an AIDL declaration alone leaves the service implementation incomplete.
The original Jio data-service-state fix does not require this preventive pair.

## Source routes and application order

The machine-readable [supplement manifest](../platform/checkpoints/ims-api-20261020/manifest.json)
records each ROM's prerequisite tree, ordered patch hashes and result trees,
plus the Cherish source-fork commits. The canonical [Cherish source index](../devices/m11q/cherish-source-index.json)
and [crDroid source index](../devices/m11q/crdroid-source-index.json) include the
new suffixes. Older checkpoint manifests and hashes remain historical records.

Choose one source route for each project:

1. For a synchronized Cherish project, use the exact updated source-fork commit recorded in the index/manifest. It
   already contains its prerequisites and the new suffix; do not apply those
   patches again.
2. Or start from the indexed upstream base and apply that project's complete
   ordered patch list once. For existing integrations, identify the current
   tree before applying only a suffix. Preserve unrelated local changes.

For the new suffix, `frameworks/base` receives data-service-state, preventive
APIs, then the factory fix; `frameworks/opt/telephony` receives the UICC service
implementation. The ROM-specific copies are under:

```text
platform/checkpoints/ims-api-20261020/cherish/
platform/checkpoints/ims-api-20261020/crdroid/
```

Use the manifest's hashes and full tree IDs rather than patch filenames alone.
The updated source forks are in the existing maintainer repositories:

- [Framework base](https://github.com/chenjohnliu/android_frameworks_base)
- [Telephony framework](https://github.com/chenjohnliu/android_frameworks_opt_telephony)

Cherish uses `cherish-13-m11q-ims`. The crDroid port is published as its pinned
upstream-base patch recipe, without a new maintainer full-source branch.
Exact commit and tree pins identify the reviewed source contents.

Published Cherish commits:

- [Jio data-service-state fix](https://github.com/chenjohnliu/android_frameworks_base/commit/771ea14b0044d5c60546941cee948c74bc3c39aa)
- [Preventive framework adapters and UICC client](https://github.com/chenjohnliu/android_frameworks_base/commit/93755bf0cd4cb6e94c1af5aa26cd0e32f9203283)
- [Static capabilities builder factory](https://github.com/chenjohnliu/android_frameworks_base/commit/24d00aa0f58abb78dcb6e155b3fe4507aad568e7)
- [UICC application IMSI service](https://github.com/chenjohnliu/android_frameworks_opt_telephony/commit/dc925e6f794415b5490beb13dcef3a67342cec3d)

`TelephonyManager.java` is AOSP source under Apache License 2.0. These patches
add authored compatibility adapters to that source; the Samsung-style method
names do not make the AOSP file proprietary. No decompiled stock implementation
or stock binary payload is included in this supplement.

## Validation and release boundary

Patch replay verifies before/after trees and reverse recovery. Actual-source
host harnesses check subscription forwarding, real-state/failure behavior,
modeled UICC selection and permission ordering, and independent fresh builders.
Standalone AIDL generation checks that all 34 pre-existing subscriber-info
transaction IDs remain unchanged and the new method is appended at offset 34.
Modeled helpers do not test real Binder, framework permissions, modem or network
behavior. No Android ROM build was run by the agent for this supplement.

Run the portable actual-source host harness from this compatibility checkout:

```sh
python3 tests/java/ims_api_20261020/run_tests.py \
  --source-root /path/to/android/source \
  --java-home /path/to/jdk17
```

Both updated local source trees passed 35 Telephony assertions and 6 builder
assertions. The harness emits source hashes and uses temporary Java/classes;
see its [scope and limits](../tests/java/ims_api_20261020/README.md).

Before distributing a build containing the preventive changes, build manually
and validate IMS stability, registration, outgoing/incoming calls and SMS, and
Wi-Fi Calling if provisioned. Record the actual artifact and tested SIM/slot;
add a network transition only when relevant. Do not mark the prevention group
as Jio-tested because the earlier original-fix build passed.

Further conditional gaps remain in CDMA/non-3GPP SMS callbacks, CMC, selected
Samsung UI/SVE paths and other vendor APIs. A static missing-symbol list is a
triage list, not a count of demonstrated runtime failures. See the
[human debugging runbook](IMS_DEBUGGING.md) for evidence collection and decisions.
The port does not change stock payloads, carrier profiles or CSC selection.
