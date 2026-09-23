# Controlled Staging: Live Agent Action Selection

This exercise produces the independent `action_selection` staging evidence required before enabling bounded planner selection of attached external-action drafts.

It is intentionally **non-destructive**: the probe never approves an action and never calls a provider execution endpoint.

## Preconditions

The deployed staging environment must already have:

- `SHUDDHO_AGENT_RUNTIME_ENABLED=true`;
- `SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=true`;
- `SHUDDHO_ACTIONS_ENABLED=true`;
- `SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=true`;
- a working Agent worker/Temporal path;
- one active staging email connection and one active staging calendar connection for the selected provider;
- a staging account token in `SHUDDHO_STAGING_TOKEN_A`;
- an HTTPS `SHUDDHO_STAGING_API_BASE_URL`.

The operator must explicitly opt in with:

```bash
export SHUDDHO_STAGING_ALLOW_LIVE_ACTION_SELECTION=true
```

## Run

Google-backed synthetic drafts:

```bash
uv run --extra coworker python scripts/staging_live_action_selection.py \
  --provider google \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.action-selection.json
```

Microsoft-backed synthetic drafts may be used after Microsoft action rollout is independently verified:

```bash
uv run --extra coworker python scripts/staging_live_action_selection.py \
  --provider microsoft \
  --base-evidence /secure/path/staging-evidence.microsoft-actions.json \
  --output /secure/path/staging-evidence.action-selection.json
```

## What the probe proves

The probe creates two synthetic immutable action drafts:

1. one email-send draft;
2. one calendar-create draft.

It attaches both to a new Agent run with an explicit instruction to use only the email draft. The live intelligent planner and normal worker path must then produce the following observable result:

- the Agent run reaches `awaiting_approval`;
- the run used the intelligent planner;
- exactly one consequential invocation exists;
- that invocation is `email.send`;
- the selected email action is still `awaiting_approval`;
- the selected action has no `approved_at`, provider receipt, or execution audit;
- the calendar action is removed from the Agent run's action binding;
- the calendar action remains `awaiting_approval`;
- its audit contains exactly one `action.released_unselected`;
- neither synthetic action has been approved or executed.

The script then cancels the synthetic Agent run and leftover draft for cleanup.

## What the probe does not prove

This live probe does not independently inspect the private model-provider request body. The opaque-handle privacy contract remains covered by deterministic CI tests that verify action UUIDs are absent from the planner's available-tool list and that only server-generated `attached.email.N` / `attached.calendar.N` handles are model-visible.

Production release requires **both** the CI privacy contract and this live end-to-end approval-boundary exercise.

## Evidence

A passing run adds:

```json
{
  "action_selection": {
    "status": "passed",
    "evidence": "live intelligent Agent selected only the attached email draft, released the unselected calendar draft, and paused at explicit approval with no provider execution or receipt",
    "verified_at": "<UTC timestamp>"
  }
}
```

The evidence contains no action IDs, recipients, payload text, OAuth details, provider credentials, or model output.

## Failure semantics

Any unexpected planner result, missing release audit, automatic approval, provider receipt, terminal Agent failure, or timeout exits non-zero and does not write passing evidence.

Do not manually convert a failed or partial run into `status: passed`.
