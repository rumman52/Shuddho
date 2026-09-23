# Shuddho: three implementation parts

Working plan, 13 September 2026. Continue in the existing `rumman52/Shuddho` repository. Keep the writing editor useful throughout the transition.

## Decisions and implementation reality

| Kind | Statement |
| --- | --- |
| Product decision | One AI coworker for everyday and professional work across languages, documents, communication, and productivity. |
| Product decision | Preserve free writing assistance. Agent pricing and paid writing quotas are not decided here. |
| Model decision | DeepSeek is the selected API provider. The model ID remains configurable. |
| Technical direction | Qwen can later be a language specialist after deployment, evaluation, and cost/latency checks. It is not serving this branch. |
| Repository fact | The active editor is React/Vite in `apps/web-editor`; the writing service is FastAPI in `services/api/shuddho_api`. Legacy Node and Next applications also exist. |
| Repository fact | Feedback uses SQLite. AI caches and background reviews use process memory and threads. They are not durable workflows. |
| Assumption | Start with one operational region and managed infrastructure; select providers and residency from actual customer needs. |
| TODO | Measure language quality, peak demand, task cost, provider capacity, and regional latency. One billion people is a product ambition, not a demonstrated capacity. |

## The three parts

| Part | Outcome | Current status |
| --- | --- | --- |
| 1. Reliable writing foundation | Existing editor + configurable DeepSeek + correct suggestion application + clear failure states | Merged in PR #100; CI passed; live API and staging verification pending |
| 2. Coworker foundation | Authenticated workspace, durable tasks/files, and one useful document workflow | Merged in PR #101; CI passed; feature flags remain off pending the staging gates in the Part 2 report |
| 3. Full services and measured scale | Remaining skills, approved integrations, agent runtime, reliability operations, and regional expansion | Waves A/B/C and the first Wave D approved-action increment are merged through PR #109; Agent Runtime foundation is implemented in the next disabled-by-default increment; staging and later execution waves remain pending |

These are three release tracks with smaller steps, not a single rewrite or three enormous launches.

## Part 1 — reliable writing foundation

### Delivered scope

1. Preserve local Bangla rules, dictionaries, spelling, punctuation, and spacing checks.
2. Introduce DeepSeek through the existing provider boundary; keep explicit Gemma rollback.
3. Validate multilingual review JSON, exact text spans, and completion status. Preserve empty-string deletions.
4. Keep timeout and cancellation active until a JSON response body finishes. Bound the backend's DeepSeek body and overall call duration.
5. Show provider failures separately from a successful review with no suggestions.
6. Carry profile ID, document ID, revision, personal dictionary, and writing mode through the editor API.
7. Persist editor preferences per legacy profile and repair the feedback route mismatch.
8. Build corrected previews from validated suggestions. Applying an edit remains the user's action.
9. Repair the existing test collection and dependency lock, and add regression coverage.

See [Part 1 details](PART_1_WRITING_FOUNDATION.md) for exact files and release verification.

### Release gate

- Backend tests, editor tests, type checking, and builds pass.
- On staging, verify one successful paid DeepSeek call, one failure path, repeated suggestion applications, deletion, and stale response cancellation.
- Verify Bangla, English, a mixed-language example, and an RTL example in the actual browser; record limitations instead of claiming all languages are validated.
- Confirm secrets exist only on the backend and the configured provider is intentional.
- Do not expose the legacy profile/job API as the security boundary for a new public multi-user coworker.

## Part 2 — coworker foundation

See [the Part 2 implementation and deployment report](PART_2_COWORKER_FOUNDATION.md) for the implemented scope, exact modules, limits, account boundary and remaining release gates.

### First workflow

**“Turn this document or these notes into a professional report and an email draft in my chosen language.”**

The user provides notes or an allowed file, describes the outcome, and reviews the resulting report and email. The system asks a question only when missing information changes the result. A draft email is not a sent email.

### Architecture to implement

```mermaid
flowchart TD
  UI["Writing and coworker workspace"] --> API["Authenticated FastAPI boundary"]
  API --> Writing["Writing checks"]
  API --> Tasks["Task service"]
  API --> DB["Managed PostgreSQL"]
  Tasks --> Queue["Durable workflow engine"]
  Queue --> Worker["Document worker"]
  Worker --> Files["Private object storage"]
  Worker --> Models["Model gateway"]
  Writing --> Models
  Models --> DS["DeepSeek API"]
  Worker --> DB
  DB --> Events["Task progress and results"]
  Events --> UI
```

### Implementation order

1. **Authenticated account boundary.** Choose a managed identity provider; validate sessions on the server. Derive ownership from authentication, never a client `user_id`. Scope queries, files, tasks, events, preferences, and caches by account/workspace. Add ownership tests before exposing new endpoints.
2. **Durable data.** Add PostgreSQL migrations for workspaces, documents and versions, tasks and steps, artifacts, usage, and audit events. Migrate legitimate preferences after account association; do not automatically claim an anonymous profile belongs to a logged-in account. Store binaries in private object storage with short-lived authorized downloads.
3. **Durable workflow execution.** Use a managed workflow engine such as Temporal through one adapter. Compare hosting cost with the expected workload before provisioning. Persist task state independently of HTTP connections. Separate interactive writing capacity from file/agent workers. Recover after worker restarts and retry only retryable operations within a budget.
4. **File intake.** Start with TXT, DOCX, and text-based PDF, using explicit size/page limits. Detect file type, scan where available, and parse in restricted workers. Scanned PDFs require a separate OCR path; indicate this instead of pretending empty extraction is success. Treat file contents as data, not execution instructions.
5. **Deterministic workflow.** Extract → understand the request → draft report/email → validate → export. Use DeepSeek for the reasoning/writing steps that need a model, with bounded calls. A rule-based intent route is enough for the initial workflow; no open-ended planning loop is necessary.
6. **Document artifacts.** Create DOCX/PDF through document libraries and templates. Store output versions, source references, and task association. Report success only after an artifact exists, passes basic validation, and is accessible to its owner.
7. **Responsive task UI.** Return a task ID quickly; show queued/running/needs-input/completed/failed/cancelled status. Use SSE with a resumable event cursor and polling fallback. Persist tasks so refresh/reconnect does not restart work. Keep typing, local recovery, and the writing pane responsive while a task runs.
8. **Usage budgets.** Record tokens, latency, retries, and artifact cost per task. Enforce account budgets and concurrency before sending a paid request. Keep the free writing path available under a separate quota policy; this plan does not promise unlimited free inference.

### Proposed contracts — new, not existing routes

| Contract | Purpose |
| --- | --- |
| `POST /api/v1/tasks` | Authenticated task submission with instruction, output language, owned document IDs, and an idempotency key; returns 202 and task ID |
| `GET /api/v1/tasks/{id}` | Current owner-authorized status, progress, result artifacts, and failure information |
| `GET /api/v1/tasks/{id}/events` | Resumable progress events; no hidden chain of thought or credentials |
| `POST /api/v1/tasks/{id}/cancel` | Cooperative cancellation; stop new steps and make any completed work visible |
| Upload initialization/finalization | Enforce ownership and limits before an uploaded file can enter a workflow |
| Artifact download | Check ownership and return a short-lived download URL |

Each task carries account/workspace, task ID, workflow version, request ID, output language, input document versions, call/time budget, and result artifact IDs. Event sequencing and idempotency are server-enforced. An LLM response is never proof that an external action succeeded.

### Done when

- A real user can log in, submit a supported document, and download an editable report and email draft.
- Restarting a worker or refreshing the page preserves task progress and produces no duplicate artifact generation beyond the defined retry policy.
- Cross-account task, file, preference, and event reads are rejected.
- Empty files, unsupported scans, provider outages, quota exhaustion, and cancellation produce understandable terminal states.
- A curated multilingual evaluation records source fidelity, writing quality, formatting, task success, latency, and cost. No unmeasured universal language guarantee.

## Part 3 — remaining services and global operation

Wave A is implemented in [the Part 3 work-services report](PART_3_WORK_SERVICES.md). It adds seven services to the existing report-and-email workflow, with typed output and native downloads. Enable it only after the coordinated API/worker rollout and staging checks described there.

### Skill rollout

| Wave | Services | Implementation requirement |
| --- | --- | --- |
| A | Email drafts, social posts, careers/CVs, official documents, meeting agendas/minutes, daily/personal plans | Reuse the authenticated text/document workflow. Keep user facts and deadlines explicit; mark missing facts rather than inventing them. |
| B | Presentations, spreadsheets, broader file transformations | [Implemented scope and release gates](PART_3_PRESENTATIONS_SPREADSHEETS.md): existing durable workers create editable PPTX/XLSX, charts, notes and exports. Bounded CSV/XLSX/PPTX snapshots; native rendering and recalculation checks. |
| C | Web research, travel research, comparisons | [Implemented scope and gates](PART_3_RESEARCH.md): one explicit search, provider-retrieved page text, validated citation excerpts, source dates and cited native reports. Web content cannot authorize tools or account changes. |
| D | Calendar events, reminders, approved email sending, document sharing, approved social publishing | [First increment](PART_3_APPROVED_ACTIONS.md): Google email sending and single calendar events, encrypted OAuth connections, exact previews, explicit approval, durable execution, receipts and audit history. Reminders, sharing and social publishing remain later increments. Live provider validation is required before enabling. |

Reminders and calendar events require a persisted timezone-aware schedule. A generated checklist alone does not create a reminder. Reading transcripts does not imply audio transcription; add and evaluate that capability separately.

### Agent Runtime foundation

The first goal-driven runtime increment is documented in [the Agent Runtime foundation report](PART_3_AGENT_RUNTIME_FOUNDATION.md). It adds owned agent runs, steps, typed tool invocations, receipts, resumable events and a server-owned tool registry.

PR #111 adds the code-owned deterministic planner, crash-safe agent outbox and Temporal `AgentWorkflow`. PR #112 adds approval-aware Gmail/Calendar steps that pause and resume through the existing immutable action approval path. PR #113 adds [structured Agent Memory](PART_3_AGENT_MEMORY.md) with explicit user-owned facts, scoped runtime use, versioned provenance, expiry and hard deletion.

PR #114 adds [bounded intelligent planning](PART_3_INTELLIGENT_PLANNER.md): the model may select only server-provided non-consequential tool names; Shuddho reconstructs and validates executable arguments. Initial planner failures fall back to deterministic routing, and a run may automatically replan once only when an unstarted capability becomes unavailable.

PR #115 adds [typed Agent Step Handoffs](PART_3_AGENT_HANDOFFS.md). A later non-research task may consume a bounded live source derived from the nearest prior completed task in the same owner/run. Handoff text is not copied into Temporal history, task notes, tool arguments or durable receipts; only provenance is persisted.

PR #116 adds [bounded incomplete-result replanning](PART_3_OUTCOME_REPLAN.md). The existing structured `needs_input` state may trigger the run's single automatic replan for later unstarted steps only; completed work remains immutable and no draft content is exposed to the planner.

PR #117 adds [bounded multi-source handoffs](PART_3_MULTI_HANDOFFS.md): a later non-research task may consume up to two server-selected prior completed task results under one shared handoff byte budget.

PR #118 adds a [bounded dependency graph](PART_3_DEPENDENCY_GRAPH.md). Durable dependency metadata is derived by trusted server code after plan validation; model-selected step IDs and arbitrary DAG edges remain out of scope.

PR #121 adds [bounded parallel execution](PART_3_PARALLEL_EXECUTION.md): new runs may use the versioned `shuddho_agent_run_v2` path when both graph and parallel flags are enabled, with server-owned readiness, bounded fan-out/fan-in, serialized approved actions, deterministic failure behavior, and v1 fallback when the flag is off.

PR #123/#124 add [Agent Evaluation and Production Staging Gates](PART_3_AGENT_EVAL_STAGING_GATES.md): CI-safe routing evaluation, opt-in live planner evaluation, and an explicit machine-readable GO/NO-GO gate before enabling Coworker or Agent Runtime for production traffic.

PR #126 adds [live infrastructure probes](CONTROLLED_STAGING_LIVE_PROBES.md): non-destructive validation for managed identity JWKS, TLS PostgreSQL + migrations, private object storage round trips, Temporal namespace connectivity, and optional live DeepSeek planner evaluation.

PR #127 adds the [authenticated API exercise](CONTROLLED_STAGING_API_EXERCISE.md): two-account owner-isolation checks across workspace/document/task/event/cancel boundaries plus an optional live artifact authorization/download path that can promote identity and storage evidence from partial to passed.

PR #128/#129 add the [Temporal recovery exercise](CONTROLLED_STAGING_TEMPORAL_RECOVERY.md): a real AgentWorkflow v2 two-branch fan-out/fan-in run with a deliberate staging worker replacement, exact child-task idempotency checks, persisted dependency timing checks, and fail-closed promotion of temporal, parallel_restart and fan_in evidence.

PR #130 adds the [isolated backup/restore drill](CONTROLLED_STAGING_BACKUP_RESTORE.md): synthetic Coworker database/object state is snapshotted through real managed backup mechanisms, restored into separate targets, and accepted only when relational records plus private object bytes match the pre-backup manifest and SHA-256.

PR #131/#132 add [retention, deletion and orphan cleanup](CONTROLLED_STAGING_RETENTION_DELETION.md): first-class administrative task/account erasure, durable referenced-object inventory, dry-run and age-bounded orphan cleanup, and a synthetic staging exercise that promotes the deletion gate only after database rows and private objects are actually removed.

PR #133 adds the [Agent v2 → v1 feature-flag exercise](CONTROLLED_STAGING_FLAG_ROLLBACK.md): the real dispatcher must record v2 before rollback, current workers keep both workflow identities registered, parallel execution is disabled without schema downgrade, and a newly dispatched Agent run must be recorded by Temporal as v1 while the prior v2 execution remains valid.

PR #134 adds [live Tavily Research validation](CONTROLLED_STAGING_LIVE_RESEARCH.md): Shuddho's real Tavily adapter must return bounded provider-retrieved page evidence with valid provenance and exact-quote validation, then one authenticated deployed Research task must complete through the real workflow with cited sources, accounting evidence and owner-authorized non-empty artifacts before the conditional research gate can pass.

PR #135 adds [live Google approved-action validation](CONTROLLED_STAGING_LIVE_GOOGLE_ACTIONS.md): one real staging Gmail send and one real primary-calendar event must remain inert before exact approval, reject a wrong preview hash, preserve immutable preview/hash through execution, produce exactly one execution audit path, and finish with confirmed Google receipts before the conditional actions gate can pass.

PR #136 adds the [controlled cohort GO/NO-GO gate](FINAL_CONTROLLED_COHORT_GATE.md): combine completed staging evidence with an explicit rollout manifest, bounded first-cohort size, capability dependencies, exact kill switches, monitoring references and incident ownership.

PR #137 adds [server-enforced cohort admission](SERVER_COHORT_ADMISSION.md): a backend-only account allowlist with a hard cohort-size ceiling, fail-closed configuration validation, denial before workspace provisioning, and a live invited-vs-fresh-non-member staging proof.

PR #138 adds the [controlled cohort health and stop gate](CONTROLLED_COHORT_HEALTH_GATE.md): a read-only aggregate health snapshot over the enforced cohort plus explicit thresholds for queue age, task/provider/Agent/Research/action failures, model latency, token use, storage and uncertain consequential actions. It returns `CONTINUE_COHORT` or `STOP_ROLLOUT` and exposes the existing kill switches without giving application code deployment-admin credentials.

PR #140 adds the [controlled cohort observability export](CONTROLLED_COHORT_OBSERVABILITY.md): the same health snapshot/evaluator produces an atomic, label-free OpenMetrics textfile plus a small operator JSON status for external schedulers, dashboards and alerts. No public metrics endpoint or deployment-admin credentials are added.

PR #141 adds [controlled cohort canary progression](CONTROLLED_COHORT_CANARY_PROGRESSION.md): sustained sanitized health history, freshness, monitoring continuity and real task/provider/Agent sample minimums govern whether the current stage is HOLD, ELIGIBLE_FOR_EXPANSION or STOP_ROLLOUT. The default path is 5 → 10 → 25 users; no account is added automatically.

PR #142 adds the [tamper-evident controlled cohort release ledger](CONTROLLED_COHORT_RELEASE_LEDGER.md): every HOLD, expansion-eligibility, approved-stage, or STOP decision binds the exact rollout manifest, canary plan, progression decision and operator status through SHA-256 hashes, a chained entry hash, and an operations-only HMAC.

PR #143 adds [controlled cohort rollback completion](CONTROLLED_COHORT_ROLLBACK_COMPLETION.md): a STOP is not considered resolved until the selected deployment kill switch is actually off, cohort work/outboxes are drained, consequential-action uncertainty is reconciled, a fresh post-rollback health status is clean, and a schema-v2 `rollback_completed` event is chained to the exact earlier STOP evidence without rewriting schema-v1 history.

PR #144 adds [controlled cohort recovery verification](CONTROLLED_COHORT_RECOVERY_VERIFICATION.md): Coworker may return only after a completed global rollback, exact deployed capability flags match the approved rollout manifest, cohort membership remains within the current canary stage, invited/denied access boundaries still hold, one real synthetic report/email workflow produces an authorized artifact, and a fresh post-smoke health snapshot is clean. A schema-v3 `recovery_verified` ledger event binds the recovery evidence to the original STOP and rollback-completion chain.

PR #145 adds a ledger-verified post-recovery observation epoch to [controlled cohort canary progression](CONTROLLED_COHORT_CANARY_PROGRESSION.md): historical STOP evidence remains immutable, but only health generated after the recorded recovery verification may count toward later expansion. This increment also tightens the epoch boundary so health can count only after the recovery event itself is committed to the verified ledger.

PR #146 adds [controlled cohort capacity qualification](CONTROLLED_COHORT_CAPACITY_QUALIFICATION.md): the fully earned 25-user stage must provide fresh simulated-provider infrastructure load evidence, a smaller budgeted real-provider load sample, demonstrated concurrency reserve, and a clean post-load health status before it can become `ELIGIBLE_FOR_CAPACITY_REVIEW`. Capacity qualification does not authorize cohort expansion; the next stage must be chosen from measured demand, provider quota, cost, error budget and operations staffing.

PR #147 adds a [curated multilingual Coworker quality gate](MULTILINGUAL_COWORKER_QUALITY_EVAL.md): deterministic CI scoring plus an opt-in live DeepSeek run measure schema compliance, requested language, exact fact preservation, unsupported-claim absence, provenance references, missing-information behavior, latency and token use on synthetic English, Bangla, Spanish and Arabic cases. This becomes required production-staging evidence before broader enablement. It is a bounded regression gate, not a claim of universal language quality.\n\nPR #148 adds [bounded cohort scale review](CONTROLLED_COHORT_SCALE_REVIEW.md): a human-proposed next stage must bind fresh capacity qualification, fresh live multilingual quality evidence, provider quota headroom, approved cost headroom, remaining error budget, confirmed on-call staffing, and a fresh post-evidence operator status. The gate can only return eligibility for a bounded expansion; it never changes cohort membership or production flags automatically.

PR #149 adds [bounded scale activation verification](CONTROLLED_COHORT_SCALE_ACTIVATION.md): after a separately approved deployment change, Shuddho verifies that backend cohort enforcement remains enabled, the deployed cohort ceiling exactly matches the reviewed ceiling, membership expanded but did not exceed that ceiling, an allowed account is admitted, a fresh non-member is denied before provisioning, and post-deploy health is clean. A schema-v4 release-ledger event then binds the reviewed decision, deployment record, operator status, and activation proof into the existing tamper-evident chain.

PR #150 adds [post-scale cohort observation](POST_SCALE_COHORT_OBSERVATION.md): a schema-v4 activation creates a new ledger-verified observation epoch for the dynamically reviewed stage. Only post-activation health counts; overflow, stale health, or any STOP fails closed. Sustained enrollment, healthy windows, monitoring continuity, and real task/provider/Agent samples produce `ELIGIBLE_FOR_REQUALIFICATION`, which lets the existing capacity qualification gate run again for that exact dynamic stage. This closes the repeatable scale loop without hard-coding 25 → 40 → 80 or any other future cohort sizes.

PR #151 adds a [shared provider capacity governor](PROVIDER_CAPACITY_GOVERNOR.md): document drafts and intelligent-planner calls acquire short-lived PostgreSQL-backed leases before external model calls. One transaction-scoped admission lock enforces global concurrency/token reserve and per-workspace fair-share ceilings across all worker replicas. Capacity pressure is retryable backpressure rather than a permanent task failure, abandoned leases expire after worker loss, and aggregate lease pressure is exported through cohort health/OpenMetrics.

PR #152 adds [adaptive provider quota and cost policy](ADAPTIVE_PROVIDER_POLICY.md): all provider call types reserve against one atomic global UTC-day token budget, with known usage settling conservative reservations and unknown outcomes retaining their full charge. A deterministic policy compiler binds the reviewed scale decision, scale-review request and capacity qualification, then proposes bounded concurrency, reserve, daily-budget, fair-share and lease settings from demonstrated capacity, provider quota, approved cost envelope and current policy. It never mutates production; deployment remains an explicit reviewed change.

The next control-plane increment adds [provider policy activation verification](PROVIDER_POLICY_ACTIVATION.md): after an approved policy deployment, Shuddho verifies the exact deployed runtime limits, current aggregate provider pressure and fresh post-deploy health. A schema-v5 `provider_policy_verified` event binds that evidence into the existing release ledger. Bounded cohort scale activation then requires that exact ledgered provider-policy proof before cohort membership may expand, preventing scale-out against stale or unreviewed runtime limits. PR #153 adds provider-policy activation verification and schema-v5 release-ledger evidence, making verified runtime provider policy a prerequisite for bounded cohort expansion.

The next action-safety increment adds a [connector-neutral consequential-action policy](CONSEQUENTIAL_ACTION_POLICY.md): every external mutation kind must register a typed provider/capability/destination/reconciliation contract. Prepared actions carry a server-owned approval-scope manifest binding identity, payload SHA-256, destinations, policy and expiry; approval and execution revalidate it before any provider mutation. Existing Google email/calendar behavior remains compatible, while Outlook, document sharing, social publishing, attachments and other future connectors cannot bypass this boundary.

PR #154 adds the connector-neutral consequential-action policy registry and v2 approval-scope contract for every new external mutation.

The next connector increment adds a disabled-by-default [Microsoft Graph email/calendar adapter](MICROSOFT_GRAPH_ACTIONS.md): OAuth state is provider-bound, Microsoft Graph implements the same adapter interface as Google, and approved email/calendar actions reuse the exact same immutable preview, explicit approval, committed claim, identity recheck, receipt and uncertain-outcome boundaries. Microsoft frontend exposure and live staging remain separate gates.

The next release-safety increment adds [controlled live Microsoft action validation](CONTROLLED_STAGING_LIVE_MICROSOFT_ACTIONS.md): one real Microsoft Graph email and one real calendar event must pass provider-bound v2 approval-scope validation, wrong-hash rejection, no-auto-approval checks, immutable preview verification, single execution audit, and Microsoft-specific receipt validation. The new `microsoft_actions` staging gate is independent from Google `actions` evidence; frontend Microsoft exposure remains blocked until it passes.

The next frontend increment adds a default-off Microsoft provider selector and secure `/oauth/microsoft/callback` handler. It validates Microsoft login origin/path, exact state and exact same-origin callback before redirect, stores only state/account in session storage, calls only fixed backend Microsoft start/finish routes, and preserves provider identity when editing saved actions. The UI remains Google-only unless `VITE_MICROSOFT_ACTIONS_ENABLED=true`, so shipping the code does not itself authorize Microsoft rollout.

The next control-plane increment adds [Microsoft rollout activation verification](MICROSOFT_ROLLOUT_ACTIVATION.md): the exact live `microsoft_actions` staging evidence is SHA-bound to an approved deployment record, backend Google/Microsoft action flags are checked from the deployed runtime, and the deployed frontend is verified through a build-generated rollout manifest containing the exact source revision plus Coworker/Microsoft UI flags. Fresh post-deploy operator health is required before the rollout becomes `microsoft_rollout_verified`.

The following release-evidence increment extends the existing tamper-evident controlled-cohort ledger with schema v6 `microsoft_rollout_verified`. The exact Microsoft staging evidence, reviewed deployment, post-deploy operator status, and activation artifact are chained into the same release ID/stage already used for production cohort control; duplicate activation recording and unattached stage claims fail closed.

The next enforcement increment makes bounded production cohort activation consume that schema-v6 proof whenever Microsoft actions are deployed. Google-only releases remain unchanged; Microsoft-enabled scale progression fails closed unless the exact `microsoft_rollout_verified` artifact has one matching schema-v6 ledger event for the current stage, and the resulting bounded-scale activation artifact records that Microsoft proof SHA-256.

The following recovery-safety increment applies the same invariant after global rollback: if Microsoft actions are re-enabled during recovery, recovery fails closed unless a fresh post-rollback `microsoft_rollout_verified` artifact is ledgered as schema v6 after the exact schema-v2 rollback-completion event. The schema-v3 recovery artifact binds that Microsoft proof by SHA-256.

The next release-admission increment makes the final controlled-cohort manifest provider-aware. Legacy action releases remain Google-only; a release that explicitly declares Microsoft must also pass the independent `microsoft_actions` live gate before `GO_CONTROLLED_COHORT`, and the decision records the exact approved provider set.

The next bounded Agent/action bridge allows the intelligent planner to select only opaque handles for user-attached, still-unapproved email/calendar drafts. Shuddho resolves handles server-side, releases unselected pending drafts, preserves already-approved actions, and keeps explicit approval/execution unchanged behind a disabled-by-default `SHUDDHO_AGENT_ACTION_SELECTION_ENABLED` gate.

The following staging increment adds an executable, non-destructive live proof for that boundary: two synthetic attached drafts are planned through the deployed intelligent Agent, exactly one selected draft must remain bound and paused at `awaiting_approval`, the unselected draft must be released unchanged, and no approval/provider receipt may exist. Passing evidence is written as `action_selection` for the final release gate.

The next activation-control increment binds that exact timestamped `action_selection` staging evidence to a reviewed production deployment, verifies Coworker/Agent/planner/actions/action-selection/cohort runtime controls from the deployed backend, requires fresh clean post-deploy cohort health, and emits `action_selection_verified` before the feature is treated as production-activated.

Broader model-created external actions and connector expansion remain later increments.

### Consequential actions

Bind approval to the exact recipients, content, attachments, account, destination, and time. If the payload changes, request fresh approval. Record an idempotency key before execution. On an uncertain network outcome, reconcile using the external provider's receipt/status before retrying. Display sent/published/scheduled only after a confirmed provider result.

Use one typed tool registry with per-tool authorization, argument schemas, allowed destinations, deadlines, and audit records. External documents, email threads, and search results never grant permissions. Avoid arbitrary shell or unrestricted browser execution in the product.

### Scale from observed demand

1. Cache and distribute static UI through a CDN. Keep editor work local where possible. This improves reach but does not eliminate cross-region model latency.
2. Run stateless API replicas and independent writing/agent worker pools. Scale workers from queue age and active task demand, with per-account fairness and backpressure.
3. Use database connection pooling, indexes based on real queries, object storage for large files, and lifecycle/deletion policies. Add a cache only for a demonstrated need. Private data keys must include ownership and version context.
4. Set separate latency/error objectives for local editing, quick checks, model review, task start, and artifact completion. Track p50/p95/p99 by region and language. A healthy HTTP endpoint does not prove a healthy model provider.
5. Load-test the application with a simulated model at realistic delays/errors, then run budgeted end-to-end capacity tests. Account for provider account-level capacity; new API keys do not create unlimited independent capacity.
6. Add regional cells only when demand, residency obligations, and operations justify them. Each cell owns its customers' primary data, queues, workers, and provider configuration. Route a workspace to its home region; avoid cross-region database calls on every edit.
7. Exercise backups, restores, worker loss, provider outages, overload shedding, key rotation, staged rollout, and rollback. Expansion requires an operational owner and measured reserve capacity.

### Capacity worksheet

Use measured inputs instead of sizing directly from “one billion users”:

- Peak writing requests/second = active sessions × checks per session/second.
- Approximate concurrent model calls = model requests/second × mean call duration in seconds, plus planned reserve. Bursts require separate testing.
- Agent worker demand depends on task mix, file sizes, number of model/tool calls, execution duration, and user concurrency.
- Total cost includes model tokens, retries, storage, database, workers, document rendering, search/OCR, and network transfer.

A billion registered accounts, a billion monthly users, and a billion simultaneous users require very different systems. No repository change can establish “zero lag” or a billion-user capacity claim; release targets must be measured and funded.

## Source notes

DeepSeek's current official examples use `deepseek-flash`; model selection remains environment-configurable because aliases can change. [DeepSeek API quick start](https://api-docs.deepseek.com/)

For writing review, JSON-object mode and explicit non-thinking mode are supported. JSON-mode responses may still be empty or truncated, which is why Part 1 validates completion and body content. [JSON output](https://api-docs.deepseek.com/guides/json_mode/), [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/)

Provider concurrency is a separate constraint from application replicas. Verify account limits before capacity planning. [DeepSeek rate limits and isolation](https://api-docs.deepseek.com/quick_start/rate_limit/)

The service boundaries, rollout sequence, and release gates above are Shuddho design choices. They do not imply that the planned infrastructure is already installed or provisioned.
