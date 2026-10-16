# CW-10 — Owner-requested model-generated Python draft (phase 6)

**Baseline:** main `08512aba78d5446c8115adbeafeded8a9e4f33cd`. Merged PR [#428](https://github.com/rumman52/Shuddho/pull/428) had green final-head CI [#38848800194](https://github.com/rumman52/Shuddho/actions/runs/38848800194). Matching merged-main CI [#38850518005](https://github.com/rumman52/Shuddho/actions/runs/38850518005) was in progress at start.

## User-visible behavior

In the existing Agent run code-review panel, the **explicit owner** may request "Generate Python draft for review" when the server advertises that this capability is eligible. It generates a bounded Python 3.11 draft using the configured backend-only DeepSeek provider, stores exactly one *inert* immutable `AgentCodeProposal` snapshot, and displays its source and full SHA-256 for the owner to review. This does **not** call any sandbox, approve the proposal, mount files, grant a tool, enqueue an execution or create an external action.

This closes the missing practical **model-produced-source → persistent owner-inspected proposal** portion, but not autonomous planner initiation, owner notification outside the open workspace, or complete operated approved execution.

## Contract and controls

- `SHUDDHO_MODEL_CODE_PROPOSALS_ENABLED=false` is an independent gate. It requires existing runtime-v3, intelligent planner and sandbox flags if enabled. No rollout or deployment settings are changed in this PR.
- `POST /api/v1/agent-runs/{run_id}/code-proposals/generate` is authenticated and has an explicit 8–110-character idempotency key. The request accepts **no model source, code arguments, tool grant, file content or destination**. It uses the same owner-run lookup and conversation-admission policy as CW-10 review. It **denies** any selected private document, memory, connector source, or attached action before a provider call.
- A replay of the same live key returns the same persisted proposal and **does not** call DeepSeek again. Separate concurrent requests under one key can race on provider calls but the existing SQL uniqueness constraint means at most one proposal persists; account/daily/provider model budgets still apply. Do not claim exactly-once provider inference or zero provider cost on interrupted attempts.
- The server reserves an ordinary `AgentRepository.reserve_planner` call against provider, daily, per-run and cost limits **before** invoking the model, and settles it even on a failure. The model sees only the owner-authored run goal, no attached document bytes, no credentials and no instructions or permissions from retrieved content.
- `DeepSeekAgentPlanner.propose_code` uses a strictly bounded JSON shape `{"source": "..."}`, validates no tool_calls/refusals, response completeness, maximum 4,096 UTF-8 bytes, nonempty source, zero null bytes, and Python syntax. It returns only an untrusted Python draft. The backend computes source SHA-256, canonical timestamps/expiry (≤5 minutes and run deadline), exact current resource limits, `egress_profile=none` and empty private inputs/destinations.
- A **second admission check after inference** (existing `prepare_code_proposal`) validates exact owner/run, current conversation scope, cancellation, expiry and immutable code identity. Cancellation/source withdrawal during the model call fails closed with **no persisted proposal**.
- Model origin uses reserved `model-v1:` idempotency-key namespace. Ordinary owner code POST explicitly rejects that namespace; it is provenance and **not** an execution authorization. Existing human review and independent default-off dispatch stay separate.
- UI reflects `generation_enabled` from the backend list, requires an actual click, holds the idempotency key across an uncertain response, displays the generated draft for exact inspection, and never renders an execute button.
- Files: `config.py`, `agent_planning_model.py`, new `model_code_producer.py`, `agent_repository.py`, `api.py`, web-editor `CodeProposalReview.tsx` + typed `client.ts`, model/API/frontend tests, and canonical checkpoint/inventory. No migration or new table is needed.

## Verification and missing evidence

Required final-head `test-and-build`, mandatory zero-skip `coworker` (including CW-10 provider-mock, owner/scope/race/rollback and migration), and `ci-merge-gate`. The tests must prove disabled-before-provider, ownership and context denial, SHA-bound exact persistence, one-key replay, invalid outputs, cancel-after-provider, unchanged dispatch state, and no client execution path. No paid provider call is part of CI; any actual DeepSeek model quality and prompt-injection review require separate consented staging evaluation.

No independent security or accessibility/browser inspection yet. Actual trusted generated-code dispatch remains prohibited without live worker source revocation, process termination, temporary-file destruction, PostgreSQL concurrency/restart, mixed-version deployment compatibility and isolation qualification. CW-11 reviewed skill lifecycle, CW-09 operated browser tests, and full coworker scenarios remain separate blockers. **Do not merge, deploy or activate without the session's explicit authorization.**
