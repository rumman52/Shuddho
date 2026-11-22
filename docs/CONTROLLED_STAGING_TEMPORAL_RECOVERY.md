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
SHUDDHO_SOURCE_REVISION=<full-40-character-deployed-git-sha>
```

## Phase 1 — prepare

Run:

```bash
uv run --extra coworker python scripts/staging_temporal_recovery.py prepare \
  --state /secure/path/temporal-recovery-state.json \
  --rollout /secure/release/cohort-rollout.json
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

No customer content is used. The prepare phase also captures the pre-restart registered worker ID; it refuses to create the run if exactly one matching live poller is not available.

## Phase 2 — observe the active child, then replace the worker

The `prepare` receipt captures a worker registration **before** the AgentRun
starts. Its heartbeat can legitimately become older than the worker registry's
15-second TTL while the real research child executes. Do not invent a newer
timestamp or loosen the TTL. Just **before** triggering the authorized platform
restart, record a new, read-only, protected checkpoint:

```bash
uv run --extra coworker python scripts/staging_temporal_recovery.py checkpoint \
  --state /secure/path/temporal-recovery-state.json \
  --rollout /secure/release/cohort-rollout.json \
  --output /secure/path/temporal-pre-restart-checkpoint.json
```

This refuses to publish a checkpoint unless the same source-SHA worker
registration remains the only fresh poller, the original worker ID and
registration are unchanged, and a real, owned child `cw_tasks` row plus
its `cw_agent_steps` row are currently running in the original AgentRun.
It writes an immutable new 0600 file without overwriting the prepare
receipt. The checkpoint carries only IDs, times, the approved release context
and the old worker heartbeat, not credentials, customer content or object keys.

**Immediately after this readback**, replace or restart the staging Coworker
worker through the actual authorized deployment platform. The recorded
platform restart time must follow the checkpoint, the old heartbeat must
still be within the real 15-second worker TTL, and the same checkpointed child
must be active at interruption. A checkpoint is not a platform restart or
approval for provisioning; reviewer D independently corroborates both.
If a phase has already finished or more than 15 seconds elapsed, create
a fresh, new observed checkpoint while another child is genuinely running,
rather than modifying an existing protected receipt.

Record:

- the exact restart/deployment timestamp;
- a durable platform reference such as deployment ID, pod UID transition, service event, or run ID.

The verifier rejects a restart timestamp that occurred before Agent execution actually started.

The old initial prepare snapshot remains a supported fast-exercise fallback
when the restart truly happens within its 15-second heartbeat freshness
window. For real longer-running hosted tasks, supply the separate
`--checkpoint` receipt; the verifier binds its recorded original worker ID,
release, run, active child ID, captured timestamp and fresh heartbeat to
the actual restart and the DB-confirmed completed child window.

The pre-restart worker identity and heartbeat are captured by `prepare`.
That heartbeat must still be fresh **at the actual platform restart**, using
the same 15-second `WORKER_HEARTBEAT_TTL_SECONDS` as the persisted
`worker_inventory`, and it must not be future-dated. The old worker must
have registered before the Agent child execution began. A delayed operator
restart **must not** reuse a stale prepare snapshot to claim active-worker
interruption. If the old-worker heartbeat has aged beyond this boundary,
the exercise fails closed; re-run a fresh approved synthetic recovery
exercise rather than edit timestamps or backdate the restart event.
Independent reviewer D still checks the actual host/Temporal event history.

## Phase 3 — verify

After the run completes:

```bash
uv run --extra coworker python scripts/staging_temporal_recovery.py verify \
  --state /secure/path/temporal-recovery-state.json \
  --restart-at 2026-09-22T08:30:00+06:00 \
  --restart-reference render-deploy-12345 \
  --checkpoint /secure/path/temporal-pre-restart-checkpoint.json \
  --rollout /secure/release/cohort-rollout.json \
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
- exactly one fresh, reviewed-SHA worker is registered on the target queue before the run;
- a distinct replacement worker registers **while the same Agent run is active**, near the actual platform restart timestamp, advances its heartbeat and remains the only fresh poller on the queue;
- the recovered AgentRun has exactly **one delivered `cw_agent_outbox` ledger row**;
- the three child tasks use the real AgentRuntime direct Temporal execution path (`enqueue=False`), so **zero** `cw_outbox` rows exist for those child tasks (no duplicate dispatch path);
- exactly three child tasks exist for the Agent run;
- each child task maps to one distinct Agent step;
- child task idempotency keys are exactly `agent:{run_id}:1..3`;
- the recorded worker replacement occurred after Agent execution started and before the recovery run finished;
- a non-empty deployment/restart evidence reference is supplied.

The verifier includes a redacted `recovery_outbox` receipt with run/workflow IDs, one parent outbox effect, zero child task outboxes, before/after worker IDs, heartbeat-backed replacement timing and the real platform restart reference. The Day 2 reconciliation now requires that receipt and the exact same receipt to be carried into restored evidence. This proves one *logical AgentRun dispatch effect* in the durable database; it does not independently prove that a third-party provider never executed a retried side effect.

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


The `temporal`, `parallel_restart`, and `fan_in` records bind their verification timestamp, release ID, deployed source revision, and exact rollout-manifest SHA-256.
