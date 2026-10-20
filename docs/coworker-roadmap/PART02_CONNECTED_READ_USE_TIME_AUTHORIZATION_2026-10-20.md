# Part 02 — Connected-read use-time authorization and atomic payload access

**Date:** 20 October 2026 (Asia/Dhaka)  
**Status:** Source fix merged in PR #498; PostgreSQL concurrency follow-up pending exact-head CI and independent review  
**Scope:** A-01 trust boundaries, A-04 current permission enforcement, P-02 revocation

## Objective

Keep connected-read authorization current through the database operation that consumes it. A permission check in a prior transaction is not sufficient when revocation, scope removal or expiry can occur before private payload retrieval or sync persistence.

## Baseline

- Repository: `rumman52/Shuddho`
- Base `main` SHA: `ae4208e2b82c8120c72dd37707c91c2ba12e6697` (PR #497 merge).
- Existing Part 01 closes the grant-admission gap by rechecking connection state and scopes before a new grant is persisted.
- Current-main checks at implementation start: `test-and-build` passed; mandatory `coworker` remained in progress. This is not a green full-gate result.
- No migration, endpoint, policy version, capability default, production configuration or deployment change.

## Root cause

Three repository paths had gaps between authority validation and use:

1. `ConnectorReadRepository.snapshots` validated the grant in a separate transaction and fetched private snapshot payloads after that transaction released the connection/grant locks. A revoke or scope change could commit between validation and payload retrieval.
2. `apply_sync` checked grant state and expiry but did not revalidate the current connection, registered capability contract and required OAuth scopes after the provider response and before persisting returned data.
3. `reset_cursor` mutated cursor state without validating that the read grant was still active.

The public `cursor` read also validated separately from fetching the cursor.

## Implementation

- Added `PermissionGateway.validate_read_grant_in_session`. It validates the deployment flag, audience, owner-scoped grant, active connection, grant state/expiry, registered provider/capability/operation/version/audience/purpose/destination contract, and required current scopes while holding connection then grant row locks.
- Kept `validate_read_grant` as a compatibility wrapper that opens its own transaction and delegates to the in-session validator.
- Moved snapshot payload reads and cursor reads into the same transaction as authorization. The connection/grant locks remain held through the protected query.
- Revalidated authority inside `apply_sync` after the external provider read and before any snapshot/cursor/audit persistence. Snapshot lookup is explicitly owner-scoped.
- Required an active, current grant before cursor reset; a revoked grant cannot mutate cursor state.
- Added three focused test functions covering transaction-scoped snapshot reads, scope/capability changes before sync persistence (two parameter cases), and cursor reset after revocation; the snapshot response test also preserves the existing `capability` field. A separate real-PostgreSQL concurrent revoke/read regression is on the follow-up branch.

## Acceptance scenarios

| Scenario | Required outcome |
| --- | --- |
| Existing authorized snapshot read | Returns only owner-scoped active snapshots |
| Snapshot read uses a separate preflight transaction | Regression fails; protected read must use the in-session validator |
| Required OAuth scope removed after provider response | Reject with `connector_scope_missing`; do not persist snapshot or advance cursor |
| Grant revoked before cursor reset | Reject with `connector_read_revoked`; cursor and generation remain unchanged |
| Expired grant / inactive connection / changed registered contract | Reject through the same validator |
| Concurrent revoke while a protected read holds the connection/grant locks | New PostgreSQL CI regression must pass on the follow-up head; separate protected staging still required |

## Verification boundary

- The source fix is merged in PR #498. The PostgreSQL concurrency test and updated evidence record are on follow-up branch `codex/part02-postgres-concurrency-evidence-20261020`.
- Focused test execution is not claimed from this connected GitHub editing session.
- On PR #498's merge SHA, `test-and-build` passed while `coworker` was still in progress; no completed `ci-merge-gate` result was available at the latest observation. Follow-up exact-head checks remain pending.
- PR #498 has no submitted independent review. Independent review of the merged source and follow-up concurrency regression remains required.
- Added a real-PostgreSQL CI regression that pauses after authorization, observes a concurrent revoke attempting its grant-row lock, and asserts the revoke waits until the snapshot transaction finishes. Exact-head CI is pending; protected staging and independent review remain required.
- No staging, production qualification or capability activation is claimed.

## Residual limits

A read transaction that acquired authorization locks before a revoke can commit may still return an already-authorized in-flight response after the revocation request begins; no database transaction can recall bytes already read or a response already in flight. The guarantee is serialized authorization at the database operation, not retroactive cancellation of already-authorized network responses. Provider calls already in flight likewise cannot be recalled, but their returned data must fail current-authority validation before persistence.

**Overall architecture/core status remains INCOMPLETE.** This is a bounded source-level hardening slice, not full A-01/A-04/P-02 or production qualification.
