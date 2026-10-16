# CW-11 staging collector task-ledger and evidence-boundary hardening

Date: 17 October 2026 (Asia/Dhaka)

## Problem

The staging evidence collector duplicated a narrower task count that only caught active pre-fence reviewed Tasks with an existing identity Step. It could miss:
- an active reviewed-workflow Task whose immutable reviewed identity is missing;
- ambiguous active legacy Agent-owned research that lacks a reviewed identity Step.

The Render evidence validator was called only by the CLI entry point. A direct caller of `collect_evidence()` could skip validation and potentially obtain a `verified: true` artifact from malformed or revision-mismatched external evidence.

The same second-pass review found that the collector could ignore a lost worker on an undeclared revision, or a stale active worker when another candidate worker was fresh, despite the rollout contract requiring stale/lost workers to remain uncertainty blockers.

## Required behavior

1. Use the canonical read-only `inspect_reviewed_rollback()` classifier.
2. Refuse to emit evidence when any task-ledger blocker is present.
3. Include only aggregate, non-authorizing ledger counts in a successful artifact.
4. Validate external Render evidence inside `collect_evidence()` before database-backed selection or inventory reads.
5. Reject non-object payloads, missing or unexpected fields, non-integer schema versions/counts, a non-true verified marker, blank/equal service IDs, malformed full commit SHAs, a legacy instance count other than exactly zero, a candidate count below one, and either revision mismatch.
6. Treat lost, unknown-state and stale-heartbeat active worker records as blockers even when a fresh candidate worker is also present.
7. Keep the feature default-off and do not deploy, select, publish, rollback, migrate, drain or activate anything from this collector change.

## Implementation

- Reuse `scripts/reviewed_skill_rollback_preflight.py:inspect_reviewed_rollback`.
- Keep the existing summary field for compatibility while adding the complete aggregate task-ledger classification to the evidence artifact.
- Add regression tests for the newly covered ledger states and the collector-call boundary.
- Update `docs/CW11_TRUSTED_SKILL_ROLLOUT.md` and the canonical progress record.

## Acceptance

- Clean synthetic release: collector returns a verified artifact with `TASK_LEDGER_CHECK_ONLY`, an empty blocker list and `rollout_authorized: false`.
- Active legacy Agent research without identity: collector raises a typed `CoworkerError` and emits no verified artifact.
- Active reviewed-workflow Task without identity: same fail-closed result.
- Malformed, unverified, wrong-type, extra-field or revision-mismatched Render payload: rejected before database-backed publication selection.
- Lost, unknown-state or stale-heartbeat active worker record: collector blocks, even when its revision differs from the declared legacy revision or a fresh candidate worker is present.
- Exact final-head `test-and-build`, mandatory no-skip `coworker`, and `ci-merge-gate` all pass.
- Staging remains a separate protected operated gate. A green CI result does not prove worker drain, no in-flight external work, or production qualification.

## Evidence and limits

This is a repository-code/contract slice. It does not establish live Render state, PostgreSQL/Temporal drain, staging replay, security certification, production qualification or activation.
