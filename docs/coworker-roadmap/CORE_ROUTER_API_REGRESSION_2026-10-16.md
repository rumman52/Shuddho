# Core routing — real API regression and mandatory CI repair

- Base: main `badc8bbb66c8ead4a43c3463e32112b1bfd7e996`; independent of CW-10 scope PR #421.
- Branch: `codex/core-router-api-regression-20261016`.
- User-visible invariant: a direct-answer question sent to Agent admission returns typed `409 agent_route_direct_answer` without an AgentRun, AgentOutbox or Task, including repeated identical requests.
- Root cause: the direct-call `AgentMustNotRun` double implements only `create`. The actual API first calls read-only `public_idempotent_replay`, so the test raises AttributeError before its routing assertion. Reproduced independently on unmodified main (one failure, 1.25s). This is stale test infrastructure, not evidence that simple questions actually launch work.
- CI gap: lightweight tests skip that one boundary when JWT is absent; the heavyweight job did not run `test_core_agent_router.py`. Existing routing scripts do not prove execution of this authenticated endpoint test.
- Repair: relocate the single boundary case into the existing heavyweight `test_coworker.py` fixture environment. Use the real signed HTTP client, actual AgentRepository replay path and database; assert typed denial twice and zero durable run/outbox/task rows. Pure routing tests remain in their lightweight module. Add the exact boundary node to the existing mandatory no-skip conversation/PG JUnit command and require its module in the gate.
- No production/API/provider/permission/schema changes. Existing approved/idempotent Agent-run behavior is untouched.
- Acceptance: the real refusal case and pure routing suite pass; mandatory group cannot skip/drop the authenticated boundary; focused coworker checks and exact-head CI remain required.
- Validation: **18 passed, zero skips** (2.49s); mandatory JUnit gate passed. An initial replacement fixture incorrectly enabled research without a provider; removed that unnecessary flag so settings validate with no external provider. Full Python suite pending on this branch; baseline CW-10 full run separately reports the stale original test failure.
- Files: `tests/test_core_agent_router.py`, `tests/test_coworker.py`, `.github/workflows/ci.yml`, this contract and canonical progress.
- Evidence levels: test/CI source repair only; full local suite, final-head CI and independent review pending. No staging, production qualification, merge, deploy or activation.
- Next: verify this branch's mandatory `test-and-build`, `coworker`, `ci-merge-gate` and review before integration; resume incomplete C-04 lifecycle and operated A/P/V gates separately.
