# Controlled Staging Agent v2 → v1 Rollback Exercise

This gate proves that the bounded parallel Agent runtime can be disabled without rolling back database migrations or removing the v2 workflow definition.

The intended operational rollback is **feature-flag rollback**, not code/schema downgrade.

## What is being proven

Before rollback:

- dependency graph is enabled;
- parallel execution is enabled;
- the real dispatcher records a new Agent run as `shuddho_agent_run_v2`.

After rollback deployment:

- `SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false`;
- Agent Runtime remains enabled;
- workers still register both v1 and v2 workflow classes;
- the previously created v2 execution remains valid/completed;
- the real dispatcher records a newly created Agent run as `shuddho_agent_run_v1`;
- both runs complete against the same durable database schema.

Temporal exposes `WorkflowType` as a built-in visibility field, which is why the exercise verifies the server-recorded workflow type rather than inferring it only from local configuration. citeturn899479search4turn857286search0

## Phase 1 — prepare with v2 enabled

In controlled staging set:

```bash
SHUDDHO_STAGING_ALLOW_ROLLBACK_EXERCISE=true
SHUDDHO_AGENT_RUNTIME_ENABLED=true
SHUDDHO_AGENT_DEPENDENCY_GRAPH_ENABLED=true
SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=true
SHUDDHO_WORK_SERVICES_ENABLED=true
```

Then run:

```bash
uv run --extra coworker python scripts/staging_flag_rollback.py prepare \
  --state /secure/path/agent-rollback-state.json
```

The script creates a synthetic Agent run, pre-validates one safe document task, dispatches it through the real `Dispatcher`, checks Temporal visibility reports `shuddho_agent_run_v2`, and waits for completion.

## Phase 2 — perform the rollback deployment

Change only:

```bash
SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false
```

Deploy matching current code to API/worker instances.

Do **not**:
- drop Agent tables;
- unregister `shuddho_agent_run_v2`;
- roll back migrations;
- disable Agent Runtime unless a broader shutdown is intended.

Record the deployment/service revision reference.

## Phase 3 — verify

Run:

```bash
uv run --extra coworker python scripts/staging_flag_rollback.py verify \
  --state /secure/path/agent-rollback-state.json \
  --rollout-reference deploy-rollback-12345 \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.rollback.json
```

Verification passes only when:

- the same disposable staging account is used;
- the pre-rollback execution still reports workflow type `shuddho_agent_run_v2`;
- the pre-rollback Agent run remains completed;
- the deployed configuration has parallel execution disabled;
- a newly created run is dispatched through the real dispatcher;
- Temporal reports that new execution as `shuddho_agent_run_v1`;
- the new v1 run completes;
- a non-empty rollout/deployment reference is supplied.

Only then is `flag_rollback` promoted to `passed`.

## Roll-forward

Re-enabling parallel execution is the inverse configuration change: set the parallel flag true only after the same current code is deployed everywhere and the normal staging gates remain green. Existing v1 histories remain supported because current workers register both workflow identities.
