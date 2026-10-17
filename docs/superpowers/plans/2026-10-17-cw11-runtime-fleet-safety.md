# CW-11 Runtime Fleet Safety Implementation Plan

> **For agentic workers:** Implement inline with executing-plans; obtain independent requesting-code-review before handoff.

**Goal:** Prevent uncertain worker records or unfinished Temporal shutdown from authorizing reviewed-skill admission, selection, rollback or legacy migration.

**Architecture:** Reuse the authoritative worker registry and publication controls. Fail closed on uncertain rows in the requested queue and publish `drained` only after successful Temporal worker shutdown. Keep deployment/fleet-wide qualification separate from these repository guarantees.

**Tech Stack:** Python, SQLAlchemy, PostgreSQL/SQLite, Temporal, pytest.

**Spec:** `docs/coworker-roadmap/SPEC.md`, `docs/CW11_TRUSTED_SKILL_ROLLOUT.md`, acceptance inventory A-03/A-04/C-05.

## Global Constraints

- Preserve grants, publication hashes, one-call research budget, old histories and default-off capability controls.
- No new state ledger, schema migration, provider call, merge, deployment or activation.
- Work on `codex/cw11-runtime-fleet-safety-20261017`, based on `main` `640f42f0dbc289ab7b28d86128cbe88cb4610fcb`; PR #446 is merged; retain its collector changes from the current mainline.
- Current invocation and attached execution brief authorize implementation and reviewable PRs without a routine approval pause.

## Review Focus

- A fresh candidate must not hide lost, unknown or stale workers.
- A drained row without a completion timestamp cannot prove shutdown.
- Another task queue must not affect this queue's controls.
- A failed/cancelled Temporal shutdown must never publish `drained`.
- Registry evidence does not prove that unregistered old processes stopped or that in-flight provider outcomes were reconciled.

### Task 1: Enforce the runtime fleet contract

**Files:** `services/coworker/repository.py`, `tests/test_cw11_registry.py`.

**Interfaces:** Preserve public method signatures. Selection, rollback and admission consume `_require_compatible_worker_fleet`; migration consumes `assert_worker_drain_complete`.

- [x] Add SQL-backed regressions for lost/unknown/inconsistent-drained rows, stale compatible rows beside a fresh worker, selection/admission/rollback denial without state changes, drain/migration denial and unrelated queue isolation.
- [x] Run the new cases before editing source; expect assertion failures because unsafe controls currently succeed.
- [x] Inspect every queue row under the existing transaction locks; reject uncertain rows with a deterministic error; require exactly `drained` plus `drained_at` for old-worker drain evidence.
- [x] Run the registry and staging collector suites; preserve existing incompatible/unavailable errors and valid drained-worker behavior.

### Task 2: Make drained mean completed shutdown

**Files:** `services/coworker/worker.py`, `tests/test_cw11_registry.py`.

**Interfaces:** `main()` still uses the same Worker, dispatcher and heartbeat. No workflow/activity identity changes.

- [x] Add a controlled Worker-context lifecycle regression proving no drained state before/during `__aexit__`, successful drain afterward, and no drained state on exceptional/cancelled exit.
- [x] Observe the ordering/exception regressions fail on the base implementation.
- [x] Publish drain completion only after successful Worker context exit and clean dispatcher/heartbeat termination; dispose the database pool on every exit.
- [ ] Finish broad checks and final independent review; record evidence and open a draft PR.


### Task 3: Canonicalize PostgreSQL registry lock order

**Files:** `services/coworker/repository.py`, `tests/test_cw11_registry_postgres.py`, `.github/workflows/ci.yml`.

- [x] Establish the same order for selection, admission, rollback and migration: queue worker rows ordered by ID → selection → publication(s).
- [x] Add deterministic event-coordinated PostgreSQL concurrency cases for selection versus admission and selection versus rollback.
- [x] Add the PostgreSQL module to the mandatory CW-11 JUnit gate; the CI result is still pending on this rebased revision.
- [ ] Inspect fresh exact-head required CI and confirm the new module has zero skips.

## Execution ledger

- Base checkout was clean. Dependencies installed with `uv sync --frozen --group dev --extra coworker`.
- PR #446 exact-head CI #38967176820 passed; its collector patch is not merged and is not duplicated here.
- Independent bounded review identified premature `mark_worker_drained` before Temporal context exit; included in this task because it invalidates the same drain authority.
- Remaining operated acceptance: protected staging, full deployment inventory, PostgreSQL/Temporal process-restart/mixed-version evidence, browser and sandbox isolation, human model-quality evaluation and release review. These are not implied by this slice.

- Initial regressions reproduced: fleet/drain 22 failed, 9 passed; lifecycle 5 failed, 1 passed; unknown-state heartbeat 1 failed, 1 passed.
- Affected pre-final heartbeat-guard tree: registry + collector 48 passed, zero skips, mandatory-module gate passed. Final unknown-state guard subset: 2 passed, 45 deselected.
- Release contract and Python syntax checks passed. Full 2257-test suite running; final whole-diff independent review pending.

- Final independent review: no Critical/Important/Minor findings; 50 affected tests passed on the final source/test tree. Pre-existing lock-order, per-claim drain and registration races remain documented future work, not silently accepted as solved.


## 17 October continuation checkpoint

The current mainline base is `640f42f0dbc289ab7b28d86128cbe88cb4610fcb`. The branch is being reconciled with merged #446 while retaining #447's worker/drain changes. The PostgreSQL registry lock-order regression is now mandatory in CW-11 CI. The intermittent SQLite malformed-schema/duplicate-index symptoms remain unexplained; no fix is claimed without a causal reproduction. Staging, production qualification and activation remain separate gates.
