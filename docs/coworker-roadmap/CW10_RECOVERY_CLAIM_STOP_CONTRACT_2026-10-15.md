# CW-10 — align stale worker recovery denial with terminal stop protocol

**Date:** 15 October 2026 (Asia/Dhaka). **Base:** `main` `baa484ef861e41daf7653a29f6aaa07720932055` (merged PR #415). **Review branch:** `codex/cw10-recovery-claim-stop-ci-repair-20261015`.

## Failure reproduced in mandatory CI

Main [CI #38760717140](https://github.com/rumman52/Shuddho/actions/runs/38760717140), `coworker` job, reported eight failures in the `recovery_claim=True` variants of `test_sandbox_worker_claim_fails_closed_on_changed_persisted_source`; 1,375 other tests passed in the affected invocation. All eight expected `CoworkerError` from `worker_control` after source-integrity failure. The service instead returned `{"action":"stop","reason":"session_closed"}`, consistent with the **newer** terminal-session contract documented in [CW10_TERMINAL_SESSION_WORKER_GUARD_2026-10-15.md](CW10_TERMINAL_SESSION_WORKER_GUARD_2026-10-15.md).

## Contract and bounded change

Keep the existing production handler `SandboxRepository.worker_control` returning `stop/session_closed` for a terminal session. The worker must not receive a renewed lease; its stale execution must remain failed with `sandbox_source_integrity_failed`, scrubbed source, revoked claim and lease, and shared session `failed` with `cleanup_state=required`.

Update the existing eight recovery-claim assertions to inspect the explicit stop response. Add a real `complete_execution` attempt using an otherwise valid successful worker observation: it must reject the stale result with `sandbox_worker_claim_invalid` or `sandbox_session_closed` and leave persisted failure, no result, source scrubbed, no worker lease, and session terminal. Preserve all eight tamper modes and their first-claim cases, so no original denial or cleanup assertions are removed.

## Interfaces, compatibility and scope

- Test-only change in `tests/test_sandbox_control_plane.py`. No production runtime code, schema, migration, grant, sandbox policy, provider, or release flag change.
- `stop/session_closed` is an explicit fail-closed control signal. A 409 from completion remains required for a stale result; terminalized control should not be changed to throw merely to match a superseded test assertion.
- Feature remains disabled unless its independent release gates are satisfied. No credentials, external mutations, provider provisioning, merge or production activation.

## Required qualification

1. Mandatory `coworker` suite including this complete parametrized test, PostgreSQL, Temporal, transactions, browser and sandbox suites, with no skips in required gates.
2. Final review branch SHA must pass `test-and-build`, `coworker`, `ci-merge-gate` in its own GitHub CI run.
3. Independent review and operated real sandbox isolation remain additional evidence, not implied by repository checks.

## Progress evidence

- Root-cause alignment: mainline handler and CW-10 terminal-session design agree; older test expects an exception instead of a stop control response.
- Previous failure: [main CI #38760717140](https://github.com/rumman52/Shuddho/actions/runs/38760717140).
- Branch-head CI: pending after PR creation.
- Model-generated immutable code proposal, human decision/expiry/revocation and atomic approval verification remain **incomplete** in CW-10/C-04.
