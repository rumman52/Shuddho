# Personal agent implementation and release plan

**Scope and status.** This is the proposed delivery plan for the [architecture](PERSONAL_AGENT_ARCHITECTURE.md) and all 26 entries in the [service catalog](PERSONAL_AGENT_SERVICES.md). Baseline: PR #204, commit `9c658742ac38c6a1f3bcaf7f6c92869be47ab4f2`. This change updates design documentation only. No runtime feature, migration, deployed configuration, credential scope, customer account or production flag is changed.

**Qualify the baseline while developing the next bounded slice.** Current release gates remain mandatory: identity and owner isolation, PostgreSQL, private storage, Temporal/recovery, model and multilingual quality, backup/restore, deletion, parallel restart/fan-in, rollback and enabled-provider proofs. The reviewed rollout, source/model identity, activation bundle and ledger must match. A successful design review or mocked CI run cannot replace live evidence.

**Implement in separate reviewable increments.** Each increment includes its UI, operation limits, failure states, evidence and kill switch. The numbering is an internal plan, not GitHub PR numbers.

| Increment | Deliverable and main files | Required acceptance evidence |
| --- | --- | --- |
| PA-01 | Persistent goals, versioned edits and links to current agent runs. Extend `models.py`, migrations, `api.py`, `agent_repository.py`; add goal repository/schemas and Goals UI. | Owner isolation, idempotent creation, stale-edit conflict, link to existing run, pause/cancel semantics; no added provider authority. |
| PA-02 | Temporal schedule reconciliation, occurrence dedupe and in-app notification outbox. Extend workers/config; add automation and notification modules/UI. | Crash before/after dispatch, duplicate occurrences, DST, overlap, catch-up, expiry, quiet hours and kill-switch enforcement. |
| PA-03 | Result-aware v3 coordinator and evaluated DeepSeek profiles. Extend `agent_planning_model.py`, schemas, runtime, workflow and worker dispatch. | Verified observations change the next step; limits stop work; v1/v2 replay and rollback remain compatible; exact receipts govern completion. |
| PA-04 | Project/file retrieval, context references and memory proposals. Extend `memory_repository.py`, storage/extraction and context modules. | Tenant filtering, revoked/deleted data removal, no memory-based permission, provenance and language-quality improvement. |
| PA-05 | Separated permission/credential boundary and connector capability contracts. Extend action policy/registry; introduce independently authenticated gateway/credential components. | Scope/audience tests, revocation races, secret exclusion, destination checks, injected-instruction rejection and no bypass through direct egress. |
| PA-06 | Consented Google calendar/mail reads, sync cursors, events and renewal; Microsoft equivalents per demand. Extend provider adapters and Connections UI. | Live consent, allowed-source reads, disconnect/expiry, duplicate/out-of-order callbacks, cursor-gap recovery and notification delivery. |
| PA-07 | Supervised browser broker and secure takeover, initially research and form preparation. Add isolated browser worker deployment and session UI. | Owner/session isolation, secret concealment, SSRF/egress checks, malicious text/images/downloads, takeover, cancellation and unsupported-site handling. |
| PA-08 | Sandboxed computation and private interactive artifacts. Add executor lifecycle, bounded dependencies, export validation and isolated preview origin. | No host/secret access; resource/time/network limits; cleanup; useful data/code tasks; artifact-origin isolation. |
| PA-09 | Qualified transaction adapters for selected travel, restaurant, shopping and negotiation flows. Extend action schemas/registry and provider-specific reconciliations. | Price/terms changes invalidate approval; no blind duplicate execution; exact confirmation and explicit uncertain outcome. |
| PA-10 | Broader proactive suggestions, mobile/browser push and selected messaging/collaboration channels. Extend notification/preferences and each provider adapter. | Useful/quiet notifications, scope-preserving routing, dedupe/delivery receipts, user opt-out and channel-specific consent. |
| PA-11 | Measured expansion of artifact quality, services and operated capacity. Extend render/recalculation, task evaluations and release controls. | Supported-language/format results, cost/capacity headroom, incident/restore exercises and evidence-bound cohort progression. |

PA-01 and PA-02 are merged on `main` through PRs #207 and #208; their exact implementation heads passed repository CI and remain default-off pending separate staging/production qualification. PA-03 merged through PR #209 with frozen Runtime v3 routing, result-aware typed decisions, persisted planner evidence, explicit budgets and verified completion while preserving v1/v2 workflow compatibility; `SHUDDHO_AGENT_RUNTIME_V3_ENABLED` remains default-off pending separate live/staging/production qualification. PA-04 merged through PR #210: run-pinned owned document versions can be retrieved into bounded provenance-carrying context, deleted sources are invalidated at read/review time, existing explicit memory remains separately scoped, and DeepSeek may only create inert memory proposals that cite server-authorized context IDs and require user acceptance before becoming a memory fact. `SHUDDHO_CONTEXT_RETRIEVAL_ENABLED` remains default-off and release-gated. PA-05 merged through PR #211: code-owned connector capability contracts define exact operation scopes/audience/egress policy, approved actions obtain persisted owner/action/connection/destination-bound execution grants, trusted credential brokerage revalidates grants and identity immediately before provider access, and disconnect revokes grants. `SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED` remains default-off and release-gated. PA-06 implementation is merged through PRs #212, #213 and #214: revocable Gmail/Google Calendar and Microsoft Outlook Mail/Calendar read grants use durable cursors, normalized snapshots, authenticated/provider-bound event intake, duplicate suppression, renewal, cursor-gap recovery and the existing trust/credential boundary. `SHUDDHO_CONNECTOR_READS_ENABLED` remains default-off and release-gated; live Google/Microsoft provider qualification and controlled staging evidence remain before PA-06 is production-qualified. PA-07 remains in progress after merged PRs #215 and #216. The broker now includes an authenticated service-only worker API and a separately runnable Playwright worker that executes one leased navigation command at a time through a local CONNECT proxy. Every outbound host is DNS-resolved by the worker, revalidated by trusted application code against the active command/session and approved origin, and the proxy pins the TCP connection to one approved public IP so browser DNS cannot silently re-resolve to an internal address. Downloads are disabled, service workers are blocked, browser subprocesses receive no Shuddho worker token, commands remain ordered per session, and completion still requires bounded redirect/DNS evidence. This is still a bounded stateless navigation executor rather than full PA-07 completion: secure interactive takeover/login state, credential concealment/entry transport, durable session continuity, active cancellation propagation, hostile-page/download qualification, controlled staging and recovery evidence remain required. PA-09 requires the relevant qualified API or browser path; a browser feature alone is insufficient.

UI work is part of each slice. PA-10 broadens channels and relevance; it does not postpone the initial Goals, Approvals, Results or notification UI.

**Capability flags must be implemented through the canonical release contract.** The following names are design proposals and do not exist merely because they appear here.

| Proposed flag | Intended capability |
| --- | --- |
| `SHUDDHO_PERSONAL_GOALS_ENABLED` | Persistent goals |
| `SHUDDHO_AUTOMATIONS_ENABLED` | Reviewed schedules and event-triggered work |
| `SHUDDHO_AGENT_RUNTIME_V3_ENABLED` | New coordinator for new eligible runs |
| `SHUDDHO_CONTEXT_RETRIEVAL_ENABLED` | Scoped project/source retrieval |
| `SHUDDHO_CONNECTOR_READS_ENABLED` | Qualified revocable connected Gmail/Calendar reads and event synchronization |
| `SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED` | Deterministic connector permission/credential boundary |
| `SHUDDHO_BROWSER_ENABLED` | Brokered isolated browsing |
| `SHUDDHO_CODE_EXECUTION_ENABLED` | Isolated computation |
| `SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED` | Individually qualified transactional operations |

Implemented flags add their dependencies, live evidence, activation/ledger identity and rollback controls to `scripts/release_contract.py`; recovery evidence remains a separate production qualification step. A broad transaction flag cannot replace per-provider/per-operation allowlisting. No new flag defaults on. Preserve current coworker and LinkedIn Agent proposal production restrictions.

**Use additive compatibility and staged activation.** Add schemas first with old readers/workers supported. Backfill explicitly owned data only; do not reclassify anonymous profiles as authenticated identities. Deploy compatible API/worker versions, then activate a reviewed cohort. New runs can route to v3 while old histories continue on v1/v2. Turning v3 off affects new admission; do not replay existing v3 histories through v1.

Automation kill switches must be enforced in admission and before paid/mutating work; pausing Temporal schedules is an additional reconciled action. Disconnect/revocation invalidates grants and pending work before a new claim. Preserve completed artifacts and receipts, including uncertain actions. Recovery requires fresh matching activation evidence, not a reused pre-rollback attestation.

**Make these first acceptance stories executable.**

1. Student workflow: upload an owned syllabus, create a three-week goal, generate a plan/deck through current services, activate a daily in-app briefing, close the app and restart a worker. Each due occurrence maps to one accepted run; results and notifications remain inspectable.
2. Office workflow: produce cited research and an editable report/deck, then prepare an email. The user selects the connection/recipient and approves the exact content. A provider timeout is reconciled or displayed as uncertain, never silently resent.
3. Calendar workflow: read only consented resources, propose a conflict-free time with explicit timezone, and create an event only through the approved action. A Zoom link is reported as newly created only when the Zoom provider confirms it.
4. Commerce workflow: compare options and prepare a cart/reservation. Change the price after preview; execution must stop and request a fresh approval. Restart after a possible payment submission; no second charge is attempted blindly.
5. Revocation workflow: remove connector access or a source while a goal waits. Subsequent work cannot use the revoked resource; cached/indexed copies and queued sync do not restore access.
6. Adversarial workflow: a webpage/email/file asks the agent to leak another user's data, reveal secrets or bypass approval. The call is denied by ownership/capability/egress enforcement even if the model proposes it.

**Define release objectives before evaluating new task families.** These are proposed targets, not measured Shuddho results:

| Measure | Proposed pilot objective |
| --- | --- |
| Mandatory contract and existing quality fixtures | All required cases pass; retain stricter current fixture thresholds |
| Representative end-to-end tasks | At least 90% human-accepted completion for the selected pilot workflows; report per-language/task results and sample sizes |
| Critical authorization/isolation/recovery cases | Zero observed unauthorized writes, cross-owner reads, secret leaks or duplicate provider mutations in the release suite |
| Internal scheduled delivery under defined normal load | p95 notification availability within 60 seconds of accepted due time, excluding configured quiet hours; separately report provider delays |
| Task economics | Measured model/search/sandbox/render/storage/notification cost per completed task within an agreed budget |
| Cancellation/revocation | No newly claimed work after revocation becomes effective; honestly account for already-claimed operations |
| Artifact quality | Native opening/rendering/recalculation checks plus human review of representative multilingual outputs |

A zero-failure test suite is evidence for its tested scenarios, not proof that no failure can occur. Include provider 429/outage, duplicate callback, process loss, stale grant, changed source, DST and uncertain mutation cases. Use deterministic checks and human rubrics; model judges are supplementary. Keep raw sensitive content out of shared traces.

**Use managed infrastructure selectively.** Reuse the deployed frontend/API pattern, managed PostgreSQL, private object storage and Temporal. Add separate trusted connector workers and isolated execution pools. Choose sandbox, notification, search, OCR/embedding/speech and payment providers through short capability/security/cost evaluations. Avoid a full framework migration, Kubernetes adoption or regional replication unless a measured need justifies the operating cost.

In the initial region, assign an operational owner for every launched connector/service. Track queue depth, provider saturation, budget reservations, event lag, schedule drift, notification usefulness, missing receipts, retention and sandbox cleanup. Set restore objectives after an actual recovery exercise and publish the measured result.

**Non-technical work is part of the release.** Maintain the full service roadmap while piloting office/student and selected personal workflows. Recruit users to test outcomes, collect consented failure feedback and fix repeat problems. Define provider app verification, support, incident escalation, deletion/export, terms and real data-processing commitments before launch.

Offer clear account connection and revocation controls. Explain each approval and what remains uncertain. Price from actual workloads; include browser/code and support costs, not only tokens. Keep the free writing experience and publish realistic task limits. Obtain independent security review before expanding general browser/code access or personal transactions.

**Operational activation remains distinct from code completion.** Use the existing evidence-bound cohort progression, including the current small controlled cohort stages where applicable. Expand only capabilities with live provider and recovery proof. This plan authorizes no production activation, send, purchase, reservation or permission expansion by itself.

The implementation is a multi-increment engineering program. Commit to the next bounded slice and re-estimate after deployed task measurements and provider approvals. No unsupported percentage-complete claim or fixed parity date is attached to this redesign.
