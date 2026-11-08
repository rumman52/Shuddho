# Part 3 Reliability, Evaluation and Production Qualification — Design

**Date:** 2026-11-09  
**Base revision:** `1288ccf88ead3e63cfca45beeaf49777a58f3e14`  
**Scope:** One reviewable source-only pull request covering Part 3.1–3.5.

## Goals

1. Preserve the deterministic Phase 9 contract suite while extending the existing opt-in live Runtime v3 planner evaluation to measure multi-step decisions, no-tool/unsupported requests, forbidden consequential tools, and grounded use of authorized context.
2. Persist successful planner inference latency and combine it with existing child-model attempt latency in the Phase 10 operator export. Expose tool/model latency percentiles, retry rate, cost-estimate availability, and explicit metric scope.
3. Fix the confirmed Writing Assistant browser regression by asserting the Documents-first state before opening a document; retain real visibility and layout assertions.
4. Produce exact-revision evaluation artifacts in CI and refresh the engineering acceptance ledger with evidence and unresolved external blockers.
5. Keep staging and production untouched.

## Architecture decisions

- Reuse `scripts/agent_eval.py`, `scripts/core_agent_eval_suite.py`, `scripts/coworker_quality_eval.py`, `scripts/runtime_v3_qualification.py`, and the existing Runtime v3 Temporal tests. Do not create a second planner or a parallel evaluation framework.
- Paid live model evaluations remain explicitly opt-in and outside normal CI. Their inputs remain checked-in synthetic fixtures; live runs must bind the rollout manifest, fixture hash, source revision, configured model, measured tokens and latency, and a positive reviewed cost rate.
- Extend `AgentDecision` with nullable `latency_ms` through additive migration `0066`; older rows remain valid. Capture the latency returned by the planner and persist it with the decision. Child model latency continues to come from `ModelAttempt`.
- Report model cost as an estimate derived from the operator-configured blended effective rate, never as a provider invoice. If the rate is zero or incomplete, report cost as unavailable rather than zero.
- Keep OpenMetrics label-free and free of run IDs, prompts, source text, owner identifiers, provider credentials, and other user-derived dimensions.
- Keep telemetry ingestion, alert installation, branch protection changes, deployments, migrations against hosted databases, provider mutation and feature activation outside this PR.
- A repository pass is not staging qualification. Staging remains blocked until an authorized operator restores durable PostgreSQL, provisions the persistent worker and configures Temporal, private storage, identity and protected secrets.

## Acceptance

- Browser test verifies Writing Assistant Documents landing state, New document transition, editor visibility, and existing desktop/mobile layout checks.
- Live evaluation supports 0–3 expected tools, a final completion decision, forbidden-tool rejection, optional context grounding checks, aggregate token/latency/cost evidence and fail-closed run budgets.
- Unit tests cover multi-step loop sequencing, unsupported/no-tool handling, forbidden tool decisions, context/memory source bounds, cost/latency accounting and migration-compatible null latency.
- Observability exports model/tool p50/p95/p99, retry rate, and honest cost availability while preserving label-free output.
- Required repository CI checks pass on the exact PR head. No staging or production deployment or configuration change occurs.
- The release ledger distinguishes implemented, repository-verified, live-model-evaluated, staging-verified, production-qualified and activated states. No status is upgraded without matching evidence.
