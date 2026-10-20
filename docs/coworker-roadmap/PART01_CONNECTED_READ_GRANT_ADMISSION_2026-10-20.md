# Part 01 — Atomic Connected-Read Grant Admission

**Date:** 20 October 2026 (Asia/Dhaka)  
**Status:** Implemented on review branch; exact-head CI and independent review pending  
**Scope:** A-01 trust boundaries, A-04 current permission enforcement, P-02 revocation

## Objective

Prevent a connected-read grant from being persisted when the connection is disconnected or loses a required OAuth scope between authorization preflight and grant persistence.

## Baseline and branch

- Repository: `rumman52/Shuddho`
- Base `main` SHA at task start: `bb366506d07ab2748fbbc8ea8d36b7b799f9cfb7` (merge commit for PR #496).
- Work branch: `codex/part01-connected-read-grant-admission-20261020`.
- Existing relevant behavior: `PermissionGateway.validate_read_connection`, `ConnectorReadRepository.create`, and `ActionRepository._disconnect`.
- No database migration, new endpoint, new grant type, capability enablement, or production configuration change.

## Root cause

`ConnectorReadRepository.create` validated the connection in a separate session, then inserted a `ConnectorReadGrant` in a later transaction without re-reading the connection. A disconnect or scope change in that gap could leave a persisted grant marked active even though its authority had been revoked.

## Implementation

The grant-creation transaction now:

1. Locks the current owner-scoped, active `Connection` row before touching grant state, matching the disconnect path's connection-first lock order.
2. Rejects a missing/inactive connection.
3. Compares the locked provider, capability, subject and account identity with the preflight authorization.
4. Rechecks that every code-owned required scope is still present.
5. Only then handles idempotency and inserts the grant/cursor/audit record.

The authorization remains restricted to the existing registered capability, purpose, destination and audience. This change does not expand authority.

## Acceptance scenarios

| Scenario | Required outcome |
| --- | --- |
| Positive control: normal connected-read grant creation and sync | Existing tests continue to pass |
| Disconnect after preflight but before persistence | Fail closed with not-found; no grant or cursor is created |
| Required OAuth scope removed after preflight | Fail closed with `connector_scope_missing`; no grant or cursor is created |
| Cross-owner grant access | Existing owner-scoped tests continue to reject access |
| Runtime/staging concurrency | PostgreSQL lock ordering serializes grant admission against disconnect; must be exercised in protected staging |

The new regression test injects the disconnect/scope change immediately after the preflight authorization returns, making the time-of-check/time-of-use gap deterministic. This is a repository test, not a claim that a concurrent PostgreSQL race has already been operated.

## Files changed

- `services/coworker/connector_reads.py`
- `tests/test_connector_reads.py`
- `docs/coworker-roadmap/PART01_CONNECTED_READ_GRANT_ADMISSION_2026-10-20.md`
- `docs/coworker-roadmap/ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md`
- `docs/coworker-roadmap/PROGRESS.md`

## Verification and release boundaries

- Focused local test execution is not claimed from this connected GitHub editing session.
- Required next checks: `pytest -q tests/test_connector_reads.py tests/test_permission_gateway.py`, then exact-head `test-and-build`, `coworker`, and `ci-merge-gate`.
- The pull request must receive independent review; do not merge merely because an early job passes.
- Operated PostgreSQL staging is still required to prove connection-first lock ordering under concurrent disconnect and grant admission.
- Production defaults remain unchanged; no capability activation is authorized.

## Completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Complete on review branch | Source guard and deterministic regression tests committed |
| Repository-verified | Pending | Exact-head required CI and independent review |
| Staging-verified | Pending | Protected PostgreSQL concurrency/revocation test |
| Production-qualified | Not established | Broader A-01/A-04/P-02 security and release gates remain |
| Activated | No | No activation requested or performed |

**Residual risk:** This bounded fix closes the grant-admission gap; it does not prove every owner/run/source/artifact boundary or qualify the full trust-boundary architecture.
