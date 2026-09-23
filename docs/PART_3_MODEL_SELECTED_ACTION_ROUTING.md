# Bounded Model-Selected Attached-Action Routing

This increment is the first controlled bridge between Shuddho's intelligent planner and consequential actions.

It does **not** let the model create or authorize an external mutation. It lets the planner recommend the order of actions that the user already prepared and explicitly attached to the Agent run.

## Why this is the next boundary

Shuddho already has a connector-neutral consequential-action registry, immutable v2 previews, server-owned approval scopes, explicit user approval, committed execution claims, Google/Microsoft adapters, and serialized approved-action execution inside Agent Workflow v1/v2.

The missing architecture step is planner awareness without transferring authorization to the model.

## Default-off flag

```text
SHUDDHO_AGENT_ACTION_PLANNING_ENABLED=false
```

Production configuration fails closed if this flag is enabled without Agent Runtime, the bounded intelligent planner, and consequential actions.

## Planner-visible data

For already attached actions, the model may receive only:

```json
[
  {"slot": 1, "tool": "email.send"},
  {"slot": 2, "tool": "calendar.create"}
]
```

The planner does not receive external action IDs, connection IDs, providers/provider subjects, recipients, attendees, content, subject, location, time, preview hashes, approval scopes, OAuth material, or provider receipts.

Unknown fields supplied to the planner adapter are stripped before the provider request.

## Routing semantics

The normal planner `steps` remain non-consequential task tools only. The planner may additionally return an `action_order` list.

Server rules:

1. each slot must refer to an action already attached to this run;
2. slots are unique and bounded to the existing maximum of three attached actions;
3. the model cannot introduce a new action ID or action kind;
4. omitted slots are **not dropped**; Shuddho appends them in original server order;
5. all consequential actions remain after normal task steps;
6. Shuddho reconstructs exact `action_id` arguments only after model output is validated;
7. every action still uses the existing immutable preview -> explicit approval -> serialized execution -> provider receipt/reconciliation path.

Planner output can influence routing order only. It cannot expand authority.

## Replanning

Capability-change and incomplete-result replanning use the same contract. Actions that already completed are removed from the candidate set by trusted server state. Remaining bound actions are exposed only as fresh opaque slots and remain preserved even if the planner omits them.

## Compatibility

When the flag is false, no attached-action candidates are sent to the planner, deterministic server action order is unchanged, existing Agent Workflow v1/v2 behavior is unchanged, and prepared actions continue through the exact approval path.

No database migration or Temporal workflow identity change is required.

## Release gate

Before enabling the flag for a controlled cohort:

1. dedicated Coworker CI must be green;
2. privacy tests must prove action IDs and preview content never enter planner requests;
3. slot validation must reject invented/out-of-scope slots;
4. tests must prove no attached action can be silently dropped;
5. staging must prove the action still pauses before provider execution until exact user approval;
6. restart/idempotency checks must continue to produce one provider mutation at most;
7. keep the existing Microsoft/Google provider and global action kill switches available.

A later increment may consider model-authored action **preparation**, but only behind a separate typed schema, explicit preview generation, and fresh user approval. This increment does not provide that capability.
