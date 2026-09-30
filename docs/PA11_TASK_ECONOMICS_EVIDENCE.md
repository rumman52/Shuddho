# PA-11 Task Economics Evidence

This slice closes the PA-11 release-objective gap for measured task economics. It does **not** add runtime billing, change user quotas, enable a capability, or prove live/staging/production qualification by itself.

The accepted Personal Agent plan requires measured model, search, sandbox, render, storage and notification cost per completed task. This evidence path turns reviewed accounting inputs plus real completed-task measurements into a rollout-bound, source-revision-bound artifact for the existing bounded cohort scale review.

## Boundary

Task economics is a **scale-review evidence artifact**.

It does not:

- charge a user or create invoices;
- change model/provider selection;
- change provider, account, sandbox, storage or notification limits;
- enable Artifact Services, Browser Push, Runtime v3, sandbox execution or another feature flag;
- authorize a cohort expansion;
- replace capacity, quality, recovery or operator-health evidence.

The scale-review command requires task-economics evidence only when proposing growth beyond the already-qualified controlled cohort.

## Inputs

Prepare four exact inputs:

1. The reviewed rollout manifest for the release.
2. The reviewed provider-policy plan. Its `blended_token_cost_usd_per_million` remains the single model-pricing input already owned by the provider-policy workflow.
3. A task-economics pricing plan for the remaining resource categories.
4. Metering-only completed-task samples from the exact release revision.

The checked-in pricing template contains example values only. It is **not** a statement of current DeepSeek, search, compute, rendering, storage or notification prices. Replace every rate with the effective reviewed accounting rate for the actual deployment/provider contracts.

All prices are expressed in **micro-USD** (1 USD = 1,000,000 micro-USD). Storage is priced per GiB-hour; sandbox usage is measured in milliseconds and priced per second.

## Sample contract

Each task sample contains only:

- an opaque/redacted task reference;
- task kind and language;
- terminal state `completed`;
- model tokens;
- search credits;
- sandbox milliseconds;
- render operations;
- storage byte-hours;
- notification attempts;
- retry count.

Do not copy task instructions, source text, document contents, notification bodies, prompts, secrets or provider credentials into economics evidence.

The sample set must:

- come from one full 40-character source revision;
- include at least the reviewed minimum number of completed tasks;
- use unique task references;
- cover every cost category at least once across the sample set;
- include retry resource usage in the measured resource totals rather than adding an invented retry surcharge.

A zero value is valid for a category on an individual task. The **set** must still demonstrate non-zero measured use for model, search, sandbox, render, storage and notification categories.

## Compile

Copy and review the templates first:

```bash
cp docs/task-economics-pricing.template.json /secure/release/task-economics-pricing.json
cp docs/task-economics-samples.template.json /secure/release/task-economics-samples.json
```

Compile:

```bash
uv run python scripts/task_economics_evidence.py \
  --rollout /secure/release/cohort-rollout.json \
  --provider-policy-plan /secure/release/provider-policy-plan.json \
  --pricing-plan /secure/release/task-economics-pricing.json \
  --samples /secure/release/task-economics-samples.json \
  --output /secure/release/task-economics-evidence.json
```

The compiler fails closed when:

- release IDs disagree;
- the provider-policy plan is invalid;
- source revision is not a full commit SHA;
- samples are malformed, duplicated, not completed, or too few;
- one of the six required cost categories is absent from the sample set;
- a task exceeds the reviewed per-completed-task budget;
- timestamps are invalid or materially in the future.

A passing artifact records:

- exact rollout/provider-policy/pricing/sample SHA-256 values;
- exact source revision;
- completed sample count and retry count;
- category coverage and aggregate category costs;
- average, p95 and maximum per-task cost;
- the reviewed per-task budget.

## Scale review

The bounded cohort scale review consumes the compiled artifact:

```bash
uv run python scripts/cohort_scale_review.py \
  --plan docs/cohort-scale-review-plan.template.json \
  --review /secure/release/cohort-scale-review.json \
  --rollout /secure/release/cohort-rollout.json \
  --capacity-qualification /secure/release/capacity-qualification.json \
  --quality-eval /secure/release/coworker-quality-eval.json \
  --task-economics /secure/release/task-economics-evidence.json \
  --incident-restore /secure/release/incident-restore-evidence.json \
  --operator-status /secure/release/post-review-operator-status.json \
  --output /secure/release/bounded-scale-decision.json
```

The scale review requires task economics to bind the exact rollout and the same source revision as live quality evidence. Both the compiled economics artifact and its underlying measured sample timestamp must satisfy the scale-review freshness window; recompiling stale samples does not refresh the measurement. It also requires the separate PA-11 incident/restore artifact for the same rollout/source revision and a fresh underlying recovery exercise. The final operator-health snapshot must be generated after capacity, quality, task-economics and incident/restore evidence. The bounded-scale decision binds the exact task-economics and incident/restore artifact SHA-256 values.

The downstream provider-policy compiler must receive that same task-economics artifact and the same reviewed provider-policy plan used for economics measurement. It verifies the decision's task-economics SHA and the economics artifact's `provider_policy_plan_sha256` before producing a policy proposal.

This prevents a cohort expansion decision from relying only on a manually estimated monthly budget while ignoring measured per-task economics.

## Evidence status

Checked-in tests and this compiler prove schema validation, binding and release-control behavior only. They do **not** create real pricing approval, staging samples, live provider measurements or production qualification. Those remain NOT VERIFIED until reviewed real artifacts are produced for a release.
