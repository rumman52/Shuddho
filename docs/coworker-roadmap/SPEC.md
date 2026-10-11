# Coworker evolution specification

## Outcome

Present one continuous Shuddho coworker that remembers authorized project context,
tracks goals, resumes bounded work, produces inspectable artifacts, schedules useful
work and prepares consequential actions for exact human approval.

## Preserve

Preserve the free multilingual/Bangla writing experience, local fallback engines,
explicit provider diagnostics, backend-only DeepSeek credentials and configurable
model, and explicit Gemma rollback. Do not select a provider silently.

Preserve PostgreSQL application/approval records, Temporal durable execution and old
history compatibility, private object storage, the existing ExternalAction ledger,
owner-bound context, permission gateway and credential broker.

## Durable conversation contract

Create owner-scoped conversations/messages with an explicit client request key and
payload fingerprint. One request identity admits at most one dispatch. Identical replay
returns the same message and linked task/run/action; changed input conflicts.

Store references to existing goals/tasks/runs/actions/artifacts rather than duplicate
their state. Concurrent independent messages can link separate runs. Steering/cancel
targets an explicit run and expected revision; late observations cannot undo cancellation.
SSE/polling uses durable cursors; reconnect never dispatches work.

Accepting an automation or approving a mutation requires a deterministic UI/API control.
A natural-language "yes" in unrelated chat, source document or retrieved memory grants
no execution authority.

## Context and files

Maintain owner/resource/version/provenance/checksum/deletion linkage for selected files.
Start with existing document/artifact records; introduce a logical workspace manifest
only for relationships/versioning those records do not support. Do not build a second
filesystem truth store.

Conversation context is bounded and purpose-authorized. Recheck revoked/deleted
sources at use. Inferred facts remain reviewable memory proposals. Memory conveys no
permission. Distinguish source observations from user instructions and model inference.

## Reasoning and tools

Reuse Runtime v3's observe -> decide -> execute -> verify cycle. Validate typed decisions;
only verified outputs/receipts can support completion. Keep model/account/run capacity
reservations and exact versioned tool metadata.

Add a read-only brokered browser tool first; a browser click never authorizes purchase/send.
Generated Python must become a stored immutable code proposal, show the source/inputs/
limits/destinations to the user, and execute only that reviewed hash in isolated compute.
Keep the existing exact-user-supplied Python path compatible. Generating a skill or tool
inside the sandbox does not register it as trusted production authority.

Code/browser workers have no production secrets, host filesystem, container socket or
cross-owner access; enforce resource, network and cleanup limits outside generated code.

## Proactivity and transactions

Reuse the existing scheduler, occurrence dedupe, connector ingestion and notification
ledger. Require consent, quiet hours, expiry, overlap policy, bounded catch-up, source
freshness and kill-switch checks at admission and before paid/mutating work.

Use exactly one approved execution identity and existing external-action claim. Bind
owner, counterparty/destination, amount/currency, terms, source revision, expiry, preview
hash and provider/operation. Changed terms invalidate approval.

Classify uncertainty after possible provider dispatch. Reconcile read-only receipts;
never blindly reclaim an uncertain mutation. Shopping/travel require concrete registered
providers and a user-present hosted handoff; handoff creation is not booking/purchase
success. Provider confirmation needs exact receipt validation.

## Qualification

Separate statuses: planned, implemented, repository-verified, staging-verified,
production-qualified and activated. A status change carries exact revision and evidence.
CI must run mandatory safety tests with required dependencies and zero skips.

Define all 16 Phase 11 outcomes in ROADMAP.md. Prove dispatch/recovery through actual
public API, PostgreSQL, Temporal and process interruption where relevant. Pure model
or ORM mocks are not deployment proof.

Use existing stricter quality thresholds. Proposed pilot target: at least 90% human-
accepted outcomes for the selected workflows, with counts and per-language results.
Zero observed cross-owner access, unauthorized mutations, secret exposure and duplicate
approved mutations in the qualification suite. Define 99.9% availability separately and
measure over an operated window; do not certify it from CI or chaos cases.

## Authorization scope

This request authorizes the roadmap, reusable engineering skill, coding instructions and
reviewable repository setup. It does not activate production, broaden financial authority,
create paid infrastructure, send messages or execute purchases. Future execution must
follow the concrete task's authorized scope and current release contract.

