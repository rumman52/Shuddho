# TX-05 — Confirmed receipt finality (21 October 2026)

## Defect
After a first successful reconciliation, a changed receipt persisted on an ExternalAction can produce a new evidence digest and be appended as a second successful observation. A completed provider result must not be overwritten by mutated durable action metadata.

## Bounded fix
- Keep exact-evidence replay idempotent.
- Before appending a new successful observation, fail closed if an earlier succeeded observation exists for the same owner, transaction, and ExternalAction.
- Add a regression using the real transaction test fixture: persist success, mutate stored ExternalAction receipt, sync again, expect transaction_evidence_integrity_failed (409), one original evidence row, unchanged confirmed state.
- Preserve the valid outcome_unknown -> first succeeded transition, approval/claim/lease/owner gates, and all existing execution behavior.

## Evidence limits
- Based on main 3f41a085eb465c875085e72a25c0b29e3f343b81.
- No local full integration run: Temporal and database dependencies are not available in the isolated shell. A Python syntax check of the added guard snippet passed, but this is not an integration test.
- Required exact-head test-and-build, coworker and ci-merge-gate, independent review, and operated staging evidence remain pending.
- No provider call, activation, schema, credential, production deployment or permission change. V-01 native protection may not be bypassed.
