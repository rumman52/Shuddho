# TX-04: Immutable local mutation qualification records (21 October 2026)

## Defect and bounded scope
- Base: `3f41a085eb465c875085e72a25c0b29e3f343b81`.
- The in-memory `TransactionMutationGuard` returned a mutable `MutationRecord`, allowing callers to rewrite reserved execution identities, providers, attempts, and attached receipt hashes.
- `attach_receipt` silently replaced an existing receipt hash with a conflicting value, rather than detecting inconsistent provider evidence.
- This guard is an **in-memory qualification helper**, not the persistent production `ExternalAction` ledger. Do not treat this source repair as TX-04 production qualification.

## Corrective change
- Make returned records frozen and update attached receipt via an atomic copy inside the existing lock.
- Permit exact same-receipt idempotent replay; reject conflicting receipt with `ValueError("receipt_conflict: ...")`.
- Reject empty/non-string first receipt hashes; return thread-safe immutable snapshots from `get`.
- Preserve duplicate-mutation rejection, execution identity, provider, attempt count and original method signatures.
- No action dispatch, claim/lease, provider calls, authorization, migrations, settings, flags or deployment changes.

## Verification evidence and limitations
- Test-first local reproduction on unchanged source: **2 failed, 3 passed** (conflicting receipt overwrite, externally mutable returned record).
- Local corrected focused suite: `python -m pytest tests/test_transaction_mutation_guard.py -q` => **5 passed**, zero failures; source `compileall` succeeded. This is isolated local coverage, not the full Shuddho repository suite.
- Additional concurrency case proves 60 competing reservations yield exactly one accepted mutation.
- Exact-head CI (including mandatory coworker tests) and independent human review are required before merge.
- TX-05 reconciliation still requires provider-bound observed evidence and protected staging. V-01 native ruleset may exist but must be independently validated with blocked/unreviewed and successful reviewed PR controls.
