# SystemUI registration-constant import correction — 2026-10-10

The user's user-variant build failed in `MobileSignalController.java` because
the icon patch imported `android.telephony.ims.ImsRegistrationImplBase`.
Android 13's actual class is
`android.telephony.ims.stub.ImsRegistrationImplBase`; the missing `.stub`
caused the two invalid static imports and the four dependent compiler errors.
This failure is unrelated to the nonfatal vendor property-prefix warnings.

The correction changes only the owner of the two imported registration
constants. It retains the existing icon registration-state handling and does
not alter IMS handover, audio routing, carrier policy or the radio behavior.

The live WSL source and the current
[complete icon patch](../platform/systemui/wfc-registration-icon.patch) are
corrected. The published `platform/checkpoints/ims-20261010` files and their
manifest hashes remain historical and unchanged. A fresh checkout replaying
that checkpoint must also apply
[the import-only follow-up patch](../platform/systemui/0001-fix-ims-registration-constant-import-package.patch).
Do not apply the full icon patch a second time after replaying the checkpoint.
The current WSL source already has the correction and needs neither replay.

The previous host callback test extracted Java method bodies and supplied fake
constant declarations. It tested state transitions but could not detect the
incorrect Android package import. The regression tests now check the actual
namespace and provide a small Java import compilation check against existing
Android 13 API artifacts via `M11_SYSTEMUI_API_CLASSPATH`. This is not a full
SystemUI or Android ROM build.

Validation: 9 focused tests passed, including real `javac` compilation of the
source's actual imports against the existing Android 13
`android-non-updatable.stubs.system` API jar. The historical icon checkpoint
plus the import-only follow-up patch reproduced the corrected live source
byte-for-byte; the old checkpoint manifest hash still matches.

Corrected `MobileSignalController.java` SHA-256:
`16e315151e4b534da1938fd04b05b3eeb16b2ac39764fccace24d38715968f1a`.

## Publication and user acceptance

The WSL `frameworks/base` correction is committed as
`2521273c19652476c4ee7392c4c4607ff6949c84`, directly after historical checkpoint
HEAD `ccfc0c8da6c4f64300ca27f0b78e263167f8e38b`. That repository's working tree
is clean. Its source correction is published through this compatibility repo's
current complete icon patch and import-only follow-up patch; no push to
crDroid upstream or new fork is implied.

On 2026-10-10, the user reported testing the updated version and confirmed that
the icon now behaves correctly, then authorized commit and push. This records
user-reported icon acceptance, not a new full IMS call-test batch. The agent
performed only non-ROM-build validation.
