# Adaptive Provider Quota and Cost Policy

PR #151 protects instantaneous model-provider capacity across all Coworker workers. This increment adds the missing aggregate spend boundary and a measured policy compiler.

## Runtime global daily budget

Every draft or intelligent-planner provider lease now reserves tokens against one global UTC-day budget before the external model call starts.

The reservation is serialized by the same PostgreSQL admission lock used for concurrency fairness.

On a known provider result, the global daily allocation is settled from the conservative reservation to actual token usage. On an unknown outcome or worker loss, the full reservation remains charged for that UTC day.

When the global daily ceiling is exhausted, new provider calls fail closed with `provider_daily_budget`. This is a spend boundary, not transient concurrency backpressure.

## Measured policy compiler

Runtime limits are not self-modifying.

Before changing provider limits for a reviewed cohort expansion, compile a proposal from:

- the exact bounded scale decision;
- the exact scale-review request bound by that decision;
- the exact capacity qualification bound by that decision;
- a checked/reviewed policy plan containing pricing and policy constraints.

The compiler considers:

- reviewed projected peak concurrency;
- demonstrated live-provider concurrency;
- actual provider concurrency quota;
- required provider headroom;
- approved monthly budget;
- reviewed estimated monthly cost;
- a conservative budget-utilization ceiling;
- bounded step growth from the currently deployed policy;
- maximum per-workspace shares;
- task/planner reservation ceilings;
- provider timeout plus crash-recovery margin.

The result is either `ELIGIBLE_FOR_POLICY_REVIEW` or `HOLD_CURRENT_POLICY`.

A successful artifact contains exact proposed environment values, but it never changes production itself.

## Pricing input

`blended_token_cost_usd_per_million` is an operator-supplied contract/accounting input. The checked-in template is an example only and is not a claim about current DeepSeek pricing. Use the effective blended rate for the model/account and review it whenever provider pricing changes.

## Run

```bash
uv run python scripts/provider_policy_compiler.py \
  --plan /secure/release/provider-policy-plan.json \
  --scale-decision /secure/release/bounded-scale-decision.json \
  --scale-review /secure/release/cohort-scale-review.json \
  --capacity-qualification /secure/release/capacity-qualification.json \
  --output /secure/release/provider-policy-proposal.json
```

The proposal should be reviewed with the same change process used for cohort expansion. A later activation check must compare the deployed environment to the exact approved proposal before it is treated as production evidence.
