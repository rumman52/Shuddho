# Mandatory main CI recovery — Day 2 / Day 7 / Day 8 source mismatches

- **Objective:** repair deterministic source/fixture mismatches blocking mandatory exact-head CI after the Day 6 and Day 2 merges, without changing the runtime authorization, quality thresholds or release posture.
- **Dependency evidence:** merged [#804](https://github.com/rumman52/Shuddho/pull/804) and [#805](https://github.com/rumman52/Shuddho/pull/805); current main `8abb5972e6b03e86bc891d736eb2854b63c53b61`; [failed main CI #44598107021](https://github.com/rumman52/Shuddho/actions/runs/44598107021).
- **Base branch/SHA:** `main` / `8abb5972e6b03e86bc891d736eb2854b63c53b61`.
- **Work branch:** `codex/restore-main-ci-day2-day7-day8-20261120`.
- **Interfaces reused:** `_day8_cases` and `compare_day8_development`; `run_probe` / `Day2Failure`; `_enable_briefings` / `automation_container` test fixture.
- **Files changed:** `scripts/core_agent_observability.py`, `tests/test_staging_day2_execution.py`, `tests/test_automations.py`, `docs/superpowers/plans/2026-11-20-restore-main-ci-source-contracts.md`, this contract, and `docs/coworker-roadmap/PROGRESS.md`.
- **Follow-on PR-head reproduction:** run #44602686715 was 1 failed / 195 passed in Day 8 Coworker. Its remaining failure exposed `AutomationRepository.notify_run_completed` not linking the one briefing completion receipt to the occurrence. Fix adds occurrence ID **only** for briefing completion; non-briefing start notice retains the unique occurrence ID and separate completion receipt. The focused existing briefing test and proactive separate-notice test cover both invariants.
- **Public/API/database compatibility:** no interface/schema/migration change; no new dependency.
- **Expected outcomes:** the Day 8 parser tuple is correctly destructured; missing owner-B control remains rejected pre-write; the positive Day 7 briefing test explicitly opts into required local fixture capabilities, without enabling them in production.
- **RED reproduction:**
  - `test-and-build`: one failed Day 2 assertion only because expected regex starts lowercase, versus actual `Owner B`; 2531 passed / 93 skipped (main run #44598107021).
  - `coworker` Day 8: 28 failed / 168 passed due `_day8_cases` tuple used as mapping and one positive briefing test lacking flags.
- **CI to verify:** `uv run --locked --extra coworker pytest -q tests/test_core_agent_observability.py tests/test_staging_day2_execution.py tests/test_automations.py`; full `test-and-build` and mandatory Coworker job on the PR head.
- **Safety boundaries:** source/CI only; no secrets, external provider calls, production actions, owner grants, writes, provisioned services, paid infrastructure, or telemetry ingestion.
- **Approval:** a separate, attributable human reviewer and admin-managed GitHub App/ruleset repairs remain prerequisites for merge. This PR does not carry Founder/Owner-C release authorization.
- **Out of scope:** Day 9 independent holdout (40 cases), 20 operated recoveries, Day 10 signed release decision, staging parity, 2 natural scheduler fires, and pilot admission.
- **Rollback:** revert this commit if CI finds an unintended regression.
- **Residual risk:** the Day 8 parser also produces rerun and provenance metadata; this patch only repairs the consumer type mismatch, not an independently qualified first-run/rerun custody workflow.

## Completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Patch proposed | New PR branch and exact files listed above |
| Repository-verified | Pending exact-head CI | PR test and release checks |
| Staging-verified | Not established | No paired API/worker/schema operating proof |
| Production-qualified | No | Required Day 9/10 evidence and approvals missing |
| Activated | No | No pilot admission or feature rollout |

**Exact next action:** run and inspect mandatory CI on the new head; obtain independent review and platform governance repair before merge. Do not alter release counts from this source-only correction.
