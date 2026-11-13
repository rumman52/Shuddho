# Day 10 — absolute security verdict for independently reviewed holdout

- **Objective:** Prevent `READY_FOR_OWNER_CONTROLLED_PILOT` when any one of forty independent holdout cases has an absent, false, or non-boolean security verdict, even if 39/40 human-reviewed outcomes meet all quality thresholds.
- **Dependency / source truth:** `docs/coworker-roadmap/DAY9_PILOT_QUALIFICATION_2026-11-12.md` states an absolute security NO-GO; the unchanged canonical cohort gate remains authoritative.
- **Base:** `main` `6b604e4cc13e98f740729f3b11df3ed432e04dcb`.
- **Review branch / PR:** `fix/day10-holdout-security-absolute-nogo-20261113`, [#705](https://github.com/rumman52/Shuddho/pull/705) (draft, independent review required).
- **Existing interface:** `scripts/day10_release_decision.py::holdout_ok` and the read-only `decide` collector; no new release authority, schema, provider or activation path.
- **Files:** Day 10 decision script, its existing tests, Day 10 operator handoff and this task record; PROGRESS status updated separately.
- **Evidence contract:** Each of 40 D-controlled case records has explicit JSON boolean `security_passed: true` from actual operated deterministic security verification. Missing, false and string values are not equivalent. Human-accepted thresholds stay >=36/40 overall and >=9/10 in each workflow/language cell. This CLI still cannot authenticate the human/operator receipt.
- **Reproduction (RED):** [test-only commit `4b2a13c`](https://github.com/rumman52/Shuddho/commit/4b2a13cbba354dae76e45cb28285ad31856c95c6); [exact-head run 43461268411](https://github.com/rumman52/Shuddho/actions/runs/43461268411), `test-and-build` Python suite: **3 new expected failures**, **1,947 passed, 81 skipped, 6 warnings**. Every new failure shows the unsafe `READY_FOR_OWNER_CONTROLLED_PILOT` instead of `SOURCE_ONLY` at 39/40 accepted outcomes.
- **Minimal fix:** A single fail-closed per-row guard before counting accepted holdout outcomes. No threshold adjustment and no production/pilot operation.
- **Verification required:** Green exact-head `test-and-build`, mandatory `coworker`, `frontend`, `browser-qualification`, PG18 test, PR ancestry, merge gate and independent review. Preserve all failures/skips in handoff; no staging-verified claim from synthetic CI data.
- **External prerequisites:** Native GitHub main protection, approved Render PG18 recovery/backup, persistent worker, real matched API/worker schema/provider, 40 independent D evaluations, 20 operated recovery rows, founder+C approval.
- **Out of scope:** Billing changes, production activation, external action sends, new telemetry ingestion, synthetic pilot authorization.

## Evidence levels

| Level | Status |
| --- | --- |
| Implemented | Source change committed on review branch; final review pending |
| Repository-verified | Exact corrected-head CI pending |
| Staging-verified | No (Render staging PG18 suspended; worker absent) |
| Production-qualified | No |
| Activated | No |

The next actor should verify exact PR head and all CI jobs, address independent review findings, and update this record with final SHA/results. Do not merge on the strength of a synthetic passing holdout.
