# Bounded Agent Parallel Execution

This increment adds a new Temporal workflow identity for bounded server-owned fan-out/fan-in while preserving `shuddho_agent_run_v1` for existing and flag-off runs.

## Contract

Parallel execution is active only when both `SHUDDHO_AGENT_DEPENDENCY_GRAPH_ENABLED=true` and `SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=true`.

- New runs are routed to `shuddho_agent_run_v2`; v1 is unchanged.
- `SHUDDHO_AGENT_MAX_PARALLEL_STEPS` defaults to 2 and is hard-bounded to 1-4.
- A readiness activity reads persisted same-run dependency and step state. Temporal never asks the model which durable step IDs are runnable.
- Research steps remain dependency-free source branches. A later non-research task deterministically depends on the immediately preceding research fan-out, creating a persisted fan-in barrier.
- Consequential and approval-required actions are never placed in a parallel batch.
- Completed independent work remains immutable if another branch fails. The run fails before dependent fan-in work can start.
- Outcome replanning is conservatively serialized so the existing completed-prefix/unstarted-suffix invariant remains valid.
- Capability-change replanning is detected by readiness before launching a batch when possible, then replaces only the unstarted suffix.
- The existing eight-step ceiling, owner scoping, token budgets, idempotent child-task keys, handoff isolation, approval semantics, and one-replan limit remain in force.

## Failure and restart behavior

Each child task still uses the idempotency key `agent:{run_id}:{ordinal}`. Temporal activity retries therefore recover the same durable child task and its persisted checkpoints instead of creating duplicate tasks or artifacts.

The v2 workflow waits for every activity in a launched batch to settle. If one branch fails, successful independent branches remain completed, unfinished/dependent steps are marked failed, and no fan-in step is scheduled.

Cancellation remains cooperative through the existing run and child-task cancellation state. Approved actions continue through their existing immutable preview and provider-confirmed receipt path.

## Release gate

Keep both flags disabled by default outside controlled staging until:

- dedicated coworker CI is green;
- a worker restart during two concurrent branches produces no duplicate tasks, model drafts, searches, or artifacts;
- fan-in starts only after all persisted dependencies complete;
- a failed branch prevents its dependent fan-in step while completed independent work remains immutable;
- approved actions are observed to execute serially;
- disabling the parallel flag routes new runs back to v1.

## Deferred

Arbitrary/model-authored DAG edges, cross-run dependencies, speculative execution, unbounded concurrency, multi-agent delegation, and autonomous external actions remain out of scope.
