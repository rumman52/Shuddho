# Shared Provider Capacity Governor

Shuddho already enforces per-task and per-workspace daily token budgets. Those controls do not protect the shared DeepSeek account from concurrent bursts across many workspaces or multiple worker replicas.

This increment adds a database-backed provider admission lease shared by document drafting and intelligent Agent planning.

## Guarantees

Before an external DeepSeek call starts, the worker must hold a short-lived provider lease.

Admission checks all four bounds:

- global concurrent provider calls;
- concurrent provider calls per workspace/account;
- global reserved tokens across active calls;
- reserved tokens per workspace/account across active calls.

The lease is inserted in the same database transaction as the existing task/planner budget reservation. PostgreSQL uses one transaction-scoped advisory lock so multiple replicas cannot race past a limit.

A completed, failed, cancelled, or unknown call releases its lease. If a worker process disappears before settlement, the lease expires and is reaped by the next admission or health snapshot.

## Configuration

The initial fail-closed defaults are:

```text
SHUDDHO_PROVIDER_MAX_CONCURRENT_CALLS=8
SHUDDHO_PROVIDER_MAX_CONCURRENT_PER_WORKSPACE=2
SHUDDHO_PROVIDER_MAX_RESERVED_TOKENS=800000
SHUDDHO_PROVIDER_MAX_RESERVED_TOKENS_PER_WORKSPACE=200000
SHUDDHO_PROVIDER_LEASE_SECONDS=120
```

These are safety defaults, not provider-quota claims. Production values must come from measured capacity qualification and the actual provider contract.

The lease duration must exceed the configured model timeout. A lease timeout is crash recovery, not normal scheduling.

## Backpressure semantics

When the shared provider is full, the worker raises `provider_capacity_busy`.

When one workspace reaches its fair-share bound while shared capacity remains, the worker raises `workspace_provider_busy`.

Both are transient backpressure errors. Temporal may retry them. They must not be converted into a permanent task or Agent failure.

Existing per-task, daily-token, active-task, Agent-run, and action quotas remain in force. This governor is an additional shared-capacity boundary, not a replacement.

## Operations

Cohort health snapshots expose only aggregate lease counts, reserved tokens, and oldest lease age. They never expose account IDs.

During rollout, compare provider admission pressure with queue age, provider p95/p99 latency, provider failures, and actual token usage. Increase limits only after measured capacity evidence; adding worker replicas alone does not create provider capacity.
