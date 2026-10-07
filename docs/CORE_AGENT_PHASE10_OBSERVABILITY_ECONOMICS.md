# Core Agent Phase 10 — Observability + Agent Economics

Phase 10 moves the bounded Core Agent from evaluation-only confidence to production-operable economics and reliability controls.

## Scope

This phase records one sanitized operational record per durable Agent run with:

- run ID;
- model/model set;
- conservatively accounted tokens;
- end-to-end run latency;
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

The Phase 10 export provides run success ratio, tool failure ratio, model failure ratio, p50/p95/p99 end-to-end run latency, average tool steps per run, total token consumption, average cost per run, duplicate attempts, `outcome_unknown`, abandoned/deadline runs, and provider failures.

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

The cost ceiling uses the deployment-reviewed `SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS` rate. Unknown or failed calls retain conservative token reservations for economics accounting. Production should set this rate to the reviewed effective model price; a zero rate intentionally reports zero model cost and therefore cannot provide a meaningful monetary stop gate.

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
