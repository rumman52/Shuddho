# Controlled Cohort Bounded Scale Review

PR #146 proves that the 25-user cohort has measured infrastructure/provider reserve. PR #147 adds objective multilingual output-quality evidence. PA-11 task-economics evidence adds measured per-completed-task cost across the operated resource categories. PA-11 incident/restore evidence adds a fresh release-bound recovery-readiness check over the existing staging restore, Temporal restart/fan-in and rollback exercises. None of these artifacts should automatically expand Shuddho.

This gate turns the human scale review into a machine-checkable, fail-closed artifact.

## Required evidence

The review requires all of the following for the same release:

- a fresh capacity qualification with `ELIGIBLE_FOR_CAPACITY_REVIEW`;
- a fresh **live** Coworker multilingual quality evaluation with `PASS` that binds the exact reviewed rollout SHA-256;
- fresh PA-11 task-economics evidence that binds the same rollout and source revision;
- fresh PA-11 incident/restore evidence that binds the same rollout and source revision, with a fresh underlying recovery exercise;
- a clean operator status generated after capacity, quality, task-economics, and incident/restore evidence;
- a human-proposed next cohort stage and size;
- projected peak concurrency plus provider quota evidence;
- estimated monthly cost plus an approved budget;
- remaining reliability error budget;
- confirmed on-call staffing;
- demand, quota, budget, on-call, and change references.

The gate never edits the cohort allowlist, feature flags, provider quota, budget, or deployment configuration.

## Growth bound

The initial reviewed plan allows a proposed cohort no larger than:

```
current_max_users * max_growth_ratio
```

The checked-in template uses a 2.0 maximum ratio. This is a ceiling, not a recommendation. A smaller human-selected stage is valid when measured demand justifies it.

## Headroom

The initial template requires:

- provider concurrency quota >= projected peak concurrency × 1.25;
- approved monthly budget >= estimated monthly cost × 1.15;
- at least 50% of the defined reliability error budget remaining.

These are release-policy defaults and should be revised from real measurements and provider contracts.

## Run

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

The scale review requires capacity qualification, live quality evaluation, task-economics evidence, and incident/restore evidence to bind the exact supplied rollout manifest. Task economics and incident/restore evidence must also bind the same source revision as live quality evidence. Both the incident/restore compiler timestamp and its underlying exercise completion timestamp must be fresh, so recompiling an old drill cannot refresh recovery readiness. The bounded-scale decision carries the rollout SHA-256 plus the exact task-economics and incident/restore evidence SHA-256 values.

The only successful decision is `ELIGIBLE_FOR_BOUNDED_EXPANSION`. Any policy or evidence failure returns `HOLD_AT_CURRENT_COHORT` or fails closed on invalid evidence.

A passing decision still requires a separate human/deployment change to alter cohort membership. It does not authorize automatic expansion or a global-scale claim.


## Scale activation verification

A passing scale review does not prove the reviewed change was deployed correctly. After the separate deployment change, run [controlled cohort scale activation verification](CONTROLLED_COHORT_SCALE_ACTIVATION.md).

That verifier checks the actual deployed cohort ceiling and membership bounds, re-runs the allowed/denied admission boundary against the deployed API, requires fresh post-deploy health, and produces a SHA-256-bound activation artifact for the release ledger.
