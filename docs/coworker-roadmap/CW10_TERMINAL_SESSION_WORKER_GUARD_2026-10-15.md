# CW-10 — terminal sandbox session revokes sibling worker authority

**Date:** 15 October 2026. **Base:** `main` `4015dc9fc30525b2344f522d5e0b195ed5d35fd3` (merged PR #414; PR-head and merged-main mandatory CI pending at bootstrap). **Branch:** `codex/cw10-terminal-session-worker-guards-20261015`. Scope: bounded worker-control safety repair, not model-generated code execution or feature activation.

## Defect and user-visible outcome

A SandboxSession can contain more than one SandboxExecution. One worker may hold a valid, unexpired lease while a newly prepared sibling execution is rejected for source-integrity violation by `claim_executions`. That rejection transitions the **shared session** to `failed`, but does not revoke the other execution's already-claimed lease. Previously `worker_control` and `complete_execution` checked cancellation and chronological expiry, **not** the general terminal session state. The earlier worker could therefore continue receiving a lease extension, or submit a successful result under a failed session. This is source-level logic with deterministic regression, not proof of an observed production compromise.

**Outcome:** Every terminal session (`failed`, `completed`, `cancelled`, `expired`) denies further worker authority or result acceptance, even where its expiry timestamp remains in the future and cancel_requested is false. Already claimed source is scrubbed when the worker returns; claim/lease revoked; sandbox cleanup remains `required`. A worker cannot use a failed shared session to create a verified artifact or ToolReceipt.

## Scope and implementation

- In the authenticated `SandboxRepository.worker_control` transaction, inspect terminal state before extending an otherwise active lease. For non-cancellation, non-expiry terminal state, mark the current execution failed with `sandbox_session_closed`, scrub source, revoke lease and return `stop/session_closed` without changing its sibling-induced terminal session state.
- In the `SandboxRepository.complete_execution` transaction, reject any terminal session, not just cancellation/timeout. Preserve the actual `failed` state for a sibling-induced integrity failure; scrub and revoke the previous execution and reuse PR #414's commit-before-typed-409 mechanism.
- Keep exact current policy hashes, owner grant, worker identity, no-network isolation, receipt validation and default-off switches unchanged. No schema migration, new approval/action ledger or auto-generated-code execution path.

## Reproduction and acceptance

- `tests/test_sandbox_control_plane.py::test_terminal_session_failure_stops_other_claimed_sandbox_worker`: parameterized real repository worker control and completion. Claim code A, then prepare code B, alter its stored source, invoke the real integrity-gated claim, observe shared terminal failure while A remains leased; both heartbeat and completion must terminate A, scrub, revoke and deny further claims.
- `tests/test_coworker_postgres.py::test_postgres_terminal_sandbox_session_blocks_prior_worker_result`: real PostgreSQL verifies same progression and durable committed rejection. Tests inspect raw persisted rows *before* any later scavenger endpoint.
- Require exact branch-head `test-and-build`, mandatory no-skip `coworker` including PostgreSQL/Temporal/sandbox/browser/transactions, and `ci-merge-gate`. Independent adversarial review and operated worker isolation remain distinct gates. No local full repo environment; source/test changes committed pending CI evidence.

## Dependencies and next action

Review branch with owner/sibling integrity, stale claim, cancellation and completed artifact adversarial cases. Keep the PR draft until required tests pass; do not merge/deploy/activate without explicit authorization and applicable review. Then implement the **remaining C-04 generated-code proposal/approval**: immutable owner/run/code/input/limit binding, explicit human decision with expiry/revocation and claim-time atomic verification, bounded actual sandbox execution and cleanup. CW-09 operated network/DNS/SSRF, CW-11 grant-bound reviewed skill publication and personal coworker scenarios are independently open.
