# Day 10 — absolute security verdict for independently reviewed holdout

- **Objective:** Prevent `READY_FOR_OWNER_CONTROLLED_PILOT` when any one of forty independent holdout cases has an absent, false, or non-boolean security verdict, even if 39/40 human-reviewed outcomes meet all quality thresholds.
- **Dependency / source truth:** `docs/coworker-roadmap/DAY9_PILOT_QUALIFICATION_2026-11-12.md` states an absolute security NO-GO; the unchanged canonical cohort gate remains authoritative.
- **Base:** `main` now includes the fix from [merged PR #705](https://github.com/rumman52/Shuddho/pull/705) (merged 2026-11-13 18:34 UTC).
- **Merged source:** `scripts/day10_release_decision.py::holdout_ok` now requires explicit boolean `security_passed=true` for every case; the fix is part of the current main history.
- **Existing interface:** `scripts/day10_release_decision.py::holdout_ok` and the read-only `decide` collector; no new release authority, schema, provider or activation path.
- **Files:** Day 10 decision script, its existing tests, Day 10 operator handoff and this task record; PROGRESS status updated separately.
- **Evidence contract:** Each of 40 D-controlled case records has explicit JSON boolean `security_passed: true` from actual operated deterministic security verification. Missing, false and string values are not equivalent. Human-accepted thresholds stay >=36/40 overall and >=9/10 in each workflow/language cell. This CLI still cannot authenticate the human/operator receipt.
- **Reproduction (RED):** [test-only commit `4b2a13c`](https://github.com/rumman52/Shuddho/commit/4b2a13cbba354dae76e45cb28285ad31856c95c6); [exact-head run 43461268411](https://github.com/rumman52/Shuddho/actions/runs/43461268411), `test-and-build` Python suite: **3 new expected failures**, **1,947 passed, 81 skipped, 6 warnings**. Every new failure shows the unsafe `READY_FOR_OWNER_CONTROLLED_PILOT` instead of `SOURCE_ONLY` at 39/40 accepted outcomes.
- **Minimal fix:** A single fail-closed per-row guard before counting accepted holdout outcomes. No threshold adjustment and no production/pilot operation.
- **Repository verification:** corrected-head [run #43461923994](https://github.com/rumman52/Shuddho/actions/runs/43461923994) passed `test-and-build` with **1,950 passed, 81 skipped, 6 warnings, 0 failed**; frontend tests/builds, browser qualification and PR ancestry also passed on that review head. The full Coworker and PostgreSQL 18 jobs were still running at that historical check. This is not staging evidence.
- **External prerequisites:** Native main protection is now active and separately audited; current staging uses the active Supabase PostgreSQL project at Alembic `0070`, not the expired Render PostgreSQL service. Still outstanding: private off-platform backup and restore drill, persistent paid worker, operated Temporal/S3/API/worker evidence, 40 independent D evaluations, 20 operated recovery rows, founder+C approval.
- **Out of scope:** Billing changes, production activation, external action sends, new telemetry ingestion, synthetic pilot authorization.

## Evidence levels

| Level | Status |
| --- | --- |
| Implemented | Merged in PR #705 |
| Repository-verified | Corrected-head Python, frontend, browser and ancestry checks passed |
| Staging-verified | No (API is live; worker and live archive/restore remain absent) |
| Production-qualified | No |
| Activated | No |

The security gate is merged and repository-verified. Do not treat synthetic CI as independent holdout evidence; only D-controlled receipts from actual operation can satisfy the pilot gate.
