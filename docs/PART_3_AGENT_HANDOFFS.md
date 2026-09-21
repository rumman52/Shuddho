# Typed Agent Step Handoffs

This increment lets a later Agent Runtime task consume the verified output of the nearest prior completed task step.

It is intentionally smaller than a general dependency graph and remains disabled by default.

## Problem

Before this increment, a multi-step plan such as:

```text
research -> presentation -> email draft
```

executed in order, but each task mostly worked from the original goal and owned input documents. The generated result of one step was not automatically available as context to the next step.

## Handoff model

```text
completed task step
      |
      +-- durable tool receipt
      +-- durable task draft checkpoint
      |
      v
server verifies same owner/run
      |
      v
bounded ephemeral handoff source
      |
      v
next non-research task draft
      |
      v
receipt stores provenance only
```

Only the nearest prior completed non-consequential task step is eligible.

Approved Gmail/Calendar actions are never handoff sources.

## Durable link

Migration `0008` adds `agent_step_id` to agent-owned child tasks.

The API cannot set this field. The trusted Agent Runtime creates child tasks with both:

- `agent_run_id`
- `agent_step_id`

The handoff resolver verifies the prior receipt, task owner, run ID, step ID, task terminal state, and draft checkpoint before returning any context.

## Runtime scope

Handoff context is injected only during drafting.

It is not added to:

- planner prompts;
- Temporal workflow payloads/history;
- web search queries;
- source extraction;
- Gmail/Calendar previews;
- action approvals;
- task notes;
- tool arguments.

A `research.search` step never receives prior agent handoff text. Its evidence path remains based on the original owned request plus provider-retrieved web evidence.

## Bounds

Default:

```text
SHUDDHO_AGENT_HANDOFFS_ENABLED=false
SHUDDHO_AGENT_HANDOFF_BYTES=12000
```

At most one nearest prior task result is included.

The source text is serialized from the prior validated draft checkpoint and bounded by the configured UTF-8 byte limit. If truncated, the handoff provenance records that fact.

The source `sha256` hashes the exact bounded text supplied to the downstream model. A separate upstream digest identifies the complete prior draft serialization.

## Provenance

The downstream task draft checkpoint and final tool receipt persist only handoff provenance:

```json
{
  "handoff": [
    {
      "invocation_id": "...",
      "task_id": "...",
      "tool": "document.create",
      "ordinal": 1,
      "truncated": false
    }
  ]
}
```

The prior generated text is not copied into the downstream receipt.

## Trust model

The prior generated result is still untrusted task data. Existing drafting instructions continue to prevent source content from overriding system/tool policy.

A handoff cannot:

- register or select a tool;
- grant permissions;
- approve an action;
- select an account or external destination;
- create arbitrary URLs or shell/browser access;
- cross account or agent-run boundaries.

## Replanning

A replan may replace only unstarted steps as established in the bounded intelligent planner increment.

Handoffs are resolved at execution time from completed durable receipts. Newly replanned steps therefore cannot reference deleted/unstarted steps through model-supplied IDs.

## Deferred

This increment intentionally does not add:

- planner-selected dependency IDs;
- arbitrary DAGs;
- multiple upstream dependencies;
- binary artifact ingestion as model context;
- cross-run dependencies;
- cross-workspace sharing;
- model-selected artifact IDs;
- result-quality-driven replanning.

Those require separate contracts and evaluation.

## Release gate

Keep `SHUDDHO_AGENT_HANDOFFS_ENABLED=false` until:

1. migration `0008` is deployed after `0007`;
2. API and worker releases are coordinated;
3. same-run ownership and migration parity tests pass;
4. Temporal chaining and restart tests pass;
5. research evidence isolation remains green;
6. staging verifies bounded payload size and downstream source attribution.
