# Post-Scale Cohort Observation

The initial canary path is intentionally fixed at 5 → 10 → 25 users. After PR #148 and PR #149, later stages are chosen from measured demand rather than hard-coded into that original plan.

This gate provides the repeatable observation phase for those dynamically reviewed stages.

## Epoch boundary

The observation epoch starts only after both:

- the scale-activation artifact reports `bounded_expansion_verified`; and
- the tamper-evident release ledger contains the matching schema-v4 `bounded_expansion_verified` entry that SHA-256-binds that exact activation artifact.

Health generated before that boundary cannot count toward the new stage.

## Fail-closed conditions

The gate returns `STOP_ROLLOUT` when:

- any post-activation health decision is `STOP_ROLLOUT`;
- the latest health snapshot is stale;
- configured cohort membership exceeds the reviewed stage ceiling.

It returns `HOLD` when enrollment, healthy windows, observation time, monitoring continuity, or sample counts are insufficient.

It returns `ELIGIBLE_FOR_REQUALIFICATION` only after all post-scale observation requirements are earned.

## Dynamic enrollment

The reviewed stage maximum is read from the verified scale-activation artifact. The observation plan does not hard-code a 40-, 50-, or 100-user stage.

The default plan requires enough enrollment to satisfy both:

```
prior_max_users + 1
ceil(reviewed_stage_max * min_enrollment_ratio)
```

The checked-in starting policy uses a 75% enrollment ratio. This is a review default, not a universal scaling rule.

## Run

```bash
uv run python scripts/cohort_post_scale_observation.py \
  --history-dir /secure/release/cohort-health-history \
  --plan docs/cohort-post-scale-observation-plan.template.json \
  --scale-activation /secure/release/bounded-scale-activation.json \
  --release-ledger /secure/release/coworker-cohort-001.jsonl \
  --output /secure/release/post-scale-observation.json
```

A successful result does not approve another expansion. It only allows the current dynamic stage to enter a new measured capacity/quality requalification cycle.

The capacity qualification gate accepts this result when its `final_stage` is set to the same dynamic stage.
