# Part 3 Reliability, Evaluation and Production Qualification — Implementation Plan

> **Execution:** Native implementation on the isolated GitHub branch `codex/part3-reliability-qualification-20261109`. All work lands in one PR. Follow test-first sequencing and verify the exact final PR head.

**Goal:** Complete the repository-level reliability/evaluation/observability work for Part 3 while keeping staging and production unchanged.

**Design:** `docs/superpowers/specs/2026-11-09-part3-reliability-qualification-design.md`

## Global constraints

- Base: `1288ccf88ead3e63cfca45beeaf49777a58f3e14`.
- Preserve existing API contracts and v1/v2/v3 runtime compatibility.
- No live database migration, staging/production deploy, worker provisioning, provider mutation, PostHog ingestion, feature-flag change, or production activation.
- Live model evaluation remains opt-in/manual and must require an exact rollout, full source revision, synthetic fixtures, positive cost rate, and bounded total token/cost budgets.
- Never weaken browser assertions, required CI jobs, security gates, owner isolation, approval rules, or zero-tolerance metrics.
- Report unavailable external evidence as blocked, not passed.

## Task 1 — Repair the Writing Assistant browser regression

**Files:** `apps/web-editor/test/coworker-browser.mjs`

- [ ] Add assertions for Documents-first route state immediately after navigating to Writing Assistant.
- [ ] Assert the New document action is visible and the editor canvas is not visible before user action.
- [ ] Remove the stale initial wait for the hidden editor subtitle and the invalid back-to-documents click.
- [ ] Preserve document dashboard geometry checks, explicit New document click, editor geometry checks and mobile review-panel checks.
- [ ] Verify the browser workflow on the PR head.

## Task 2 — Expand live model evaluation without paid CI calls

**Files:** `scripts/agent_eval.py`, `tests/test_agent_eval.py`, `tests/fixtures/agent_eval_cases.jsonl`, `docs/PART_3_AGENT_EVAL_STAGING_GATES.md`

- [ ] Add failing unit tests for 3-step planning, no-tool/unsupported decisions, forbidden consequential tools, context grounding and memory-source bounds.
- [ ] Generalize `evaluate_live_v3` to iterate over every expected tool step, synthesize only explicit completed observations, then require a final `complete` decision.
- [ ] Support no-tool cases with a bounded set of accepted safe decisions; reject any unexpected selected tool.
- [ ] Check every model-selected tool against both the server-provided tool set and fixture forbidden tools.
- [ ] Pass synthetic context only when the fixture declares it; check required objective facts, forbidden prompt-injection strings, and memory proposal source IDs.
- [ ] Record per-case model, decisions, prompt/tool-schema hashes, tokens and latency; aggregate total tokens, p50/p95/p99 latency, cost estimate and pass rate.
- [ ] Fail closed when the configured live-evaluation token/cost budget is exceeded or a positive cost rate is absent.
- [ ] Keep live calls out of ordinary CI; CI runs deterministic/offline tests only.

## Task 3 — Persist planner latency and complete observability economics

**Files:** `services/coworker/models.py`, `services/coworker/migrations/versions/0066_agent_decision_latency.py`, `services/coworker/agent_runtime.py`, `services/coworker/agent_repository.py`, `scripts/core_agent_observability.py`, `tests/test_core_agent_observability.py`

- [ ] Add tests that demonstrate planner latency is persisted and exported; add tests for missing cost-rate behavior and retry-rate calculation.
- [ ] Add nullable `AgentDecision.latency_ms`; migration 0066 adds/drops only that column and follows revision 0065.
- [ ] Capture the measured planner latency returned by `DeepSeekAgentPlanner.decide` and persist it with the committed decision.
- [ ] Combine successful planner decision latency with existing child `ModelAttempt.latency_ms`; expose samples and p50/p95/p99, plus explicit coverage/scope.
- [ ] Add tool latency p50/p95/p99 and retry attempt rate to aggregate dashboard metrics.
- [ ] Treat zero/unknown configured pricing as unavailable; never report an unpriced nonzero token volume as $0.
- [ ] Preserve label-free OpenMetrics and atomic export writes.
- [ ] Add regression checks for NaN/unavailable values and absence of user/run labels.

## Task 4 — CI evidence and regression qualification

**Files:** `.github/workflows/ci.yml`, `docs/CORE_AGENT_PHASE9_EVALUATION_SYSTEM.md`, `docs/CORE_AGENT_PHASE10_OBSERVABILITY_ECONOMICS.md`

- [ ] Preserve the existing deterministic Phase 9 gate and all mandatory CI jobs.
- [ ] Write the deterministic Phase 9 result to a machine-readable artifact bound to the workflow commit.
- [ ] Upload the report even when the evaluation step fails, without adding paid provider calls.
- [ ] Verify the browser job retains real Chromium and existing product-level assertions.
- [ ] Keep governance audit fail-closed; record the branch-protection administrator dependency rather than bypassing it.

## Task 5 — Staging preflight, documentation and release acceptance

**Files:** `docs/CORE_AGENT_PART3_RELIABILITY_QUALIFICATION_2026-11-09.md`, `docs/coworker-roadmap/CORE_AGENT_COMPLETION_LEDGER.md`, `docs/coworker-roadmap/ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md`, `docs/PART_3_AGENT_EVAL_STAGING_GATES.md`

- [ ] Record exact source/CI evidence and distinguish offline, live-model, Temporal test-server, staging and production evidence.
- [ ] Document the manual live planner/quality/runtime qualification commands and their budget prerequisites.
- [ ] Record the current staging blockers: expired/suspended database continuity, stale staging API, missing persistent worker, and missing verified Temporal/private-storage/identity credentials.
- [ ] Document monitoring/alert verification as pending until a real metrics receiver and alert destination are authorized and observed.
- [ ] Document rollback for migration 0066 and the source release.
- [ ] Record the governance failure and administrator-only no-bypass branch-protection action.
- [ ] Do not mark the PR as staging-qualified or production-ready.

## Task 6 — Final verification and review

- [ ] Run focused Python tests for Agent evaluation and observability.
- [ ] Run migration/static compatibility checks.
- [ ] Run the full Coworker Python test gate with required integrations and zero skips.
- [ ] Run frontend tests/builds and the real Chromium Coworker browser workflow.
- [ ] Run the complete deterministic Phase 9 suite (minimum 300 scenarios).
- [ ] Inspect all changed files and the exact PR diff for secrets, user-derived labels, accidental live endpoints, deployment triggers and weakening of safety assertions.
- [ ] Re-run CI on the final PR head; capture every job conclusion.
- [ ] Record independent review and all remaining owner/operator actions without fabricating approval or staging evidence.

## Completion rule

This PR can complete repository implementation and CI qualification only. Live-model thresholds, staging operation, monitoring ingestion/alerts, backup/restore, independent security/operations review, branch protection and production release acceptance remain separate evidence gates until actually executed by authorized operators.
