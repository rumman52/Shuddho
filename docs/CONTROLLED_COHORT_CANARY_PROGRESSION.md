# Controlled Cohort Canary Progression

A single healthy snapshot is not enough to expand a production cohort.

This gate evaluates a directory of sanitized health-decision JSON files produced over time and returns one of:

- `HOLD`
- `ELIGIBLE_FOR_EXPANSION`
- `STOP_ROLLOUT`

It never edits the backend cohort allowlist and never changes deployment flags automatically.

## Default first-cohort progression

The checked-in template uses:

1. **canary-5**
2. **canary-10**
3. **cohort-25**

Each stage has:
- a hard maximum configured member count;
- a minimum number of healthy windows;
- a minimum observation duration;
- minimum task/provider/Agent samples;
- optional Research/action sample minimums.

The final 25-user stage never returns an automatic expansion decision.

## Run

Store each sanitized `cohort_health_gate.py` decision as a separate JSON file in a history directory, then run:

```bash
uv run python scripts/cohort_canary_progression.py \
  --history-dir /secure/path/cohort-health-history \
  --rollout /secure/path/cohort-rollout.json \
  --plan docs/cohort-canary-plan.template.json \
  --current-stage canary-5 \
  --output /secure/path/cohort-progression.json
```

The command exits:
- zero only for `ELIGIBLE_FOR_EXPANSION`;
- non-zero for `HOLD` or `STOP_ROLLOUT`.

## STOP conditions

The progression gate immediately returns `STOP_ROLLOUT` when:

- any relevant health window contains `STOP_ROLLOUT`;
- the latest health decision is stale;
- backend cohort membership exceeds the current stage maximum.

A STOP result carries the rollout manifest's documented rollback controls.

## HOLD conditions

The stage remains `HOLD` when:

- the stage is not sufficiently enrolled;
- too few healthy windows have accumulated;
- observation time is too short;
- health records contain a monitoring gap above the plan limit;
- real task/provider/Agent/Research/action sample counts are below stage requirements;
- the current stage is the final planned stage.

This prevents expansion based only on time passing with little or no real usage.

## Expansion procedure

`ELIGIBLE_FOR_EXPANSION` means an operator may review the evidence and approve the next planned cohort size.

It does not mutate:
- `SHUDDHO_COWORKER_COHORT_ACCOUNT_IDS`;
- `SHUDDHO_COWORKER_COHORT_MAX_USERS`;
- any feature flag.

After human approval:

1. update the approved cohort/change ticket;
2. add only the approved opaque Coworker account IDs;
3. redeploy current API instances;
4. run the cohort-admission staging/production check;
5. continue collecting health windows at the new stage.

Never skip a stage because the system happens to be healthy at a smaller cohort.
