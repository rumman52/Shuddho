# Controlled Cohort Capacity Qualification

The 25-user controlled cohort is an engineering safety ceiling, not evidence that Shuddho is ready for a larger rollout.

Before any proposal to exceed that cohort, Shuddho requires measured capacity evidence from two different test modes plus a fresh healthy production/cohort status.

This gate returns only:

- `ELIGIBLE_FOR_CAPACITY_REVIEW`
- `CAPACITY_NOT_QUALIFIED`

It never changes cohort membership, feature flags, autoscaling configuration, or provider quotas.

## Prerequisite: final canary stage

The supplied canary progression result must be:

```json
{
  "decision": "HOLD",
  "current_stage": "cohort-25",
  "next_stage": null,
  "reasons": ["final_stage_reached"]
}
```

That means the existing 25-user stage has already earned its required healthy windows, observation duration, and real task/provider/Agent sample minimums.

A stage that is merely "running" or has insufficient traffic cannot enter capacity review.

## Two required load reports

### 1. Simulated-provider / infrastructure load

Use a dedicated staging deployment or test environment where model responses are simulated at realistic latency/error distributions.

This report is intended to measure Shuddho-controlled infrastructure:

- authenticated API submission latency;
- PostgreSQL concurrency/backpressure;
- outbox/dispatcher throughput;
- Temporal scheduling;
- worker throughput;
- artifact generation/storage;
- queue growth and drain behavior.

Do not point this test at customer data.

### 2. Budgeted live-provider load

Run a much smaller, explicitly budgeted end-to-end test using real DeepSeek provider calls and synthetic non-sensitive prompts.

This report measures what simulated provider load cannot establish:

- actual model/provider failure behavior;
- real provider p95 latency;
- end-to-end task completion latency;
- actual accounted token use;
- provider/account-level capacity behavior.

Set provider spend alerts/limits before running it.

## Report schema

Both reports use the same schema. The `kind` field is either `simulated` or `live_provider`.

Required fields include:

- release ID and generated timestamp;
- test duration;
- distinct staging accounts;
- offered concurrency;
- submitted/completed/failed/rejected tasks;
- submission p95/p99;
- completion p95/p99;
- maximum queue age;
- provider sample/failure counts;
- provider p95 latency;
- total accounted tokens.

Examples:

- `docs/cohort-capacity-simulated-report.example.json`
- `docs/cohort-capacity-live-report.example.json`

The gate validates report arithmetic and schema before evaluating thresholds.

## Reserve capacity

The checked-in first review plan uses:

```
expected_peak_concurrency = 10
min_reserve_ratio = 1.5
```

Therefore both reports must demonstrate at least 15 offered concurrent tasks.

This is an initial review assumption, not a claim that 10 concurrent model calls are Shuddho's production peak. Replace it with observed demand before relying on the result for a larger rollout.

## Initial qualification thresholds

The template currently requires, among other controls:

**Simulated/infrastructure**
- at least 10 distinct synthetic accounts;
- at least 200 tasks;
- ≥99% completion success;
- ≤1% rejection;
- submission p95 ≤500 ms and p99 ≤1 s;
- completion p95 ≤15 s and p99 ≤30 s under the simulated model;
- max queue age ≤30 s.

**Live provider**
- at least 5 staging accounts;
- at least 20 real-provider tasks;
- ≥95% completion success;
- ≤5% rejection;
- completion p95 ≤120 s and p99 ≤180 s;
- provider failure rate ≤5%;
- provider p95 ≤90 s;
- average accounted tokens ≤20,000 per completed task.

These are conservative starting thresholds and must be reviewed against real product expectations and provider contracts.

## Fresh health after the load

Both load reports must be fresh, and the operator status supplied to the gate must be generated **after both reports**.

That status must still be:

- `CONTINUE_COHORT`;
- zero breaches.

This prevents a load test from "passing" while leaving the actual cohort unhealthy afterward.

## Run

```bash
uv run python scripts/cohort_capacity_qualification.py \
  --plan docs/cohort-capacity-plan.template.json \
  --progression /secure/release/cohort-25-progression.json \
  --simulated-report /secure/capacity/simulated.json \
  --live-report /secure/capacity/live-provider.json \
  --operator-status /secure/release/post-capacity-status.json \
  --output /secure/release/capacity-qualification.json
```

A successful output means only that the measured evidence is eligible for human capacity review.

It is **not** authorization to:
- exceed 25 users;
- increase provider spend;
- add regions;
- claim billion-user scale;
- remove backpressure or rate limits.

## Next review

After qualification, capacity review should decide the next bounded stage from measured demand, cost, provider quota, error budget and operational staffing.

Do not hard-code a 25 → 100 or 25 → 1000 expansion before those measurements exist.


## Dynamic post-scale requalification

The original qualification path starts after the fixed `cohort-25` canary reaches `final_stage_reached`.

After a schema-v4 bounded expansion has been deployed and verified, later stages are not added to the original 5 → 10 → 25 canary plan. Instead, run [post-scale cohort observation](POST_SCALE_COHORT_OBSERVATION.md).

When that gate returns `ELIGIBLE_FOR_REQUALIFICATION`, set this capacity plan's `final_stage` to the exact dynamic stage name and use the post-scale observation artifact as the progression input.

The same simulated and live-provider capacity thresholds then apply again. A post-scale HOLD or STOP result cannot enter capacity qualification.
