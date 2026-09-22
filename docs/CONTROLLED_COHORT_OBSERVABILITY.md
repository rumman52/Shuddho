# Controlled Cohort Observability Export

This increment turns the controlled-cohort health decision into artifacts that standard operations tooling can consume without adding a public metrics endpoint or a second release-control implementation.

It reuses the exact snapshot and STOP/CONTINUE evaluator from `scripts/cohort_health_gate.py`.

## Outputs

The exporter writes two files atomically:

1. **OpenMetrics/Prometheus text format** for a textfile collector or equivalent.
2. **Operator JSON status** for incident automation, dashboards or change-ticket attachment.

It intentionally emits no account IDs, subjects, prompts, documents, file names, email/calendar content, OAuth data, raw provider responses or model text.

## Run

```bash
uv run --extra coworker python scripts/cohort_observability_export.py \
  --rollout /secure/path/cohort-rollout.json \
  --thresholds /secure/path/cohort-health-thresholds.json \
  --prom-output /var/lib/node_exporter/textfile_collector/shuddho_coworker.prom \
  --status-output /secure/path/shuddho-coworker-status.json
```

The process exits non-zero when the shared evaluator returns `STOP_ROLLOUT`. Files are still written first so the monitoring system sees the STOP state and breach count.

## Exported metric families

The text export includes stable, low-cardinality numeric metrics for:

- continue/stop state and breach count;
- snapshot timestamp and observation window;
- configured cohort member count;
- active tasks, Agent runs and provider actions;
- oldest active work age;
- task samples/completions/failures/needs-input and success/failure ratios;
- model attempt samples, failed/unknown count, failure ratio, p95 latency, conservative token accounting and in-flight reservations;
- Agent samples/failures/failure ratio;
- Research samples/failures/failure ratio;
- consequential action samples/failures/unknown outcomes/failure ratio;
- aggregate cohort storage bytes.

When a ratio has no measured samples, the metric value is `NaN` rather than inventing a healthy zero.

The metrics intentionally contain **no labels**. This keeps cardinality fixed and prevents release IDs or user-derived values from leaking into the metrics surface. Release identity belongs in the operator JSON and deployment metadata.

## Suggested alerts

For the first cohort, alert at minimum on:

- `shuddho_coworker_cohort_stop == 1`;
- `shuddho_coworker_cohort_breaches > 0`;
- exporter/scheduler failure or stale snapshot timestamp.

The detailed threshold comparisons still live in one place: `cohort_health_gate.py`. Do not duplicate them as slightly different alert rules.

## Collection model

A recommended deployment is an external scheduler every five minutes:

1. run the exporter using read-only application database access;
2. let a node-exporter textfile collector or equivalent scrape the `.prom` file;
3. archive the small JSON status with the release/change record;
4. alert operations if the command exits non-zero or the STOP metric becomes 1;
5. operators invoke the manifest's documented kill switches through the deployment platform.

The exporter itself never receives deployment-admin credentials.

## Failure behavior

Atomic replacement prevents a scraper from reading a partially written metrics file.

If snapshot collection fails entirely, the previous metrics file may remain on disk. Monitoring must therefore alert on a stale `shuddho_coworker_cohort_snapshot_timestamp_seconds` value and on scheduler/exporter execution failure.

A `CONTINUE_COHORT` result is not permission to expand the cohort. Cohort expansion remains a separately reviewed release decision.
