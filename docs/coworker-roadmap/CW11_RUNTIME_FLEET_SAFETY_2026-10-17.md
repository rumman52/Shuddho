# CW-11 runtime fleet and confirmed drain safety

- **Objective:** A reviewed-skill control must not treat an unaccounted worker as safely absent, or a worker still stopping Temporal activities as already drained.
- **Base:** `main` `640f42f0dbc289ab7b28d86128cbe88cb4610fcb`; clean dedicated checkout; branch `codex/cw11-runtime-fleet-safety-20261017`.
- **Dependencies:** Existing publication/selection/rollback registry, worker inventory and legacy migration. PR #446 is merged into the base; its collector hardening remains intact and is not duplicated.
- **Interfaces/files:** `Repository._require_compatible_worker_fleet`, `assert_worker_drain_complete`, `heartbeat_worker`, `mark_worker_drained`; worker heartbeat and `main()` lifecycle; `tests/test_cw11_registry.py`; `tests/test_cw11_registry_postgres.py`; the mandatory CW-11 CI gate. Public signatures, persisted schema and Temporal identities stay compatible.
- **Initial reproduction:** Existing registry/collector baseline: 11 passed. New fleet/drain cases: 22 failed, 9 passed; lifecycle cases: 5 failed, 1 passed. A real SQL unknown-state heartbeat also returned `running` (1 failed, 1 passed). Failures demonstrate admitted controls, false drain evidence, premature publication and a dead heartbeat leaving dispatch unstopped.
- **Expected denial:** Lost/unknown states, stale active heartbeats, and drained rows without timestamps block select/admit/rollback. Every legacy row must have a completed drain before migration. Denials leave selection, publication lifecycle, registry events and Task admission unchanged. Another queue is isolated.
- **Lifecycle:** Registry completion follows successful `Worker.__aexit__`, which awaits Temporal shutdown. Dispatch/heartbeat/shutdown errors or cancellation skip completion. The engine is disposed on success and failure. Heartbeat errors stop dispatch and still propagate.
- **Budget/authority:** No provider/model calls, credentials, grants, API authority, research limits or release activation added. Existing default-off controls remain. No migration or paid provisioning required.
- **Validation:** Focused registry/collector suite, mandatory-module JUnit gate, Python compilation, broader available pytest suite, required exact-head GitHub `test-and-build`, `coworker`, `ci-merge-gate`, independent bounded review.
- **External prerequisites:** Real protected staging and deployment inventory; PostgreSQL/Temporal processes, provider reconciliation and operated mixed-version recovery. Synthetic Worker contexts prove Python ordering and failure behavior only.

## Registry transaction lock order

All reviewed-skill control transactions use the order worker inventory rows (ordered by ID) → selection row → publication row(s). Admission's initial unlocked read is only for error classification; it re-reads the selected publication after acquiring the worker locks. The PostgreSQL test coordinates selection against admission and rollback so the old lock cycle is reproducible rather than timing-dependent.

## Evidence and next action

| Level | Status |
| --- | --- |
| Implemented | Implementation 1b246442; independent affected checks 50 passed |
| Repository-verified | Pending final exact-head required CI |
| Staging-verified | Blocked on matching operated staging evidence |
| Production-qualified | Not established |
| Activated | No |

Independent source review reproduced premature completion and uncertain-record
acceptance. Final independent diff review found no material findings; validation results are recorded in the canonical
`PROGRESS.md` checkpoint rather than inferred from the presence of these tests.

The registry selection/admission/rollback lock-order issue is included in this revision. Remaining review findings are per-claim drain fencing for Agent/action outboxes and preventing a new legacy worker from registering after a fleet snapshot. The patch does not prove fleet-wide quiescence.

The prior intermittent parallel SQLite malformed-schema/duplicate-index symptoms remain unresolved: two failures were reported and then passed in a serial rerun, but no causal reproduction has been captured. No SQLite fix is claimed.

PR #447's previous exact-head CI applies to the older revision only. Fresh exact-head CI and independent review are required for this rebased source/test tree.
