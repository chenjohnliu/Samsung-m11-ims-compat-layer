# Bridge source provenance record

This is a technical provenance record, not legal advice. These files were
created as project-specific Codex output for this compatibility project. Under
the OpenAI terms applicable to the output, rights held by OpenAI in that output
are assigned to the user. The project nevertheless performed the technical
third-party-source audit below before publication.

## Exact reviewed source inventory

| File | SHA-256 | Technical classification |
| --- | --- | --- |
| `GoogleModernImsService.java` | `29d2f10d0c42f889f15ecaa9ef31b0200b12e6d9cdb30fc3217147add7b9e152` | Project-specific Android 13 service adapter |
| `GoogleModernMmTelFeature.java` | `4a8831307b335f29e2dda0d0853a5ba07f329cb6f6d33af5cf6844b175f25390` | Project-specific MmTel adapter |
| `ModernCallRelay.java` | `3f9a0e478346ae2a77e74bc0da4a65312cae82de76119d8923440a28fd152a2f` | Generated from AOSP Binder declarations plus a project-authored relay template |
| `ModernCallSession.java` | `1720e929f4e1154142730146b9a844528918ebc6b56b7ee01dd459e1bf38a410` | Generated from AOSP Binder declarations plus a project-authored delegation template |
| `ModernEventQueue.java` | `7fec02e56ed5997a7f52341f3687e265b68aa4c705e4aff79844a6ae1e1e8339` | Project-authored queue state machine |
| `ModernSmsBridge.java` | `fb50305bc9501552c8d8e6f5ba158fbe05ced16788feb5ac87a8d481f463d44b` | Project-specific SMS adapter |
| `ModernVoiceContext.java` | `1ab736a98b45942f8fde89627a0567e2540f11db4690724d761deda3edb1d1c1` | Project-specific voice and registration state machine |

## Technical audit result

- No JADX, CFR, Fernflower, `Method not decompiled`, renamed-symbol, synthetic,
  or similar decompiler markers were found.
- No Samsung method implementation body was identified in the seven files.
- Calls to Samsung private class and method signatures are compatibility
  boundaries; the Samsung implementations remain in user-supplied stock code.
- `ModernCallRelay.java` and `ModernCallSession.java` are mechanically generated
  from declaration-only Android 13 Binder ABI data plus project templates.
- The other five files contain project-specific SIM1, ownership, queue,
  registration, call, SMS, and hot-swap policies consistent with the design and
  runtime history documented in this repository.
- The reviewed relay is the pre-BQ7 version. The excluded BQ7 source has a
  different hash and is not part of this inventory.

The source is published under the repository's Apache-2.0 licence. Samsung
firmware, binaries, decoded trees, method implementations, and other proprietary
inputs remain excluded. Code-generation output can still be subject to
third-party licences; the exact-hash inventory, AOSP ABI attribution, and
no-implementation-copy audit are retained for that reason.
