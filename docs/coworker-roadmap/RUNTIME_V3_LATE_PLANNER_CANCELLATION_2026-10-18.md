# Runtime v3 late planner cancellation task contract

- Objective and user-visible behavior: a cancellation or terminal transition that commits while Runtime v3 is awaiting the planner must prevent the late result from writing a new decision, creating a memory proposal, or appending work.
- Roadmap mapping: cross-cutting correctness work supporting the CW-06 acceptance criterion “cancellation beats delayed result.” This is not the roadmap's CW-02 transaction-chaos qualification task and does not complete all of CW-06.
- Dependency tasks and current evidence: reuse the existing Runtime v3 run ledger, cancellation transaction, planner reservation/settlement, and scoped context/memory services. The failing-first exact-head CI reproduced both unsafe writes before the fix.
- Initial failing-first commit/base: `87a37898979455b62b248098d3c5027f3490f5cd` based on `e52006c112c8b07623dbe1c07dc982406ce31084`; it was 13 commits behind current main.
- Implementation base branch/SHA: `main` `515dbc8d842645e3b93403cbe003e707642a4955`.
- Work branch/PR: `codex/cw02-v3-cancellation-race-20261018`; [PR #455](https://github.com/rumman52/Shuddho/pull/455). The branch name retains its historical `cw02` segment from the original test-only commit.
- Existing interfaces to reuse: `AgentRepository.record_v3_decision`, `AgentRepository.cancel_in_session`, `MemoryRepository.propose_from_agent`, and the existing `AgentRun` row lock.
- Exact files to create/modify: `services/coworker/agent_repository.py`, `services/coworker/memory_repository.py`, `tests/test_coworker.py`, this contract, `docs/coworker-roadmap/PROGRESS.md`, and `docs/coworker-roadmap/ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md`.
- New interface signatures / schema and compatibility: none; no API, database schema, workflow-history, or public contract change.
- Acceptance scenarios and assertions:
  1. Pause the planner response, cancel the owned run, then release the response; it must raise `agent_cancelled`, persist no new `AgentDecision` or `MemoryProposal`, and create no `ToolInvocation`.
  2. Direct memory-proposal persistence after cancellation must fail without a proposal row.
  3. A non-cancelled terminal run must reject late decision and memory writes.
  4. Replaying an already-recorded planner-call decision after cancellation remains idempotent and creates no duplicate.
- Reproduction / initial failure: [CI run #39059380961](https://github.com/rumman52/Shuddho/actions/runs/39059380961) — `test-and-build` passed; the mandatory `coworker` job failed exactly the two new regressions (2 failed, 1407 passed, 647.14s), showing a decision was recorded and a memory proposal was accepted after cancellation. Its head was based on `e52006c112c8b07623dbe1c07dc982406ce31084`; it is pre-fix evidence only.
- Expected failure outcomes: terminal/cancelled run is rejected before any new durable decision/proposal/work is written; the transaction remains consistent.
- Tests and required CI commands: the new regressions live in `tests/test_coworker.py`; require exact-final-head `test-and-build`, mandatory `coworker` with required suites collected and no required skips, and `ci-merge-gate`.
- Secrets / owner / grant / approval / egress boundaries: no provider calls, credentials, external actions, broadened grants, or authority changes.
- Budget / timeout / cancellation / revocation behavior: preserve existing planner reservation settlement in `finally`; revalidate cancellation/terminal state under the existing run-row lock at the write boundary.
- Default-off gate and rollback: no flags changed; no capability activation. A rollback reverts this coherent source/test slice while leaving prior cancellation and ledger behavior unchanged.
- External prerequisites: exact-head CI is required for repository verification. Full CW-06 dispatch/steering acceptance and operated PostgreSQL/Temporal/process-interruption evidence remain separate gates.
- Out of scope: the CW-02 transaction-chaos matrix, staging secret access, deployment, publication selection, provider activation, broad runtime redesign, and claims of production qualification.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Implemented on PR #455 branch | Source and regression tests added; current code/test candidate `dcec2490057be63ad366a9aa4eda4c15a679a898` |
| Repository-verified | Pending | Must pass all required exact-head CI jobs on the latest PR head |
| Staging-verified | Pending | Full operated cancellation/recovery matrix not run by this change |
| Production-qualified | No | Requires release-bound operated evidence and independent review |
| Activated | No | No activation authorized or performed |

- Test pass/fail/skip counts: failing-first run 2 failed, 1407 passed; post-fix counts pending.
- Exact-head CI links: [failing-first run #39059380961](https://github.com/rumman52/Shuddho/actions/runs/39059380961); the post-fix final-head run must be recorded after this correction.
- Review findings and resolution: failing-first behavior reproduced; independent review and final-head review pending.
- Residual risks: a successful unit/CI run does not prove operated Temporal process interruption, staging qualification, or production safety.
- Next exact action: inspect all three required CI jobs on the final PR head; repair concrete failures without weakening assertions; then obtain independent review and run the authorized operated cancellation/recovery qualification matrix.
