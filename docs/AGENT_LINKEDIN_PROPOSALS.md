# Inert LinkedIn Agent Action Proposals

## Purpose

This bounded Wave D increment lets Shuddho's intelligent planner suggest one exact personal LinkedIn text post as an **inert action proposal**. It does not grant the Agent publishing authority.

The implementation is disabled by default:

```text
SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false
SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=false
SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false
```

The LinkedIn proposal gate is nested. It may be enabled only when ordinary inert Agent proposals and the existing approval-bound LinkedIn publishing capability are also enabled.

## Authority boundary

The lifecycle is:

```text
model suggests exact post text
-> inert ActionProposal
-> user reviews exact proposal hash
-> user chooses an owned LinkedIn social connection
-> server prepares the normal social_publish_linkedin preview
-> user reviews the immutable preview
-> user explicitly approves
-> existing durable action workflow performs the provider mutation
```

The model does not choose:

- provider or connection;
- LinkedIn member identity;
- organization or company page;
- visibility;
- media;
- schedule;
- comments, reactions, reshares, analytics, edit, or delete operations;
- approval or execution timing.

The only new model-owned field is the exact bounded UTF-8 post text already validated by `LinkedInSocialPublish`. The proposal hash continues to bind the Agent run, exact typed payload, and rationale.

## No new executable Agent tool

This increment does **not** register `social_publish_linkedin` as an Agent tool and does not modify the Agent action-selection bridge.

An `ActionProposal` has no provider credential, outbox, approval, execution claim, provider receipt, or Temporal action workflow. Saving a LinkedIn proposal while `SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=false` fails closed.

Promotion re-checks the dedicated gate and then calls the existing `ActionRepository.prepare` path with the connection explicitly selected by the signed-in user. The existing consequential-action registry therefore revalidates provider/capability matching, the social-publishing kill switch, connection ownership, quotas, canonical payload, approval scope, expiry, and immutable preview hash.

Promotion still stops at `awaiting_approval`. It does not publish.

## Planner contract

Only the initial intelligent planning pass may produce an inert LinkedIn proposal. Replanning remains proposal-blind.

The planner receives two distinct booleans:

- `action_proposals_allowed`;
- `linkedin_action_proposals_allowed`.

LinkedIn proposals are allowed only when both are true. The system prompt limits them to a personal public text-post suggestion and explicitly forbids author/account selection, organization pages, media, alternate visibility, scheduling, and engagement actions.

## Runtime and rollback controls

The authenticated runtime manifest exposes:

```json
"agent_linkedin_proposals": false
```

The exact rollback switch is:

```text
SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=false
```

Disabling this flag blocks new LinkedIn proposal persistence and promotion while leaving ordinary email/calendar proposals and already-recorded action history unchanged. The underlying LinkedIn publishing feature retains its independent kill switch.

Existing activation and release verifiers normalize this new optional capability to `false` so historical reviewed evidence remains valid.

## Production status

This capability is **release-qualified for a reviewed controlled cohort while remaining disabled by default**.

A rollout declaring `agent_linkedin_proposals=true` now requires a dedicated passed `agent_linkedin_proposals` live staging record. Missing or failed evidence keeps the final cohort decision at `NO-GO`.

Production enablement additionally requires the exact activation and ledger chain documented in [LinkedIn Agent Proposal Production Activation](LINKEDIN_AGENT_PROPOSALS_ACTIVATION.md).

## Release qualification guarantees

Before a controlled production cohort enables the capability, the qualification chain proves all of the following:

1. a deployed intelligent planner can create an exact synthetic LinkedIn proposal while no matching `ExternalAction` exists;
2. no provider/account/member is chosen by the model;
3. wrong-hash promotion is rejected;
4. promotion requires an operator-selected owned LinkedIn social connection;
5. exact promotion creates one standalone `social_publish_linkedin` preview in `awaiting_approval`;
6. the saved Agent plan gains no consequential LinkedIn tool step;
7. no approval, execution audit, provider request, or LinkedIn receipt exists before explicit approval;
8. production activation binds the exact staging proof, reviewed rollout, deployed source revision, runtime manifest, cohort controls, and fresh operator health;
9. schema-v15 `agent_linkedin_proposals_verified` records the exact activation in the tamper-evident release ledger and requires current-stage schema-v8 `action_proposals_verified` plus schema-v14 `action_social_publishing_verified`;
10. schema-v10 bounded scale and post-rollback recovery consume that exact schema-v15 attestation and fail closed if it is absent, stale, reordered, or tampered.

The release-safety path preserves the existing personal-text-only LinkedIn boundary. It does not add organization publishing, media, social reads, scheduling, edit/delete, engagement operations, or direct Agent execution.
