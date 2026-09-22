# Controlled Cohort Health and Stop Gate

After a cohort receives `GO_CONTROLLED_COHORT`, Shuddho still needs an operational decision loop. This gate reads durable Coworker state and returns either:

- `CONTINUE_COHORT`
- `STOP_ROLLOUT`

It does **not** mutate deployment configuration itself. A STOP result is designed for a scheduler/alert pipeline and an operator using the already documented kill switches.

## Inputs

Use the approved rollout manifest plus a reviewed threshold file:

- `docs/cohort-rollout.template.json`
- `docs/cohort-health-thresholds.template.json`

Run:

```bash
uv run --extra coworker python scripts/cohort_health_gate.py \
  --rollout /secure/path/cohort-rollout.json \
  --thresholds /secure/path/cohort-health-thresholds.json \
  --snapshot-output /secure/path/cohort-health-snapshot.json \
  --output /secure/path/cohort-health-decision.json
```

The command exits non-zero on `STOP_ROLLOUT`.

## Durable signals

The snapshot is aggregated only across the configured backend cohort account IDs.

It contains no prompts, source text, email bodies, calendar content, OAuth tokens or per-user identities.

It measures:

- number of configured cohort members;
- active task/Agent/action counts;
- age of the oldest active work item;
- task completion/failure/needs-input outcomes in the time window;
- DeepSeek/model attempt failure or unknown-outcome rate;
- model p95 latency;
- model tokens charged in the window;
- Agent run failure rate;
- Research task failure rate when Research is enabled;
- consequential-action failure/unknown rate when actions are enabled;
- count of `outcome_unknown` actions;
- total Coworker storage bytes held by cohort accounts.

## Default first-cohort stop thresholds

The checked-in template is deliberately conservative and is not a universal SLO.

Notable defaults:

- active work older than 5 minutes → STOP;
- task failure rate >20% after at least 5 measured tasks → STOP;
- model/provider failed-or-unknown rate >10% after at least 5 attempts → STOP;
- model p95 >90 seconds after at least 5 attempts → STOP;
- more than 250k model tokens in a 15-minute window → STOP;
- Agent failure rate >20% after at least 3 terminal runs → STOP;
- Research failure rate >20% after at least 3 Research tasks when enabled → STOP;
- any consequential action with `outcome_unknown` → STOP;
- consequential-action failure/unknown rate >10% when actions are enabled → STOP;
- configured backend cohort larger than the approved rollout manifest → STOP.

Review these thresholds before every cohort expansion. Do not silently relax them in production.

## Why the gate does not auto-disable flags

The application should not possess deployment-admin credentials merely to turn itself off. An automatic in-process flag mutation could create a second control plane, complicate incident recovery, and turn a transient database/query issue into a cascading outage.

Instead:

1. run the health gate from an external scheduler/operations environment;
2. alert on any STOP decision;
3. use the rollout manifest's documented kill switches through the deployment platform;
4. preserve current code/migrations while work drains or is reconciled.

## Suggested cadence

For the initial cohort, run every 5 minutes and retain sanitized decisions/snapshots with the change ticket. The repository does not enforce scheduler frequency.

A healthy result does not justify widening the cohort automatically. Expansion remains a reviewed release decision using observed latency, error, cost, quality and operational load.
