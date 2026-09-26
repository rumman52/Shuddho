# Personal AI agent architecture

**Decision record.** Proposed on 26 September 2026 against commit `9c658742ac38c6a1f3bcaf7f6c92869be47ab4f2` (PR #204). Scope: all 16 requested personal-agent categories plus Shuddho's writing, work, research, presentations, spreadsheets and approved actions. These contracts specify the target; they are not evidence of deployed features.

The [service catalog](PERSONAL_AGENT_SERVICES.md) covers user outcomes and the [implementation plan](PERSONAL_AGENT_IMPLEMENTATION.md) defines delivery slices. The existing [release contract](../scripts/release_contract.py) continues to govern current capabilities.

**The product contract is a verified outcome with continuing ownership.** A user can request a deliverable or establish a goal lasting weeks. Shuddho plans, performs authorized work, checks results, asks for material missing information, and follows up on due times or relevant events. Chat, documents, goals and connected applications feed one workflow system. Records tie every result to sources, permissions, resource versions, costs and external receipts.

**Retain the implemented foundations.**

| Foundation | Existing area | Target extension |
| --- | --- | --- |
| FastAPI writing and local engines | `services/api/shuddho_api/` | Separate fast-writing capacity from agent work |
| Durable accounts/files/tasks/outboxes | `services/coworker/models.py` | Goals, triggers, notifications, context references |
| Typed tools | `agent_tools.py` | Reviewed read, browser, sandbox and transactional operations |
| Temporal v1/v2 | `workflow.py`, `worker.py` | New result-aware workflow version, compatible old histories |
| Bounded planner | `agent_planning_model.py` | Observations, next-step decisions, model profiles |
| Structured memory | `memory_repository.py` | Scoped retrieval and reviewable memory proposals |
| Approved actions | `action_registry.py`, `actions.py` | New kinds through the same exact-preview boundary |
| Artifacts/research | `office_exports.py`, `work_exports.py`, `research.py` | Iterative quality and budgeted research expansion |
| Evidence and rollout | `scripts/release_contract.py` and current gates | Capability-specific live qualification |

The current planner selects 1–3 choices, explicitly disables thinking, and rejects native tool-call responses. Its inputs lack a rich execution-observation bundle. Handoffs and bounded replanning already exist; this redesign expands them. Changing the model name alone leaves the planner contract unchanged.

Current memory consists of explicit user facts. Research makes one query with up to five sources. Reminders attach one selected reminder to a calendar event; they are not a recurring scheduler. Send-only email access cannot read inboxes. Existing native artifact limits remain until qualified extensions change them.

**Keep a modular core and separate execution trust boundaries.** Retain React/Vite, FastAPI, PostgreSQL, private object storage and Temporal in an initially single-region deployment. Use modules unless independent scaling or isolation warrants a process boundary.

| Component | Owns | Boundary |
| --- | --- | --- |
| Workspace API | Sessions, owner checks, commands and progress | No long-running task tied to HTTP lifetime |
| Goals/automations | Goal lifecycle, desired trigger configuration, revisions and budgets | No model-created permission |
| Temporal coordinator | Durable runs, waits, branches, recovery and cancellation | Model/network/database work belongs in activities |
| Context service | Authorized retrieval, provenance, expiry and deletion | Retrieved text cannot grant authority |
| DeepSeek gateway | Profiles, protocol, capacity and metering | Cannot approve business actions |
| Capability gateway | Schema, scope, budget and dispatch checks | No arbitrary caller-selected endpoints |
| Connector workers | Fixed-provider operations, receipts and reconciliation | Narrow service identities and credential scope |
| Credential service | Secret storage, rotation and revocation | No agent-readable passwords or tokens |
| Artifact workers | Restricted parsing, rendering and verification | No production/provider secrets |
| Browser broker | Observation, narrow actions, sessions, sign-in and takeover | No unrestricted agent debugging interface |
| Code sandbox | Temporary computation over allowed file copies | No host mounts, shared secrets or deployment access |
| Notification service | Outbox, preferences, delivery and receipts | No sensitive bodies in ordinary logs |

An initial deployment can use an API process, trusted workflow/artifact workers and a separately authenticated connector/credential boundary. Add browser/code pools only when their containment is ready. An always-running VM per user is optional; logical private workspaces and disposable compute can serve the first scoped release. Maintain separate capacity for writing, long tasks, actions and sandboxes.

**Separate persistent goals from bounded runs.** A goal records owner/workspace, desired outcome, success criteria, constraints, deadline and IANA timezone, resources, authorized capabilities, budget, milestones and next review. A run is one finite attempt to advance it. A goal wakes runs when needed instead of maintaining a continuously thinking session.

Proposed logical goal states: `draft`, `active`, `paused`, `blocked`, `completed`, `cancelled`, `archived`. Runs distinguish running, waiting for input/approval/event, success, failure, cancellation and uncertain external outcomes. Map/version existing state values compatibly; do not rename historical records.

Edits increment the goal revision. Work verifies that its selected revision remains authorized. Finished artifacts can survive an edit, but pending external actions must be rebuilt when affected. Project context is explicit. Family/team sharing requires reviewed ACLs rather than shared default memory.

**Introduce bounded observation and action.** Assemble the instruction, scoped source references, relevant facts, prior verified results, tool availability and remaining budget. The planner returns one typed decision:

| Decision | Meaning |
| --- | --- |
| `next_step` | Registered tool/version, bounded inputs, dependencies and expected result |
| `needs_input` | Missing fact and why execution depends on it |
| `awaiting_approval` | Reference to a server-prepared preview, never an approval |
| `wait` | Authorized time/event condition managed durably |
| `blocked` | Unavailable capability or unsatisfied constraint with recovery guidance |
| `complete` | Results satisfying the stored success criteria |

Server code derives identity, resolves owned connection handles, binds resource versions and checks schema/scope/budget. Model output cannot register tools, choose unowned connections, expand grants or approve actions. Receipts become observations for subsequent decisions. Typed handoffs carry bounded authorized dependencies.

Parallel independent steps share the run's grant and budget. Specialist roles may reuse the same model; separate models or autonomous subagents are optional and require measured benefit. The user experiences one coordinator. No branch may restart itself to evade spending or depth limits.

Use a new `shuddho_agent_run_v3` for incompatible history changes. Retain v1/v2 workers until their executions finish or undergo documented recovery. Keep model calls and external I/O in activities and replay recorded histories during qualification.

Proposed initial v3 limits: eight tool steps, four planner calls, two concurrent steps and a 30-minute active-run deadline, plus explicit token/currency ceilings. These are evaluation starting points, not current configuration changes. A goal waiting days wakes a new bounded run with fresh permission checks. Exceeding a limit returns useful partial work or a blocker.

**Automate within the permission already granted.**

| Operation | Target automation |
| --- | --- |
| Internal drafting, organization, artifact creation | Automatic after the request or explicit recurring instruction, within scope/quota |
| Connected reads and monitoring | Automatic under revocable read/monitor grants binding source, purpose and processing destination |
| External communication, sharing, publishing, calendar changes, form submission | Prepare automatically; execute after exact current preview approval |
| Purchases, binding reservations, fee-bearing cancellation, negotiated commitments | Exact final approval, fresh price/terms and qualified provider receipt |
| Unknown operations | Capability blocker or secure user takeover |

A daily digest should not ask for approval for every already-authorized read. A generic automation instruction does not authorize arbitrary spending or data disclosure. Future delegated-write mode requires its own recipients, action types, limits, expiry, revocation and evidence contract. Current consequential actions retain per-action approval.

Reuse immutable previews and the action ledger. Extend scopes as needed for merchant, amount/currency, taxes/fees, dates, cancellation terms, exact negotiated commitment, resource revision and allowed data destinations. Changed terms invalidate the preview. Expiry/revocation is checked immediately before claiming a mutation.

External exactly-once execution is not guaranteed. Persist the execution claim, use supported provider idempotency, and reconcile uncertain results. Never clear a claim to blindly resend. Provider acceptance does not establish delivery, reading, attendance or acceptance by every counterparty.

**Use one scheduling authority with reconciliation.** PostgreSQL holds desired automation configuration/revision; Temporal Schedules owns actual due-time execution. A transactional outbox reconciler idempotently creates, updates and pauses schedules, recording applied revisions. Do not add a second independent database timer that can fire the same occurrence.

Uniquely identify a scheduled occurrence by owner, automation, revision and canonical UTC due instant. Commit its accepted-run link and outbox item together. Duplicate deliveries reuse that run. Provider mutations separately use the existing action ledger.

Define timezone, overlap policy, catch-up window, expiry and missed-occurrence behavior. Choose `BUFFER_ONE` for replaceable briefings or `SKIP` when stale work has no value. Purchases/messages are never automatically backfilled. Preview and test DST gaps/folds and timezone changes.

Verify connector callbacks and durably record owner/connection, stable event/version, cursor and receipt time before acknowledging. Reconcile authorized provider state; handle duplicates, delayed/out-of-order events, cursor gaps and expiring subscriptions. Event content is data, not an execution instruction.

Check goal pause/cancel and grant revocation at admission, before paid work and before mutation claim. Already-claimed actions can finish or become uncertain, which the UI must explain. Kill switches block new admissions even while schedule-disable reconciliation is pending.

**Extend storage additively.** No migrations are introduced by this design.

| Proposed record | Fields and invariants |
| --- | --- |
| `cw_goals` | Owner/workspace, objective reference, constraints, success criteria, revision, state, timezone and expiry |
| `cw_goal_run_links` | Goal/run, goal revision, occurrence; unique accepted run per occurrence |
| `cw_automations` | Desired trigger/revision, Temporal schedule ID, applied revision, enabled/expiry |
| `cw_trigger_deliveries` | Owned connection, stable event/occurrence key, cursor, intake/result state and dedupe constraint |
| `cw_execution_grants` | Read/internal-work scope, resources, purpose, processing destinations, limits, expiry/revocation |
| `cw_context_items` | Source/version references, trust labels, provenance, retention/deletion linkage |
| `cw_connector_cursors` | Owned subscription, renewal time, sync cursor and reconciliation state |
| `cw_notifications` | Owner/channel, purpose, dedupe key, content reference, attempts and delivery status |
| `cw_sandbox_sessions` | Owner/run, workload identity, mounts, egress profile, expiry and cleanup evidence |

Reuse existing tasks/artifacts, agent runs/steps/events, invocations/receipts, external actions, connections, memory and audit records. Do not create a second external-action ledger. Preserve owner/workspace identity through every foreign-key path; apply tenant filters before retrieval and recheck at use.

Raw source text, provider reasoning and secrets stay out of Temporal history and normal audit logs. Private context storage has explicit retention and deletion linkage. Schema additions follow expand/migrate/contract; a rollback never drops data required by old workers.

**Add APIs while preserving current routes.** These routes are proposed, not available endpoints.

| Route family | Contract |
| --- | --- |
| `POST /api/v1/goals` | Idempotent owned creation with outcome, criteria, sources and constraints |
| `GET/PATCH /api/v1/goals/{id}` | Owned inspection and revision-checked edits; stale writes conflict |
| `POST /api/v1/goals/{id}/run` | Bounded run under current capabilities and budget |
| `POST /api/v1/goals/{id}/pause`, `resume`, `cancel` | Durable state and trigger reconciliation |
| `POST /api/v1/automations` | Explicit activation of reviewed schedule/event rules and grants |
| `GET /api/v1/notifications` | Durable notification inbox with resumable cursor |
| `POST /api/v1/execution-grants/{id}/revoke` | Invalidate future use and dependent pending work |

Existing task/run/action routes remain valid. SSE/polling resumes using durable cursors; reconnect never creates another run. Fingerprints distinguish accepted idempotent replay from changed input reusing the same key.

**Build context with provenance and deletion.** Separate explicit memory facts, project/document retrieval, connector snapshots and temporary execution state. Start with existing facts plus bounded lexical retrieval; add an evaluated embedding component where semantic retrieval improves task success. PostgreSQL with a vector extension is a possible deployment choice, not a reason to add another database immediately.

Context includes owned source IDs/versions, timestamps, language and trust labels. Only selected projects and consented connector scopes are eligible. Inferred memory is user-reviewable; memory cannot authorize an action. A remembered writing preference is not permission to email somebody.

Deletion invalidates indexes, caches, future prompts and jobs that lost access. Define treatment of generated artifacts and retention-limited backups. Prevent queued sync jobs from resurrecting deleted or revoked sources using generation checks. Do not promise retroactive provider deletion beyond contractual capabilities.

**Keep DeepSeek behind an evaluated gateway.** Preserve backend-only credentials, configurable model IDs, the selected provider and explicit Gemma rollback. Proposed profiles cover writing, planning, drafting and vision. Select by task success, multilingual fidelity, latency and cost; provider model names are not quality guarantees.

Check current API capabilities at release time. Alias changes can alter underlying weights. Record configured/resolved identity where exposed, prompt/tool-schema/configuration hashes, source revision and rollout identity. If versions cannot be pinned, use canaries and requalification. Preserve PR #204's shared planner/quality evidence binding.

Native tool calls and typed JSON decisions are implementation options. The adapter must follow the selected API's tool-call ID, result and reasoning-state protocol. Keep necessary reasoning state encrypted and retention-limited; expose action summaries to users. Schema validity and model self-critique do not establish correctness or permission.

Reserve global/account capacity before calls and fan-out; bound retries/backoff and record known/unknown usage. Account-level quotas apply across workers and API keys. Maintain reserve capacity for interactive writing.

**Treat connectors as registered capabilities.** Each operation declares name/version, schemas, required scopes, supported providers, ownership resolver, data destinations, timeout, quota, retry/reconciliation strategy and receipt validator. The existing code-owned registry remains authoritative. The service catalog is planning material and cannot enable tools.

Prioritize consented calendar/email reading, then Microsoft equivalents and selected document sources. Preserve current approved send/calendar/sharing/publishing paths. Zoom meeting creation is a separate integration. Collaboration, commerce, travel and messaging channels require provider-specific feasibility and consent review.

Use scoped OAuth, audience validation, refresh/revocation handling and narrow worker identities. Remove authentication tokens/reset links from ordinary inbox observations; mailbox access must not silently become login access to unrelated services. MCP is an interoperability option; remote tool descriptions are untrusted and cannot replace application authorization.

**Separate policy, credentials and untrusted execution.** Put the permission service, credential service, trusted connector code and audit sink outside agent-writable environments. Use narrow capabilities tied to owner, run, operation, resources and expiry. Deterministic server state decides authority; an LLM cannot approve exceptions to itself.

All outbound paths use approved adapters or constrained egress. Validate hosts, resolved IPs, redirects, ports, methods and data destinations; block internal infrastructure. An allowed search domain does not authorize leaking private text in a query. Inference and search receive only purpose-authorized data.

Browser sessions are owner-isolated. A broker exposes narrow observation/navigation/actions, conceals credentials and supports secure takeover for login, MFA or CAPTCHA. Pause the agent during user takeover/credential entry. Do not expose arbitrary CDP or page-script execution over credential-bearing pages.

A browser click is not proof of an approved purchase. Use a qualified adapter or bounded site workflow that binds final destination, fields, amount and terms to approval. If that cannot be established, require the user to complete the transaction. Generic browsing does not guarantee every site's transaction coverage.

Generated code runs in disposable isolated compute with CPU/memory/disk/time/network/package limits. Mount only authorized input copies; never host/container sockets, other owners' files or production secrets. Verify exports and cleanup. A generated tool remains sandbox-local until separately reviewed for promotion.

Prompt-injection detection supplements containment and permission checks. Webpages, emails, downloads and retrieved memory cannot modify policy, choose credentials or authorize data export. Attack tests cover both text and visual inputs when vision is enabled.

**Artifacts have quality contracts.** Preserve editable DOCX/PPTX/XLSX and current PDF/TXT/CSV exports. Extend layouts, source grounding, render checks, formula recalculation and iterative revisions. Validate supported languages and target Office applications. Keep existing output limits until new tests support expansion.

Host interactive HTML on an isolated origin with restrictive content policy, sandboxed embedding and no main-application cookies. Generated interfaces get no privileged API bridge. Creating a private webpage and publishing it are distinct capabilities.

**Proactivity requires relevance and delivery controls.** Notifications bind trigger, purpose, owner, dedupe key and delivery state. Apply quiet hours, urgency, digest grouping, expiry and retry limits. Begin with an in-app inbox; add browser/mobile push and optional email after qualification. Keep sensitive content out of normal telemetry.

Suggestions derived from goals/context remain suggestions until the user activates a new automation or approves an action. Users can disable watchers or reduce notifications. Measure usefulness and completed outcomes, not interruption volume.

UI surfaces: writing, chat, goals, active work, approvals, artifacts, connected accounts, memory and activity. Show next due time, partial output, actual blockers and stop/resume controls. Provider failure never appears as successful execution.

**Operate and release with evidence.** Record cost per accepted outcome across model, search, sandbox, rendering, storage, notifications and retries. Apply run/account/global limits. Start with one operated region, and add regional cells only when demand, residency needs and operational ownership justify them.

Exercise backup/restore, deletion, key rotation, worker loss, provider outages, overload, rollback and sandbox cleanup. Application autoscaling does not expand provider quotas. Retain current mandatory fixtures and add human-reviewed outcomes, adversarial tests, recovery proof and task/language-specific cost/latency targets.

Build Shuddho-specific outcomes and policy; use managed commodity infrastructure where it reduces operating burden. Prefer provider APIs for consequential operations when available. Add specialist agents only when evaluation demonstrates useful benefit under shared scope/budget.

External technical references checked on 26 September 2026:

- [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- [DeepSeek models](https://api-docs.deepseek.com/quick_start/pricing/)
- [Temporal Python schedules](https://docs.temporal.io/develop/python/workflows/schedules)
- [Temporal determinism](https://docs.temporal.io/workflow-definition)
- [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Gmail push notifications](https://developers.google.com/workspace/gmail/api/guides/push)
- [MCP security](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)

The proposed records, routes, limits and deployment arrangement are Shuddho design decisions. They do not assert another vendor's security, scale or reliability.
