# Core Agent Phase 10 — Observability + Agent Economics

Phase 10 moves the bounded Core Agent from evaluation-only confidence to production-operable economics and reliability controls.

## Scope

This phase records one sanitized operational record per durable Agent run with:

- run ID;
- model/model set;
- conservatively accounted tokens;
- end-to-end run latency;
- successful planner inference latency persisted on each Runtime v3 decision;
- child-model inference latency from model attempts;
- tool-call count and tool latency;
- bounded retry count;
- routing decision and planner mode;
- approval-wait count and duration;
- provider-failure count;
- conservatively accounted model cost;
- completion state;
- duplicate attempts;
- uncertain outcomes;
- abandonment/deadline state.

The export is implemented in `scripts/core_agent_observability.py`. JSON preserves per-run operational records for restricted operator analysis. OpenMetrics deliberately contains no labels, user text, account IDs, prompts, recipients, transaction terms, or other user-derived dimensions.

## Dashboard metrics

The Phase 10 export provides run success ratio, tool failure ratio, model failure ratio, p50/p95/p99 end-to-end run latency, model inference latency and tool execution latency percentiles, latency coverage, retry-attempt rate, average tool steps per run, total token consumption, cost-estimate completeness, duplicate attempts, `outcome_unknown`, abandoned/deadline runs, and provider failures. Planner latency is sourced from persisted `AgentDecision.latency_ms`; child-model latency is sourced from `ModelAttempt.latency_ms`. Failed planner attempts without a persisted latency are excluded from latency percentiles and lower the reported coverage.

Transactions are measured as a separate safety domain: terminal transaction samples, confirmed transactions, failed transactions, and transaction `outcome_unknown` count/ratio. An uncertain transaction remains a reconciliation event and is never transformed into an automatic retry.

## Per-run production budgets

| Policy | Environment variable | Default |
| --- | --- | ---: |
| Max model calls/run | `SHUDDHO_AGENT_MAX_MODEL_CALLS_PER_RUN` | 12 |
| Max tokens/run | `SHUDDHO_AGENT_MAX_TOKENS_PER_RUN` | 250000 |
| Max tool calls/run | `SHUDDHO_AGENT_MAX_TOOL_CALLS_PER_RUN` | 8 |
| Max runtime | `SHUDDHO_AGENT_RUN_TIMEOUT_SECONDS` | 1800s |
| Max cost/run | `SHUDDHO_AGENT_MAX_COST_MICROUSD_PER_RUN` | 1000000 µUSD |

The model-call and token ceilings span both planner calls and model attempts made by child tasks. Reservations lock the durable Agent run before accounting, so concurrent planner/task calls cannot race past a per-run limit.

The cost ceiling uses the deployment-reviewed `SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS` rate. Unknown or failed calls retain conservative token reservations for economics accounting. The exporter reports a cost estimate from this configured blended effective rate, not a provider invoice. If nonzero token usage has no positive reviewed rate, the per-run and aggregate cost are unavailable (`NaN` in OpenMetrics), never fabricated as zero. Production must set and review the effective rate before enabling monetary stop gates.

Budget failures are explicit: `agent_model_call_limit` (429), `agent_token_limit` (429), `agent_step_limit` (429), `agent_deadline` (bounded runtime failure), and `agent_cost_limit` (402). This turns prior router 429 / budget-402 behavior into server-owned policy instead of an incidental provider error.

## Transaction safety

Transactions remain outside ordinary autonomous Agent tool execution. The Phase 9 router sends transaction intent to the Transactions surface, and Phase 10 observes that domain rather than weakening the boundary.

Consequential actions keep exactly one reviewed execution attempt, immutable reviewed terms/preview binding, provider idempotency where supported, no blind retry after an uncertain provider result, and explicit `outcome_unknown` followed by reconciliation or manual verification.

The Core Agent dashboard counts `outcome_unknown` attached actions for Agent runs, while the transaction dashboard reports transaction-domain uncertain outcomes separately.

## Failure classes from production incidents

- **invalid invocation ID** — tool invocation identity remains server-created and bound to one persisted step; clients/models do not supply executable invocation IDs.
- **TokenLimitExceededError** — planner and child-task usage now share a total per-run token ceiling in addition to existing per-call/task/daily limits.
- **router/provider 429** — call, token, tool and provider capacity limits remain explicit bounded failures and are visible in failure metrics.
- **AgentRouter 402 budget** — the per-run monetary ceiling fails before another provider reservation with `agent_cost_limit`.
- **unknown provider outcome** — conservative accounting is retained and consequential work is not blindly repeated.

## Export

Example operator command:

    uv run --extra coworker python -m scripts.core_agent_observability \
      --window-minutes 60 \
      --json-output /var/lib/shuddho/ops/core-agent.json \
      --prom-output /var/lib/shuddho/ops/core-agent.prom

The JSON file is restricted operator evidence because it contains run IDs. The Prometheus/OpenMetrics file is intentionally label-free and safe for the existing metrics collection path.

## Release evidence

Phase 10 is code-complete only when repository tests for budget enforcement and observability pass, the permanent Phase 9 evaluation suite passes, staging exports contain real Agent and Transaction samples, every `outcome_unknown` has explicit reconciliation evidence, production pricing metadata is reviewed/non-zero before monetary gating, and no CI failure is hidden by an external deployment quota/rate-limit issue.

The previous Phase 9 PR had a CI invocation defect: the evaluation file imported `scripts.*` while CI executed it as a file. Phase 10 changes the CI command to `python -m scripts.core_agent_eval_suite`, preserving the repository root on the module import path.


## Added inference and execution telemetry

Migration `0067` adds nullable `cw_agent_decisions.latency_ms`. It is nullable so pre-migration decisions remain readable. Runtime v3 persists the measured provider round-trip latency returned by the planner. The operator exporter combines those successful planner samples with child `ModelAttempt.latency_ms` samples and reports p50/p95/p99 plus coverage. Tool latency is independently reported at p50/p95/p99.

Retry rate is defined as retry attempts divided by model calls plus tool calls in the selected window. The denominator and numerator are emitted as aggregate counts/rates; no per-user or per-run labels are added.

## Monitoring and concurrent-load evidence

The exporter and label-free OpenMetrics contract are repository-verified by tests. Metrics receiver ingestion, dashboard panels, alert delivery, threshold calibration and concurrent workload measurements require an operated staging environment and owner-approved SLO/alert thresholds. They are not claimed as verified by this source change.


## Day 8 measured-cost comparison and configuration freeze (development evidence only)

This uses the existing exporter, pilot evaluator and DeepSeek provider. It introduces
no new router, provider, connector, PostHog SDK or agent framework. No model
settings are changed without bounded, quality-preserving evaluation.

### Evidence capture

The normal observability export remains available:

    uv run --extra coworker python -m scripts.core_agent_observability \
      --window-minutes 1440 \
      --json-output /var/lib/shuddho/ops/core-agent.json \
      --prom-output /var/lib/shuddho/ops/core-agent.prom

Create operator report directories with mode 0700 and retain JSON locally behind
access control. OpenMetrics remains label-free. The exporter now distinguishes
aggregate/reserved usage from input/output token counts, which are null when not
persisted. Runtime completion does not automatically verify artifacts or
human-accepted outcomes; unverified references stay empty.

The two Day 8 reports must contain exactly the 40 frozen development task IDs
with matching workflow/language and the same provider, model, model-parameter
hash, and tool-surface hash. Baseline and bounded-context/compact-observation
behavior and prompt hashes may differ. Do not evaluate a stronger reasoning
model without approved provider capability and funded budget.

Required report fields:

- Schema: schema_version=1, split=development, exact suite_id,
  source_revision and case_file_sha256 from the existing pilot suite.
- Receipt evidence: generation_identity_verified and
  receipts_independently_verified are explicit booleans; report-level
  provider_usage_receipt_sha256 and review_ledger_sha256 refer to independently
  retained original receipts. Hashes alone do not establish verification.
- Configuration: profile is baseline or bounded_context_compact_observations,
  provider is deepseek, model is the approved actual name, and full lowercase
  model_settings_sha256, behavior_sha256, prompt_sha256 and tool_sha256 are set.
- Each task result includes id, workflow, language, reviewed booleans
  passed/human_accepted/safety_passed, measured input_tokens, output_tokens,
  model_time_ms, tool_time_ms, retry_count and cost_microusd, or null when a
  measurement is unavailable. Include verified_artifact_refs and
  accepted_outcome_ref for accepted results. Do not replace unknown or
  reserved usage with zero or substitute unsupported pricing estimates.

Run the comparison only with independently retained, authorized evidence:

    uv run --extra coworker python -m scripts.core_agent_observability \
      --day8-baseline /var/lib/shuddho/ops/day8-baseline.json \
      --day8-candidate /var/lib/shuddho/ops/day8-bounded.json \
      --day8-report /var/lib/shuddho/ops/day8-comparison.json

The comparison requires at least 36/40 accepted development outcomes, 9/10 in
each research/report-email x Bangla/English cell, no safety violation, artifact
references, retained quality against baseline, and complete measured usage,
cost, model/tool times and retries plus independently verified receipts.
It selects the least costly eligible profile (baseline wins an exact tie).
BLOCKED means no freeze; unknown cost never becomes zero savings.
FROZEN_FOR_DAY9 records configuration, evidence, corpus and current source
hashes; promotion_authorized remains false. Holdout and production are not
qualified by this development-only comparison.

### Operational evidence outside the code slice

The second natural Day 7 briefing occurrence must be proven against actual
owner-scoped occurrence/run/notification records. Check distinct occurrence
keys, exactly one use of the new authorized document version, absence of old
version reuse or duplicate delivery, and the artifact receipts. Synthetic
replay alone cannot establish that a second natural occurrence happened.

Until the correct PostHog project, sanitized payload, consent/privacy scope,
retention/region and a genuinely ingested test event are verified, PostHog is
INCOMPLETE. Keep the operator JSON report access controlled and local. Never
emit raw prompts, documents, owner IDs, source IDs, review receipts or
unapproved telemetry to PostHog.
