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

Before creating release evidence, verify the checked-in templates still match the canonical release contract:

```bash
uv run python -m scripts.release_contract_check
```

The contract is defined in `scripts/release_contract.py`. CI also exercises this check through the Python test suite, so adding a new optional capability without updating the release templates fails closed.

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

Optional capability gates are derived from the same canonical release contract used for dependency and rollback validation. Depending on the reviewed manifest, the final gate may additionally require:

- `action_attachments`;
- `action_reminders_google`, plus `action_reminders_microsoft` when Microsoft is declared;
- `action_recipients`;
- `action_document_sharing`;
- `action_email_threading`;
- `action_social_publishing`;
- `action_selection`;
- `action_proposals`;
- `agent_linkedin_proposals`.

The checked-in staging template contains every currently supported gate as `pending`. Unused optional evidence may remain pending; the final gate only requires evidence for capabilities declared in the reviewed rollout.

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
- approved attachments are enabled without Actions and Artifact Services;
- calendar reminders, saved recipients, Gmail threading, or LinkedIn publishing are enabled without Actions;
- Drive document sharing is enabled without Actions and Artifact Services;
- agent action selection is enabled without Actions, Agent Runtime, and Intelligent Planner;
- agent action proposals are enabled without Actions, Agent Runtime, and Intelligent Planner;
- LinkedIn Agent proposals are enabled without both ordinary Agent proposals and approval-bound LinkedIn publishing;
- a capability requiring a provider is declared without that provider. In particular, LinkedIn publishing cannot use the legacy Google-only provider fallback.

Optional capabilities may remain disabled for the first cohort even if their staging gates have passed.

## Required rollback controls

The manifest must contain the exact kill switches:

- `SHUDDHO_COWORKER_ENABLED=false`
- `SHUDDHO_AGENT_RUNTIME_ENABLED=false`
- `SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false`
- `SHUDDHO_RESEARCH_SERVICES_ENABLED=false`
- `SHUDDHO_ACTIONS_ENABLED=false`
- `SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false` when attachments are declared;
- `SHUDDHO_ACTION_REMINDERS_ENABLED=false` when reminders are declared;
- `SHUDDHO_ACTION_RECIPIENTS_ENABLED=false` when saved recipients are declared;
- `SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false` when Drive sharing is declared;
- `SHUDDHO_ACTION_EMAIL_THREADING_ENABLED=false` when Gmail threading is declared;
- `SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false` when LinkedIn publishing is declared;
- `SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false` when action selection is declared;
- `SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false` when action proposals are declared;
- `SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=false` when LinkedIn Agent proposals are declared.

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


## Non-executable Agent action proposals

The optional `action_proposals=true` capability allows the initial intelligent planner to suggest typed email/calendar payloads as inert proposal records.

See [Non-Executable Agent Action Proposals](AGENT_ACTION_PROPOSALS.md).

A proposal is not an external action. It has no provider binding, approval state, outbox or executor path. The authenticated user must select an owned connection and promote the exact proposal hash. Promotion creates a separate immutable action preview in `awaiting_approval`; normal explicit approval is still required before any provider mutation.

Production enablement requires its independent `action_proposals` staging evidence from [Controlled Live Agent Action-Proposal Staging](CONTROLLED_STAGING_ACTION_PROPOSALS.md) and the exact rollback switch `SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false`.


## Action-proposal production activation

A final cohort decision with `action_proposals=true` and passed live staging evidence does not prove that production is running the reviewed revision/configuration.

Before treating `SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=true` as activated, run [Agent Action-Proposal Production Activation](ACTION_PROPOSALS_ACTIVATION.md).

The verifier binds the exact staging evidence and reviewed rollout to the reviewed deployment, fetches an authenticated read-only runtime manifest from production, requires exact source-revision/capability/provider equality plus controlled-cohort enforcement, requires fresh clean post-deploy health, and emits `action_proposals_verified`.

This activation artifact is evidence only. It cannot enable a flag, promote a proposal, approve an action, mutate a provider, expand the cohort or authorize recovery.
