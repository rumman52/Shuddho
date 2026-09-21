# Bounded Multi-Source Agent Handoffs

This increment extends typed Agent Step Handoffs without introducing a model-selected dependency graph.

## Scope

When both handoff flags are enabled, a later non-research task may receive results from at most the two nearest eligible completed task steps in the same owner/run.

The server selects eligible upstream steps from durable execution order. The planner does not provide dependency IDs.

## Flags and bounds

```text
SHUDDHO_AGENT_HANDOFFS_ENABLED=false
SHUDDHO_AGENT_MULTI_HANDOFFS_ENABLED=false
SHUDDHO_AGENT_HANDOFF_BYTES=12000
SHUDDHO_AGENT_HANDOFF_SOURCES=2
```

The 12 KB value is a shared total byte budget across all handoff sources, not a per-source allowance. The runtime also hard-caps the source count at two even if configuration is larger.

When the multi-handoff flag is off, the PR #115 nearest-prior-source behavior is unchanged.

## Trust and privacy invariants

Each source must be backed by a completed, non-consequential tool invocation, completed receipt and verified task belonging to the same owner, run and step.

Handoff text remains excluded from planner prompts, Temporal workflow payloads/history, web research queries, task notes/tool arguments, Gmail/Calendar previews/approvals, and durable tool receipts. Receipts persist provenance only.

Research steps still receive no generated handoff content. Consequential actions are never handoff sources.

## Why this precedes a dependency graph

This enables useful composition across several completed work products while keeping dependency selection code-owned and ordered. It avoids model-controlled step IDs, arbitrary DAGs, cross-run dependencies, artifact IDs or new permission paths.

## Deferred

Planner-selected dependency edges, arbitrary DAGs/fan-out/fan-in, more than two upstream results, binary artifact ingestion, cross-run/workspace dependencies, model-selected external actions and multi-agent delegation remain deferred.

## Release gate

Keep `SHUDDHO_AGENT_MULTI_HANDOFFS_ENABLED=false` until staging verifies same-owner/run/step checks, the shared multilingual UTF-8 byte ceiling, research/action isolation, provenance ordering and replay, Temporal/receipt privacy, and backward-compatible single-handoff behavior.
