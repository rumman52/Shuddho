# CORE-07 — Long-Horizon Workflow Qualification

CORE-07 adds realistic multi-step qualification on top of the existing routing,
tool, Temporal, approval-boundary and Transactions tests.

## Why workflow milestones are separate from tool steps

Shuddho intentionally caps one Agent run at eight tool invocations. CORE-07 does
not weaken that safety limit.

A realistic workflow can still contain more than eight **milestones** because
planning, context acquisition, validation, approval, provider receipt,
reconciliation and final delivery are separate workflow states around the
bounded tool calls.

CORE-07 therefore reports:

- scenario completion rate;
- milestone completion rate;
- completion rate by requested horizon: 2, 5, 10 and 20 steps;
- completion rate by workflow family;
- long-horizon completion rate for 10+ step workflows;
- Transactions completion rate separately.

## Checked-in scenarios

The CI-safe fixture set includes:

- 2-step direct-answer flow;
- 5-step document flow;
- 5-step meeting flow;
- 10-step research flow;
- 20-step email flow;
- 20-step travel transaction flow.

The email and transaction scenarios explicitly require the consequential
sequence:

Prepared Action
-> Immutable Preview
-> Human Approval
-> Execution Gateway
-> Provider Mutation
-> Provider Receipt

A trace fails if provider mutation occurs before human approval.

The transaction scenario additionally requires fresh terms, immutable
transaction binding, receipt validation and reconciliation.

## CI gate

Run:

```bash
uv run --extra coworker python scripts/agent_long_horizon_eval.py \
  --min-scenario-completion-rate 1.0 \
  --min-milestone-completion-rate 1.0 \
  --min-long-horizon-completion-rate 1.0 \
  --min-transaction-completion-rate 1.0
```

CI uses synthetic, checked-in evidence only. It proves:

- route/capability contracts;
- complete 2/5/10/20-step coverage;
- milestone ordering;
- approval-boundary ordering;
- transaction safety ordering;
- no expansion beyond the eight-tool-step Agent ceiling;
- separately reported completion metrics.

CI does **not** claim that a real external provider, live DeepSeek model,
production Temporal namespace, or production user data was exercised.

## Controlled staging

For a release candidate, run the same evaluator with:

```bash
export SHUDDHO_SOURCE_REVISION=<40-character deployed source sha>
uv run --extra coworker python scripts/agent_long_horizon_eval.py \
  --controlled-staging \
  --release-id <reviewed-release-id> \
  --cases /secure/release/agent-long-horizon-observed.jsonl \
  --output /secure/release/agent-long-horizon-evidence.json
```

The observed JSONL must use the same schema as the checked-in synthetic fixture
but must be produced from the controlled-staging runbook/evidence collection for
that exact release.

Do not copy the checked-in CI fixture and label it live evidence.

## Completion-rate policy

The initial controlled-staging threshold is 100% for this small curated set.
Future larger suites may define statistically justified thresholds, but lowering
the threshold is not a substitute for fixing a deterministic failure.

A scenario is counted complete only when all expected milestones complete and
all route, evidence, ordering and safety constraints pass.

Milestone completion and scenario completion are intentionally separate so a
workflow that reaches 19 of 20 states is visible as 95% milestone completion but
0% scenario completion.

## Transactions

Transactions remain a separate authority domain. The 20-step transaction
scenario validates:

- fresh quote/terms;
- transaction binding;
- prepared action;
- immutable preview;
- explicit approval;
- freshness re-check;
- execution gateway;
- provider mutation;
- provider receipt;
- receipt validation;
- reconciliation;
- final confirmation.

CORE-07 adds qualification evidence only. It does not select a shopping/travel
provider, add credentials, enable transaction capability flags, or grant payment
or identity authority.

Shopping checkout and travel booking production activation therefore remains
closed until real providers and controlled-staging qualification evidence exist.

## Release interpretation

Passing CORE-07 CI means the repository's long-horizon workflow contract is
coherent and regression-protected. It is necessary for the 99.2% Core Agent
target but controlled-staging evidence remains required before claiming
production qualification for real provider-backed workflows.
