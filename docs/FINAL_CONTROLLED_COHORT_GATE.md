# Final Controlled-Cohort GO / NO-GO Gate

This is the final admission gate after all Coworker staging exercises are implemented.

It does **not** turn on production traffic. It decides whether a tightly bounded first cohort is allowed to be enabled.

## Inputs

The decision requires two machine-readable files:

1. **Staging evidence JSON** produced by the existing staging exercises.
2. **Rollout manifest JSON** describing the exact first-cohort configuration and operational controls.

Start from:

- `docs/staging-evidence.template.json`
- `docs/cohort-rollout.template.json`

## Run

```bash
uv run python scripts/cohort_release_gate.py \
  --evidence /secure/path/staging-evidence.final.json \
  --rollout /secure/path/cohort-rollout.json \
  --max-cohort-users 25 \
  --output /secure/path/cohort-decision.json
```

A successful decision is exactly:

```
GO_CONTROLLED_COHORT
```

Any missing technical evidence or rollout control returns `NO-GO` and exits non-zero.

## Required base staging evidence

The first cohort always requires:

- repository/dedicated Coworker CI;
- managed identity and two-account owner isolation;
- PostgreSQL TLS + migrations;
- private object storage and owner-scoped download validation;
- Temporal reachability + real worker restart/replay;
- live DeepSeek planner evaluation;
- PostgreSQL/object backup and isolated restore drill;
- retention/deletion + orphan cleanup;
- AgentWorkflow v2 restart with no duplicate child tasks;
- persisted fan-in timing proof;
- v2 → v1 feature-flag rollback proof;
- server-enforced cohort admission proof showing an invited account succeeds and a fresh non-member is denied before Coworker provisioning.

Research evidence is required only if `research=true` in the rollout manifest.

Live Google action evidence is required only if `actions=true`.

The rollout manifest may additionally declare `action_providers`. Legacy manifests without this field remain Google-only when actions are enabled. A manifest that declares Microsoft must use `["google", "microsoft"]`; Microsoft cannot replace the existing Google action baseline in this increment.

When `microsoft` is declared, the independent `microsoft_actions` live staging gate is also mandatory before `GO_CONTROLLED_COHORT`.

## First-cohort bounds

The gate defaults to a maximum of **25 users**.

This is an engineering safety ceiling for the first controlled cohort, not a product pricing or long-term customer limit. Increase it only through an explicit change after observing real production latency, errors, cost and operational load.

The manifest must reference the approved cohort list/ticket. General signup does not satisfy this condition.

## Capability dependency checks

The manifest is rejected if:

- Coworker or base work services are disabled while requesting a cohort launch;
- Agent child features are enabled while Agent Runtime is disabled;
- multi-source handoffs are enabled without handoffs;
- bounded parallel execution is enabled without the dependency graph;
- outcome replanning is enabled without intelligent planning;
- agent action selection is enabled without Actions, Agent Runtime, and Intelligent Planner.

Optional capabilities may remain disabled for the first cohort even if their staging gates have passed.

## Required rollback controls

The manifest must contain the exact kill switches:

- `SHUDDHO_COWORKER_ENABLED=false`
- `SHUDDHO_AGENT_RUNTIME_ENABLED=false`
- `SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false`
- `SHUDDHO_RESEARCH_SERVICES_ENABLED=false`
- `SHUDDHO_ACTIONS_ENABLED=false`
- `SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false` when action selection is declared.

It must also contain a real rollback/runbook reference.

A feature is not considered safe to enable merely because a flag exists; the rollback procedure must have already been exercised by the relevant staging gate.

## Required monitoring

Every first cohort requires references for:

- queue age;
- task success;
- provider errors;
- latency;
- token/cost usage;
- storage growth;
- Agent failures.

If Research is enabled, a Research/provider dashboard or alert reference is additionally required.

If Google actions are enabled, an actions dashboard/alert reference is additionally required.

The gate checks that references exist. Operators still need to verify the referenced dashboards/alerts are actually functioning.

## Incident ownership

The rollout manifest must include:

- an on-call/incident owner reference;
- a change/deployment reference.

No owner means NO-GO.

## Decision semantics

`GO_CONTROLLED_COHORT` means only:

> The declared, bounded cohort and declared capabilities have the required staging evidence and operational controls to begin a measured rollout.

It does **not** mean:

- general availability;
- unrestricted autonomy;
- a universal language-quality guarantee;
- unlimited provider capacity;
- demonstrated billion-user scale.

After cohort activation, watch actual p50/p95/p99 latency, queue age, error rates, retry rates, token/provider spend, storage growth, research citation issues and consequential-action outcomes. If predefined thresholds are breached, use the documented kill switches rather than widening the cohort.


## Provider-aware consequential-action admission

The final cohort decision now records the exact approved action-provider set.

Rules:

- actions disabled + no provider list → no provider gate;
- legacy actions enabled + no provider list → Google only;
- explicit `["google"]` → Google only;
- explicit `["google", "microsoft"]` → Google and Microsoft;
- Microsoft without Google → NO-GO;
- duplicate, unknown, or malformed providers → NO-GO;
- providers declared while `actions=false` → NO-GO.

This is a release-control contract only. Declaring a provider does not enable its runtime flag, create OAuth connections, approve an action, or execute an action.


## Agent-selected attached action drafts

The optional `action_selection=true` capability allows the bounded intelligent planner to choose among action drafts that the user explicitly attached to an Agent run and that are still awaiting approval.

The planner receives only opaque handles such as `attached.email.1` or `attached.calendar.2`. It does not receive action IDs, recipients, subjects, event details, connection IDs, provider credentials, preview hashes, or approval data.

Shuddho resolves a selected handle server-side to the exact already-bound action. Selection cannot create or edit a payload, choose a provider, approve an action, or execute it. The existing immutable preview and explicit user approval boundary remains mandatory.

Unselected drafts that are still awaiting approval are detached from the Agent run and remain available to the user as standalone drafts. Already-approved or executing actions are never model-selectable and are never detached.

Production enablement requires all of:

- `actions=true`;
- `agent_runtime=true`;
- `intelligent_planner=true`;
- `action_selection=true`;
- `SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=true` in the reviewed deployment;
- passed independent `action_selection` staging evidence;
- the exact rollback switch `SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false`.


## Action-selection activation evidence

A final cohort manifest with `action_selection=true` and a passed live staging gate does not by itself prove the deployed backend matches the reviewed configuration.

Before treating `SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=true` as activated in production, run [Agent Action Selection Rollout Activation](ACTION_SELECTION_ACTIVATION.md).

The activation verifier binds the exact timestamped `action_selection` staging evidence to the reviewed deployment record, verifies the deployed runtime prerequisites plus cohort enforcement, requires a fresh clean post-deploy operator status, and emits `action_selection_verified`.

This activation artifact is release evidence only. It cannot approve an action, execute a provider mutation, change the cohort, or enable a runtime flag.
