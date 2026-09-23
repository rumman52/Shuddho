# Bounded Intelligent Planner

This increment upgrades the Agent Runtime from deterministic intent routing to a model-assisted bounded planner while keeping the server in control of execution.

It remains disabled by default.

## Planning contract

The planner receives only:

- the agent goal;
- the names of currently enabled, non-consequential registered tools;
- a planning reason such as `initial` or `capability_changed`;
- only when the separate action-routing flag is enabled, opaque attached-action candidates containing `{slot, tool}` and no action ID or preview.

It does not receive:

- tool credentials;
- Gmail, Outlook, or Calendar preview payloads;
- action IDs, connection IDs, recipients, event details, or action approval hashes;
- memory values;
- document text;
- search evidence;
- provider receipts;
- arbitrary URLs;
- shell/browser capabilities.

The planner may return at most three items:

```json
{
  "steps": [
    {
      "tool": "research.search",
      "objective": "Compare the current market."
    }
  ]
}
```

The model cannot supply executable arguments. Shuddho reconstructs arguments from owned runtime state and validates them through the existing server-owned tool registry.

## Consequential actions

By default, the model is never offered consequential action routing and existing bound actions from PR #112 are appended deterministically by the server.

A later bounded routing increment may be enabled with:

```text
SHUDDHO_AGENT_ACTION_PLANNING_ENABLED=true
```

When enabled, the planner receives only opaque attached-action slots such as `{"slot": 1, "tool": "email.send"}`. It may return an `action_order` preference. Shuddho maps those slots back to server-owned action IDs, keeps all unmentioned attached actions, and places the complete action suffix behind the existing approval-aware execution path.

The model cannot create an action, drop an attached action, change recipients/content/provider/time, approve an action, or cause provider execution. Exact immutable preview validation and explicit user approval remain mandatory.

## Fallback

When intelligent planning is disabled, the existing deterministic #111 planner is unchanged.

When intelligent planning is enabled but the planner provider is unavailable, times out, or returns an invalid bounded proposal during the initial planning call, Shuddho falls back to the deterministic planner.

Fallback does not grant new permissions or tools.

## Replanning

This increment allows at most one automatic replan.

The only automatic trigger is:

```text
planned task tool
    |
    +-- has not started
    |
    +-- capability is no longer enabled
    |
    v
replan_required
```

Examples include a service being disabled during a rollout or a capability being withdrawn before that step starts.

Replanning is not triggered by:

- model/provider outages;
- token or search budgets;
- user cancellation;
- missing approval;
- rejected/expired actions;
- uncertain external-action outcomes;
- content-quality judgments;
- arbitrary tool failures.

A started step cannot be replaced.

Completed steps are immutable.

The replacement plan plus completed prefix can never exceed eight total steps.

## Planner budget

Defaults:

```text
SHUDDHO_AGENT_PLANNER_CALLS=2
SHUDDHO_AGENT_PLANNER_TOKEN_BUDGET=16000
SHUDDHO_AGENT_PLANNER_MAX_OUTPUT_TOKENS=1200
```

The normal shape is one initial planning call plus one possible replan.

Planner budget is reserved before the provider request and counts against the existing daily Coworker token budget. Unknown provider outcomes retain the reservation. Planning activities are not retried by Temporal because doing so could create another paid reservation after an uncertain outcome.

The planner token field on an agent run represents conservative reserved/charged planner budget, not provider-billed token telemetry.

## Temporal history

Temporal receives only run IDs, step ordinals, counts, and safe status values.

The user goal and planner proposal remain outside workflow history.

## Safety invariants

1. Planner-selected tools must exist in the server registry.
2. Planner-selected tools must be enabled and non-consequential.
3. Duplicate tool names in one proposal are rejected.
4. Tool calls/refusals from the model response are rejected.
5. Real arguments are reconstructed by Shuddho, not accepted from model output.
6. Document IDs always come from the owned agent run.
7. External actions remain deterministic bound steps.
8. One run can replan at most once in the Temporal workflow.
9. A started step cannot be replaced.
10. The complete plan remains bounded to eight steps.

## Deferred

This increment intentionally does not add:

- open-ended plan/act loops;
- result-quality-driven replanning;
- model-created tool arguments;
- model-selected external actions;
- tool dependency graphs;
- automatic use of generated artifacts as later tool inputs;
- multi-agent delegation;
- planner access to long-term memory;
- planner access to raw document or email content.

Those capabilities require separate evaluation and policy boundaries.

## Release gate

Keep:

```text
SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=false
```

until:

1. migration `0007` is deployed;
2. all workers register the replan activity;
3. deterministic fallback is verified in staging;
4. PostgreSQL planner-budget race tests pass;
5. Temporal capability-change replan tests pass;
6. planner prompt/output privacy is reviewed;
7. tool-selection evaluations show acceptable accuracy before user exposure.


## Attached-action routing rollout

Keep `SHUDDHO_AGENT_ACTION_PLANNING_ENABLED=false` until the bounded routing tests and controlled staging approval/restart checks pass. Enabling it also requires Agent Runtime, the intelligent planner, and consequential actions to be enabled. The flag changes planning metadata only; it does not authorize a provider mutation.
