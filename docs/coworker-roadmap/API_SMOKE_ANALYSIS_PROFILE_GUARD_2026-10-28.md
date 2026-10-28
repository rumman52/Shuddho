# API smoke analysis-profile fail-closed guard — 28 October 2026

## Task contract

- **Objective:** Prevent an operator from mistaking an empty degradation-reason list for proof that checkpoint-backed local analysis is fully ready.
- **Dependency / current evidence:** Issue [#583](https://github.com/rumman52/Shuddho/issues/583) leaves production readiness semantics and deployment configuration unresolved. Existing `scripts/api_deployment_smoke.py` has an optional `--require-analysis-ready` flag; previously, a missing `analysis_profile` with `degraded_reasons=[]` passed.
- **Base revision:** `bfcf85c1e1990093520ca4b03551424524b9b3d2` on `main`.
- **Branch:** `fix/api-smoke-analysis-profile-guard-20261028`; draft PR required, not merged.
- **Interfaces reused:** public read-only `GET /health` and `GET /version`; existing `AnalysisProfile` enum and `httpx.MockTransport`.
- **Files:** `scripts/api_deployment_smoke.py`, `tests/test_api_deployment_smoke.py`, `docs/API_DEPLOYMENT_READ_ONLY_SMOKE.md`, this task contract, and `docs/coworker-roadmap/PROGRESS.md`.
- **Contract:** ordinary liveness + exact-source smoke remains GET-only. `analysis_status=ready` requires `analysis_profile=full_local` and no degradation reasons. Known partial profiles or nonempty degradation reasons mean `degraded`; missing/unknown profiles mean `unverified`. The optional strict flag rejects both non-ready states. Neither a read-only smoke pass nor metadata assertions amount to production qualification.
- **Initial failure:** With `analysis_profile` missing but `degraded_reasons=[]`, the original checker reported `ready` and accepted `require_analysis_ready=True`. This is a code-inspection finding, not a claimed live service failure.
- **Regression coverage:** synthetic missing, unknown, and four degraded profiles with an empty reason list must fail the strict flag; full-local with no reasons must pass. All tests use a mock HTTP transport and no real network.
- **Expected command:** `uv run pytest tests/test_api_deployment_smoke.py -q`; also require repository CI on the final PR head, review and the pre-merge gate.
- **Authority / secrets:** no environment changes, tokens, production POSTs, provider traffic, deployments, database mutations or live analyzer calls. No new feature flags.
- **Rollback:** revert the review-branch commits; main is unchanged until independently approved and merged.
- **Out of scope:** production readiness/health policy decision, Render health-check configuration, detector/corrector checkpoint provisioning, PA-10, transaction/provider qualification, production activation.

## Completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Proposed on review branch | File updates; not merged |
| Repository-verified | Pending | Exact final-head CI and independent review required |
| Staging-verified | Not performed | No live endpoint requests |
| Production-qualified | No | Separate operator / release gates |
| Activated | No | No deployment or feature change |

**Next exact action:** open draft PR, check exact head CI, obtain independent review, then require enforceable V-01 ruleset and merge-button negative control before allowing any main merge.