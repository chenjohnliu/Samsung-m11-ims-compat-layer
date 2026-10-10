# IMS single-active-SIM support in either physical slot

Requested scope: one active SIM in SIM1 (phoneId 0) or SIM2 (phoneId 1),
not dual-active-SIM support. This supersedes the prior slot-0-only scope.
[User test checklist](SIM1_SIM2_IMS_TEST_CHECKLIST_20261009.md).

## Implementation

Telecom derives phoneId/subId from the foreground call's phone account and
requires the exact sole active subscription to agree. The slot is not selected
from default data/default voice preference. Operator-property sanity checks
accept either single occupied position, never two occupied operators.
The call/phone/subscription tuple is stamped into each transition plan;
same-call subscription changes or slot changes invalidate prior work and LTE
source evidence. Each audio step rechecks the live subscription mapping.

All Samsung IMS queries and audio selections use the plan's phoneId:
`getRegistrationInfoByPhoneId`, `getCallCount`, `changeAudioPathForSlot`.
The selected phone must have exact ordinary counts [1,0,0,0], the other phone
[0,0,0,0]. A normal mmtel registration must belong to that selected phone.

W2L selects stock `g_call_sim_slot=0x01` for phone 0 and `0x02` for phone 1.
These are confirmed in the privately inspected CWK3
`SamsungCallMultiSimAudioParam.setSim1/setSim2` implementations, not inferred
from a guessed bitmask. STOP/mode/SAE/INFORM and CPVE ordering is unchanged.
Initial IWLAN calls retain their existing path; the adapter does not invent LTE
source evidence. The existing IMS bridge and LG3 WFC setting lookup already
use the active slot/subscription, and BT1 incoming media uses registration handle.

SEH permits one callback owner per valid phone, bound to vendor instances slot1
or slot2. Callback data still requires exactly one active subscription and the
matching phone/subscription/operator; inactive, dual-active and stale identities
return empty/error without querying the other SIM. Provider lookup and immutable
fallback snapshots remain tied to the same subscription and phone. No changes
to HIDL wire ABI, permissions, modem firmware, APN contents or CID allocation.

## Source, tooling and validation

Applied to live WSL Telecom and frameworks/opt/telephony source. Device
system.prop changes only its SEH scope comment; the product flag stays true.
The integrated SA2 has no runtime opt-in property. Timer F remains restored to
CWK3 128 seconds; global profile-backed WFC eligibility and Wi-Fi deferral are
unchanged.

SA2's verified refresh now regenerates the managed observer/hook files as well
as helpers from the original pinned baseline. This avoids upgrading helpers
while leaving a slot-0-only caller. Original rollback is retained, with previous
files in `D:/m11q/work/sa2-either-slot-revision-20261009`.
SEH refresh retains its original rollback and upgrades pinned assets plus scope
metadata; prior state is backed up at `D:/m11q/work/seh1-either-slot-revision-20261009`.

Product checks require the either-slot audio revision and both stock SIM
parameter strings; SEH checks defined `supportedPhone` and `isEnabledForPhone`
methods, not string hits. An old slot-0-only product cannot pass the new gates.

Non-build tests: 80 SA2 transition/tuple/registration/count/routing assertions,
13 SEH policy/transport and 11 bridge harness groups, including SIM2 service
selection, provider precedence, per-slot snapshots, stale queries, relocation
and dual-active rejection. Live Telecom observer/adapter and all SEH helper
classes compile standalone against existing Android 13 APIs. Python source,
rollback and packaged-ABI tests also run. No Android ROM build, APK installation,
flash, live SIM change or call is performed by the agent. SIM2 audio on this
modem remains unverified until the user's test.

The reproducible host/API check (not an Android build) is:

```sh
python3 tools/check_ims_slot_support.py \
  --android-root /home/user/android/crdroid \
  --java-home /home/user/android/crdroid/prebuilts/jdk/jdk11/linux-x86 \
  --output /mnt/d/m11q/work/ims-slot-check-new
```

Use a fresh output path. Follow the checklist's three product gates after the
user's manual ROM build, then test the same SIM in both slots.
