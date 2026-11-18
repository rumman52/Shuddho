# Day 10: bind real GitHub contexts and both runtime readbacks (18 November 2026)

## Task contract
- **Objective:** prevent a Day 10 READY decision when API/worker build digests or the worker's full capability readback are missing or drifted, or when CI reports successes under invented aliases instead of exact GitHub check names.
- **Tracker / base:** [#736](https://github.com/rumman52/Shuddho/issues/736); main `aa705726f4c76cbb819a62211b7743aa44c59b17` (after #774 merged; original reproduction on `c8aa7cf8444f1cf8c5408568e78b3cae6792f00a`).
- **Review branch:** `codex/day10-exact-readback-ci-20261118`. This source branch is **not a frozen deploy candidate**.
- **Existing interfaces:** `scripts/day10_release_decision.py:decide`, `scripts/ruke_pilot_eval.py:BUILD_DIGEST,REQUIRED_DAY9_CI`, `scripts/staging_release_freeze.py:RUNTIME_CAPABILITY_KEYS`, `scripts/cohort_release_gate.py:evaluate_release`.
- **Files:** the Day 10 evaluator and its existing tests; this contract and a dated operator handoff; historical PROGRESS entry.
- **Contract delta:** require a lowercase `sha256:<64 hex>` build digest on API and worker readbacks; require worker runtime schema v2, exact environment, all 43 boolean capabilities (including false values) equal to the rollout, and exact action-provider set. Do not change any capability default or provider implementation. Require the seven real GitHub check names from canonical Day 9 `REQUIRED_DAY9_CI`, not `frontend` or `postgres-18-qualification` aliases.
- **Reproduction on unchanged main:** `tests/test_day10_release_decision.py:evidence()` supplies neither build digest nor worker flags yet `test_not_a_production_activation_even_when_qualified` expects READY using a monkeypatched canonical gate. The main test/build job was green on [run #44278207003](https://github.com/rumman52/Shuddho/actions/runs/44278207003). This demonstrates a source validation omission; **not** a live pilot event. Actual GitHub job names are `Frontend tests and builds` and `PostgreSQL 18 staging compatibility`.
- **New negative scenarios:** missing/malformed API or worker build digest; wrong worker schema/environment; missing/extra/nonboolean/enabled-drifted worker flag; provider drift; aliases supplied instead of actual CI names.
- **Expected failure:** `SOURCE_ONLY` plus the existing corresponding API, worker, or final-head-CI blocker. A positive **mocked** fixture remains READY only as an isolated unit test, not an operated release.
- **Focused verification:** `uv run --extra coworker pytest tests/test_day10_release_decision.py tests/test_cohort_release_gate.py tests/test_staging_release_freeze.py -q -rs`; CLI help `uv run --extra coworker python scripts/day10_release_decision.py --help`. Mandatory exact-head CI and independent review follow.
- **Boundaries:** source-only; no database migrations, Render/Vercel deploys, credential reads, paid provider calls, human impersonation, external sends, telemetry changes, ruleset relaxation, feature-flag toggles or pilot admission. Canonical quality/fact-recall/holdout/recovery gate logic unchanged.
- **Evidence trust:** JSON fields and GitHub URLs are self-reported. The operator must independently authenticate API/worker image-build digests, snapshots, CI, model evaluations, receipts and distinct signoffs; this script is not an attestation service.

## Completion evidence
| Level | State at commit | Evidence |
|---|---|---|
| Implemented | Proposed for review | This branch: evaluator, positive fixture, 13 new negative cases |
| Repository-verified | Pending exact-head CI and independent review | Verify PR checks against immutable PR head |
| Staging-verified | Not complete | [Day 10 live gate #736](https://github.com/rumman52/Shuddho/issues/736) |
| Production-qualified | No | Genuine holdout, recovery, quality, rollback and approvals missing |
| Activated | No | Never toggled flags/admitted users |

**Next step:** run focused tests, then inspect full PR-head CI and independent review. C must resolve GitHub App credentials and ruleset drift separately. No fake rollout ID or digest is created.
