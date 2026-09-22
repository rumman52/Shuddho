# Controlled Staging Temporal Recovery Exercise

This exercise verifies the production Temporal recovery contract for AgentWorkflow v2 with real staging persistence and a deliberate Coworker worker replacement.

It does not enable Coworker for general production traffic.

## Preconditions

Use an isolated staging environment with:

- managed staging identity and PostgreSQL;
- private object storage;
- production-equivalent Temporal TLS connection;
- `SHUDDHO_AGENT_RUNTIME_ENABLED=true`;
- `SHUDDHO_AGENT_DEPENDENCY_GRAPH_ENABLED=true`;
- `SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=true`;
- `SHUDDHO_RESEARCH_SERVICES_ENABLED=true`;
- `SHUDDHO_WORK_SERVICES_ENABLED=true`;
- `SHUDDHO_AGENT_MAX_PARALLEL_STEPS>=2`;
- backend-only Tavily and model credentials;
- one disposable staging account token in `SHUDDHO_STAGING_TOKEN_A`.

Set this explicit operator guard only for the exercise:

```bash
SHUDDHO_STAGING_ALLOW_RECOVERY_EXERCISE=true
```

## Phase 1 — prepare

Run:

```bash
uv run --extra coworker python scripts/staging_temporal_recovery.py prepare \
  --state /secure/path/temporal-recovery-state.json
```

The script:

1. resolves the disposable staging account through the deployed API;
2. creates a synthetic Agent run directly in the staging ledger;
3. persists exactly three bounded steps:
   - research branch A;
   - research branch B;
   - document fan-in depending on both branches;
4. starts `shuddho_agent_run_v2` in the configured Temporal namespace;
5. writes only run/workflow identifiers and timestamps to the state file.

No customer content is used.

## Phase 2 — replace the worker

While the run is active, replace or restart the staging Coworker worker using the real deployment platform.

Record:

- the exact restart/deployment timestamp;
- a durable platform reference such as deployment ID, pod UID transition, service event, or run ID.

The verifier rejects a restart timestamp that occurred before Agent execution actually started.

## Phase 3 — verify

After the run completes:

```bash
uv run --extra coworker python scripts/staging_temporal_recovery.py verify \
  --state /secure/path/temporal-recovery-state.json \
  --restart-at 2026-09-22T08:30:00+06:00 \
  --restart-reference render-deploy-12345 \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.recovery.json
```

The verifier promotes `temporal`, `parallel_restart`, and `fan_in` to `passed` only when all of these hold:

- Temporal reports the workflow completed;
- the Agent run completed;
- exactly three persisted Agent steps exist;
- persisted dependencies remain `[], [], [1,2]`;
- every step has start/finish timing evidence;
- step 3 started only after both research branches finished;
- exactly three child tasks exist for the Agent run;
- each child task maps to one distinct Agent step;
- child task idempotency keys are exactly `agent:{run_id}:1..3`;
- the recorded worker replacement occurred after Agent execution started and before the recovery run finished;
- a non-empty deployment/restart evidence reference is supplied.

## What this proves

A passing exercise provides staging evidence that:

- the production Temporal namespace and worker deployment can survive a real worker replacement;
- AgentWorkflow v2 resumes from persisted checkpoints;
- fan-out branches do not create duplicate child tasks after recovery;
- fan-in remains blocked until both persisted dependencies complete.

It does not prove backup/restore, deletion/retention, provider approval safety, or global production scale.

## Failure handling

If prepare or verify fails, do not manually mark these gates as passed.

Retain the run ID, workflow ID, platform restart reference, and sanitized deployment logs for diagnosis. Never add JWTs, database URLs, provider credentials, source text, model reasoning, or object keys to the evidence file.
