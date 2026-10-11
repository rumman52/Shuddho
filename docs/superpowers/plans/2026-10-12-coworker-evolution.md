# Shuddho Coworker Evolution Implementation Plan

> **For agentic workers:** Use the installed `shuddho-engineering` skill and, where available, `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax. Delegate only when the session authorizes delegation.

**Goal:** Turn the existing bounded coworker into a continuous, resumable, permission-controlled product, and qualify selected workflows for production.

**Architecture:** Reuse PostgreSQL application records, Temporal execution, existing outboxes and the external-action ledger. Add owner-scoped conversation/workspace projections and narrowly registered tools; keep deterministic authorization outside reasoning and isolated execution.

**Tech stack:** Existing Python/FastAPI/Pydantic/SQLAlchemy/Temporal, PostgreSQL, private object storage, React/TypeScript, browser and sandbox workers. Preserve selected DeepSeek and explicit Gemma rollback.

**Spec:** `docs/coworker-roadmap/SPEC.md`

## Global constraints

- Preserve free multilingual/Bangla writing, local fallbacks and honest AI diagnostics.
- No raw secrets in frontend, prompts, commits, ordinary logs or Temporal history.
- No silent provider switch; no general payment/transfer authority.
- Exactly one existing ExternalAction execution identity per approved transaction; uncertain mutations are never blindly resent.
- Owner/resource/version/grant checks at admission and use; memory never grants authority.
- Additive migrations and old-history compatibility; new capabilities default-off under canonical release controls.
- Distinguish implemented, repository-verified, staging-verified, production-qualified and activated.
- Required safety suite runs with coworker dependencies and zero skips.
- Existing stricter quality thresholds apply; the proposed pilot human-accepted outcome target is >=90%, reported with sample sizes.
- Availability objective 99.9% must be defined/measured separately from chaos pass rate.

## Review focus

- Concurrent identical requests and changed input reusing a key: same accepted identity versus conflict (CW-01, CW-05, CW-06).
- Accepted provider mutation followed by lost response/process death: uncertainty/reconcile without resend (CW-02, CW-14..CW-16).
- Revoked/deleted source while work is queued: no cached resurrection or further use (CW-08, CW-12).
- Stale steering/cancellation and delayed tool results: version conflict; cancelled run stays cancelled (CW-06, CW-07).
- Untrusted webpage/code/artifact with indirect secret/data-export instruction: enforce ownership, grants, egress and isolated origin independently of the model (CW-09..CW-11, CW-17).

## How to execute

Run one task per reviewable PR. Refresh baseline, inspect exact interfaces and reuse existing tests before edits. New filenames/interfaces below are proposed, not existing runtime APIs. If fresh main already implements a task, verify it and skip duplicated implementation. Reassign proposed migration numbers only if main has advanced.

For coding tasks: establish the contract/reproduction, run meaningful failing regressions, implement the smallest patch, run focused and required CI, then commit a precise checkpoint. For operational tasks: do not create a fake failing test or fabricate evidence; prepare the collector, execute the real scenario with authorized access, and record expected/observed results.

No production activation or paid provisioning is authorized by this plan alone.

---
## CW-01: Repair chaos contracts and mandatory collection

**Dependencies:** None; inspect baseline and existing tests first.

**Files:**
- Modify: tests/test_transaction_chaos_qualification.py
- Modify: .github/workflows/ci.yml
- Modify: docs/phase11-transaction-chaos-qualification.md

**Interfaces:** Consume existing TransactionRepository.bind_external_action(owner, transaction_id, expected_revision, external_action_id), ActionRepository.approve(owner, action_id, preview_hash), claim_execution(action_id), and ActionService.execute(action_id). Reuse tests/test_transaction_reconciliation.py::bound_action instead of invented connection/evidence fixtures. Produce executable safety regressions and mandatory CI collection; no new production API.

**Acceptance:** same binding -> same link; different binding -> transaction_execution_already_bound; expired approval/claim -> zero provider calls; accepted-then-timeout -> uncertainty or exact reconciliation, never resend; no nonexistent advance_execution or invalid ORM fields.

- [ ] **Step 1:** Run the current file with coworker dependencies and retain exact initial failures/skips. Compare same-binding replay with existing working reconciliation tests.
- [ ] **Step 2:** Replace invalid test fixtures/assertions with production contract cases. Record all 16 expected fault outcomes and mark remaining evidence pending.
- [ ] **Step 3:** Add this file to the heavyweight coworker pytest invocation. Ensure a required CI job reports collected test counts and fails on skips in this mandatory file.
- [ ] **Step 4:** Run focused transaction suites; inspect exact-head coworker CI; preserve production idempotent behavior.
- [ ] **Step 5:** Commit tests/CI/document repair and record exact revision and residual CW-02 gaps.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_transaction_chaos_qualification.py tests/test_transaction_reconciliation.py tests/test_transaction_domain.py tests/test_transaction_terms.py -q -rs
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-02: Prove failure outcomes across dispatch and recovery

**Dependencies:** CW-01.

**Files:**
- Create: tests/test_transaction_chaos_postgres.py
- Create: tests/test_transaction_chaos_temporal.py
- Create: scripts/phase11_chaos.py
- Modify: tests/test_coworker_postgres.py, tests/test_coworker_temporal.py
- Modify: .github/workflows/ci.yml and docs/phase11-transaction-chaos-qualification.md
- Modify only if a reproduced gap requires it: services/coworker/actions.py, action_repository.py, tool_execution.py, worker.py, workflow.py

**Interfaces:** Propose FaultCase(case_id, fault, boundary) and CaseEvidence(case_id, source_sha, action_id, approved_identity, provider_dispatch_count, provider_mutation_count, state, receipt_sha256). run_case(case: FaultCase, harness: ChaosHarness) -> CaseEvidence. The harness uses public API requests, a counted provider stand-in, real PostgreSQL and Temporal/process control. Stand-in evidence is integration evidence, not live provider certification.

**Acceptance:** All 16 faults listed in ROADMAP; barrier-controlled two-worker claim races; process kill before/after claim, provider application and DB receipt commit; API duplicate races; Temporal outage; DB/S3 outages; one mutation per approved identity. Assert logical request counters and provider-applied mutations separately.

- [ ] **Step 1:** Define versioned case/evidence schemas and dispatch boundaries; reuse existing recovery harnesses. Count applied mutations independently of DB ledger rows.
- [ ] **Step 2:** Add failing cases for uncovered boundaries, including accepted-then-dropped response. Run against PostgreSQL/Temporal with process interruption rather than SQLite-only calls.
- [ ] **Step 3:** Repair only demonstrated production defects; keep uncertainty and read-only reconciliation. Never retry all provider failures generically.
- [ ] **Step 4:** Run all cases and required CI with zero mandatory-case skips; compare expected versus observed states and budget behavior.
- [ ] **Step 5:** Commit harness/results contract, update matrix by evidence level, and leave live-provider/SLO qualification unclaimed.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_transaction_chaos_postgres.py tests/test_transaction_chaos_temporal.py tests/test_transaction_chaos_qualification.py -q -rs
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-03: Refresh staging prerequisites and freeze identity

**Dependencies:** CW-01; named authorized staging environment and secure secret references.

**Files:**
- Inspect/reuse: docs/PA10_CONTROLLED_STAGING_CHECKPOINT.md, PA10_STAGING_RELEASE_FREEZE.md
- Inspect/reuse: scripts/staging_prerequisite_preflight.py, staging_release_freeze.py
- Inspect/reuse: infra/render.staging.yaml and infra/docker-compose.yml
- Modify: canonical staging checkpoint with fresh evidence; repair scripts only for reproduced defects

**Interfaces:** Consume existing preflight and PREPARE/deploy/VERIFY freeze contract. Produce a reviewed source/API/worker/model/rollout identity with status=frozen before final qualification collection. Do not invent CLI switches; read --help and current runbooks.

**Acceptance:** Actual Temporal authentication and worker polling; PostgreSQL access; private S3 upload/read/delete and owner denial; matching API/worker release; missing access -> blocked, no activation.

- [ ] **Step 1:** Refresh recorded billing/worker/Temporal/storage/auth blockers through permitted read-only checks; do not assume the historical checkpoint is today's state.
- [ ] **Step 2:** Prepare secure secret references and selected synthetic identities; complete permitted independent fixes. Report human/provider prerequisites with owners.
- [ ] **Step 3:** Use reviewed non-production provisioning only when separately authorized; validate actual worker readiness and configured dependencies.
- [ ] **Step 4:** PREPARE exact candidate, deploy matching source, VERIFY and retain frozen-release evidence.
- [ ] **Step 5:** Commit checkpoint with fresh deployed identity and links; exclude preliminary diagnostics from final release evidence.

**Verification entry points:**
```bash
uv run --extra coworker python -m scripts.staging_prerequisite_preflight --help
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-04: Qualify bounded baseline workflows

**Dependencies:** CW-02/CW-03 for operational qualification.

**Files:**
- Reuse: scripts/staging_api_exercise.py, staging_temporal_recovery.py, staging_pa10_simple_reminder.py
- Reuse: scripts/staging_backup_restore.py, staging_retention_deletion.py, staging_flag_rollback.py
- Inspect: docs/PA10_AUTOMATION_EVIDENCE_MATRIX.md and current controlled staging runbooks

**Interfaces:** Consume frozen release and existing public goal/task/automation routes. Produce actual synthetic scenario evidence bound to the same exact release. A simple reminder yields one automation_reminder, zero Agent runs and run_id=null.

**Acceptance:** Read/draft/artifact, owned goal/run, app-closed reminder, API/worker restart, cross-owner denial, revoked source, backup restore and rollback. Preserve a failed/unknown status if evidence is missing.

- [ ] **Step 1:** Select student and office synthetic fixtures with explicit resource owners and limits.
- [ ] **Step 2:** Run baseline public-API artifact/goal and simple-reminder collectors on the frozen release.
- [ ] **Step 3:** Kill/restart selected non-production workers and reconcile; inspect one accepted occurrence/run and exact artifacts.
- [ ] **Step 4:** Run owner, restore, retention/deletion and rollback collectors; fix demonstrated gaps in separate code PRs before recollecting.
- [ ] **Step 5:** Record scenario-level results, identities and hashes; retain gates off where evidence is incomplete.

**Verification entry points:**
```bash
uv run --extra coworker python -m scripts.staging_pa10_simple_reminder --help
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-05: Add durable owner-scoped conversation records

**Dependencies:** CW-01; may develop while staging access is blocked.

**Files:**
- Create: services/coworker/conversation_schemas.py, conversation_repository.py
- Create: services/coworker/migrations/versions/0055_coworker_conversations.py (renumber if needed)
- Modify: services/coworker/models.py, api.py, container.py
- Create: tests/test_conversations.py; Modify: tests/test_coworker_postgres.py

**Interfaces:** Propose ConversationCreate(title), MessageCreate(text, client_request_key, selected_resource_ids), ConversationRepository.create(owner: str, request: ConversationCreate, key: str) -> dict and append_message(owner: str, conversation_id: str, request: MessageCreate) -> tuple[dict,bool]. Store payload fingerprint and unique owner/conversation/key; produced message stores links, not duplicate run/action state.

**Acceptance:** Owned reads/writes; duplicate identical key returns same message; changed body/scope with key conflicts; two concurrent requests accept one; old API/migrations stay compatible; deletion/retention linked.

- [ ] **Step 1:** Add owner/idempotency/conflict/PostgreSQL race regressions for conversation and message records.
- [ ] **Step 2:** Define bounded Pydantic schemas and additive migration; use the repository's existing idempotency/error conventions.
- [ ] **Step 3:** Implement repository and owner-scoped routes in the existing API/container, with no implicit task dispatch on reads.
- [ ] **Step 4:** Run tests and migration/rollback-compatibility checks; verify raw text stays out of ordinary audit/Temporal history.
- [ ] **Step 5:** Commit one durable conversation slice with capability admission default-off as required by release contract.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_conversations.py tests/test_coworker_postgres.py -q -rs
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-06: Dispatch and steer work from conversation

**Dependencies:** CW-05.

**Files:**
- Create: services/coworker/conversation_dispatch.py
- Modify: services/coworker/conversation_repository.py, agent_router.py, api.py, container.py
- Modify if needed: services/coworker/agent_repository.py, goal_repository.py, workflow.py
- Create: tests/test_conversation_dispatch.py

**Interfaces:** Propose ConversationDispatchService.dispatch(owner: str, conversation_id: str, message_id: str) -> dict; steer(owner: str, run_id: str, expected_revision: int, instruction: str) -> dict. Consume qualify_agent_goal and existing task/run creation idempotency and outbox interfaces. Produce durable resource links and explicit direct_answer/task/agent/transactions/needs_input routing; do not invent another workflow ledger.

**Acceptance:** Two independent messages link independent work; message replay does not dispatch twice; modified steering conflicts on stale revision; cancellation beats delayed result; high-impact input routes to exact review; model failure creates no fake success.

- [ ] **Step 1:** Add duplicate dispatch, concurrent message, stale steering, cancellation and ambiguous-action tests.
- [ ] **Step 2:** Implement message-to-resource dispatch using existing admission/outbox boundaries; keep instructions in private context refs.
- [ ] **Step 3:** Add revision-checked steering for supported non-mutating plan edits; forbid editing a claimed/approved mutation via chat.
- [ ] **Step 4:** Run route suite plus new tests; replay old histories if workflow behavior changes.
- [ ] **Step 5:** Commit route/steering links and document supported interruptions and explicit blocked states.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_conversation_dispatch.py tests/test_core_agent_router.py tests/test_coworker_temporal.py -q -rs
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-07: Build continuous chat and unified activity UI

**Dependencies:** CW-05/CW-06.

**Files:**
- Create: apps/web-editor/src/coworker/ConversationWorkspace.tsx
- Create: services/coworker/activity_projection.py
- Modify: apps/web-editor/src/WorkspaceShell.tsx, coworker/CoworkerWorkspace.tsx, coworker/client.ts, coworker/workspace.css
- Modify: services/coworker/api.py
- Create: apps/web-editor/src/coworker/conversation.test.ts, tests/test_activity_projection.py

**Interfaces:** Propose ActivityProjection.list(owner: str, conversation_id: str, after: str | None, limit: int) -> dict with items and durable cursor; project existing goal/run/task/action/notification data. Frontend typed createMessage/getActivity methods consume CW-05/CW-06 routes. Use deterministic approval controls, not freeform yes.

**Acceptance:** Reconnect never duplicates dispatch; activity shows running/blocked/needs_input/awaiting_approval/uncertain; wrong-owner cursors denied; goal/task links work; mobile keyboard/navigation; existing writing tab remains usable.

- [ ] **Step 1:** Add API projection and frontend replay/state regressions against resource-linked records.
- [ ] **Step 2:** Implement bounded owner-filtered activity projection without a second progress database.
- [ ] **Step 3:** Build chat with multiple in-flight work cards, steering/cancel targets, artifact/goal links and resumable updates.
- [ ] **Step 4:** Run frontend tests/build and API tests; inspect representative desktop/mobile flows and existing writing experience.
- [ ] **Step 5:** Commit UI slice; record access/render checks separately from live background execution.

**Verification entry points:**
```bash
npm run test --workspace @shuddho/web-editor
npm run build --workspace @shuddho/web-editor
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-08: Unify workspace context, versioning and memory controls

**Dependencies:** CW-05/CW-06.

**Files:**
- Create if existing records are insufficient: services/coworker/workspace_manifest.py
- Modify: services/coworker/context.py, context_policy.py, memory_repository.py, storage.py, retention.py
- Modify: apps/web-editor/src/coworker/ConversationWorkspace.tsx and client.ts
- Create: tests/test_workspace_context.py; Extend: tests/test_context_memory.py, test_coworker_retention.py

**Interfaces:** Propose build_conversation_context(owner: str, conversation_id: str, run_id: str) -> dict of bounded private source refs with owner/version/hash/provenance/trust labels. Reuse existing owned document/artifact and memory records; add migration only for a demonstrated missing relationship. Produce no credential or execution grant.

**Acceptance:** Selected sources only; revoked/deleted while queued -> deny use and no sync resurrection; changed version invalidates stale proposal; read/edit/delete memory; source vs inference labels; budget-bounded context; Bangla fidelity.

- [ ] **Step 1:** Map existing document/artifact relationships before adding new tables; record the missing relationship, if any.
- [ ] **Step 2:** Add revocation/deletion/version race and bounded-context regressions.
- [ ] **Step 3:** Build the context projection and reviewable memory UI; recheck ownership/version at use.
- [ ] **Step 4:** Run context/retention suites and representative human-reviewed Bangla/English task comparisons.
- [ ] **Step 5:** Commit file/context continuity with provenance and explicit retention/deletion behavior.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_workspace_context.py tests/test_context_memory.py tests/test_coworker_retention.py -q
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-09: Expose a typed read-only browser tool to Runtime v3

**Dependencies:** CW-04/CW-06/CW-08; code may precede live qualification but stays gated.

**Files:**
- Modify: services/coworker/agent_tools.py, agent_runtime.py, agent_schemas.py, browser.py
- Modify as needed: services/coworker/agent_planning_model.py, workflow.py, scripts/release_contract.py
- Create: tests/test_agent_browser_tool.py; Extend: tests/test_browser_broker.py
- Inspect/reuse: scripts/browser_worker.mjs and browser_worker_policy.mjs

**Interfaces:** Propose BrowserReadToolInput(session_id: str, url: str, purpose: str) and browser.read tool yielding brokered observation refs, source URL/time/hash and trust=untrusted. Reuse browser owner/session broker and deterministic egress checks. No generic page script/CDP or transaction click authority.

**Acceptance:** Owner/session mismatch; internal-IP/redirect/port SSRF; malicious text/images/download; cancellation/takeover; no form submit; observations update planning but cannot widen grant; old histories unaffected.

- [ ] **Step 1:** Add typed input/output, source ownership, egress and model-injection regressions.
- [ ] **Step 2:** Register default-off browser.read under canonical capability dependencies; reuse broker and private observation storage.
- [ ] **Step 3:** Add v3 dispatch/observation handling with resumable session binding and bounded time/cost.
- [ ] **Step 4:** Run browser/runtime/policy tests, old-history replay and real isolated-worker staging cases before activation.
- [ ] **Step 5:** Commit one read-only browser capability with receipt/source and rollback contract.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_agent_browser_tool.py tests/test_browser_broker.py tests/test_coworker_temporal.py -q
node --test scripts/browser_worker_policy.test.mjs
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-10: Prepare and execute reviewed agent-generated code

**Dependencies:** CW-04/CW-06/CW-08.

**Files:**
- Create: services/coworker/code_proposals.py, code_proposal_schemas.py
- Modify: services/coworker/agent_tools.py, agent_runtime.py, sandbox.py, models.py, api.py
- Create additive code-proposal migration after current main
- Modify: apps/web-editor/src/coworker/SandboxWorkspace.tsx and client.ts
- Create: tests/test_agent_code_proposals.py; Extend: tests/test_sandbox_control_plane.py

**Interfaces:** Propose CodeProposalCreate(source, input_refs, limits, egress_profile), prepare_code(owner: str, run_id: str, request: CodeProposalCreate) -> dict; approve_code(owner: str, proposal_id: str, source_sha256: str) -> dict. Bind owner/run/source/input hashes/limits/expiry; use existing sandbox execution. Code approval grants compute only, never provider mutation.

**Acceptance:** Changed source/input/expiry invalidates approval; replay executes same bounded identity; host/socket/secret/cross-owner absence; CPU/memory/disk/time/network caps; output checksum/private preview origin; cleanup; existing exact user-Python path preserved.

- [ ] **Step 1:** Add immutable-source, replay, changed-input and sandbox authority regressions.
- [ ] **Step 2:** Store model-generated source as an inert proposal and show source/inputs/limits/destinations for explicit review.
- [ ] **Step 3:** Bind reviewed hash to existing disposable sandbox; restrict dependencies and exports, with no privileged tool promotion.
- [ ] **Step 4:** Run sandbox/container enforcement and preview isolation checks plus real staging cleanup/restart scenarios.
- [ ] **Step 5:** Commit separately gated generated-code preparation/execution and clear error/rollback states.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_agent_code_proposals.py tests/test_sandbox_control_plane.py -q
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-11: Version coworker skills without dynamic authority

**Dependencies:** CW-06/CW-09/CW-10.

**Files:**
- Create: services/coworker/skill_manifests.py
- Modify only if justified: services/coworker/skills.py, agent_tools.py, agent_planning_model.py
- Create: tests/test_coworker_skill_manifests.py
- Modify: scripts/release_contract.py and model/quality evidence only if schema changes

**Interfaces:** Propose CoworkerSkillManifest(name, version, instruction_sha256, input_schema_sha256, output_schema_sha256, tool_names, resource_limits). validate_manifest(manifest: CoworkerSkillManifest, allowed_tools: frozenset[str]) -> None. Produce code-reviewed manifests referencing existing tools; manifests cannot register provider authority or executable credentials.

**Acceptance:** Unknown tool/provider -> reject; requested tool exceeds grant -> reject; changed instructions/schema -> evidence invalidation; untrusted generated skill remains sandbox-local; version rollback remains compatible.

- [ ] **Step 1:** Inventory existing WorkSkill/template/tool versions and avoid rebuilding their registry.
- [ ] **Step 2:** Add authority-subset and evidence-version regressions.
- [ ] **Step 3:** Implement reviewed skill manifest/loading for selected pilot workflows only; preserve application-owned allowlists.
- [ ] **Step 4:** Run model/skill contract tests and compare task quality/cost before expanding the catalog.
- [ ] **Step 5:** Commit evaluated manifests; defer autonomous skill installation and unrestricted tool generation.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_coworker_skill_manifests.py tests/test_coworker_services.py tests/test_agent_release_gates.py -q
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-12: Qualify schedules, provider events and recovery

**Dependencies:** CW-03/CW-04/CW-06/CW-08.

**Files:**
- Reuse: scripts/staging_pa10_scheduled_profile.py, staging_proactive_read_event.py, staging_pa10_managed_recovery.py
- Reuse: docs/PA10_AUTOMATION_EVIDENCE_MATRIX.md and related staging runbooks
- Extend if gaps found: services/coworker/automation_repository.py, automation_scheduler.py, connector_reads.py, notification_repository.py
- Extend: tests/test_automations.py, test_connector_reads.py

**Interfaces:** Consume existing occurrence identities, cursor/subscription renewal and notification ledger. Produce same-release evidence for Daily/Weekly/Deadline/Meeting/Email/goal-driven scenarios, Google/Microsoft synthetic events, revocation, DST/overlap/catch-up/expiry and worker/API loss.

**Acceptance:** Duplicate/out-of-order callback -> one accepted occurrence; revoke/pause before claim -> no new work; cursor gap recovered; app closed -> real notification; same due event and restart -> one run; quiet hours retained.

- [ ] **Step 1:** Refresh synthetic OAuth/subscription and worker prerequisites; freeze exact candidate.
- [ ] **Step 2:** Run real scheduled/event collectors across named profiles and supported providers.
- [ ] **Step 3:** Inject revocation/cursor-gap/duplicate/restart cases and inspect one durable identity per occurrence.
- [ ] **Step 4:** Repair uncovered implementation defects in separate bounded PRs; recollect matching release evidence after changes.
- [ ] **Step 5:** Record matrix results and block activation where provider/recovery evidence is absent.

**Verification entry points:**
```bash
uv run --extra coworker python -m scripts.staging_proactive_read_event --help
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-13: Validate proactive usefulness and controlled delivery

**Dependencies:** CW-12.

**Files:**
- Inspect/reuse: services/coworker/suggestion_relevance_service.py, suggestion_repository.py, notification_digests.py, web_push.py
- Inspect/reuse: scripts/staging_browser_push.py and current PA-10 evidence tooling
- Extend: tests/test_notification_digests.py, test_browser_push_dispatch.py, test_automations.py
- Modify: docs/coworker-roadmap/PROGRESS.md with pilot review references

**Interfaces:** Consume current opt-in preferences, source-bound dedupe keys, urgency/quiet-hour/digest policies and existing independent browser_push gate. Produce human-reviewed useful-update/outcome and interruption/cost measurements; no new email/messaging delivery implied.

**Acceptance:** Repeated unchanged evidence -> no new interruption; dismissed/revoked consent -> suppressed at claim and delivery; expired updates dropped; wrong owner/device denied; failed push not shown delivered; costs include background work.

- [ ] **Step 1:** Predeclare synthetic pilot cases and human usefulness rubric; preserve existing stricter bounds.
- [ ] **Step 2:** Exercise opt-in/out, quiet hours/digests, source freshness and duplicate delivery.
- [ ] **Step 3:** Use a consenting real test browser/device for push collector; retain independent channel consent/release evidence.
- [ ] **Step 4:** Review Bangla/English notifications and cost per useful update; tune only demonstrated low-quality behavior.
- [ ] **Step 5:** Record sample sizes, useful/dismissed/duplicate/late rates and qualification limits.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_notification_digests.py tests/test_browser_push_dispatch.py tests/test_automations.py -q
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-14: Qualify negotiation and no-payment restaurant transactions

**Dependencies:** CW-02/CW-03/CW-04; exact provider access.

**Files:**
- Reuse: scripts/staging_live_personal_transactions.py, staging_live_restaurant_reservations.py
- Reuse: scripts/personal_transactions_activation.py, transaction_capability_activation.py, cohort_release_ledger.py
- Inspect: services/coworker/actions.py, transaction_repository.py, opentable_actions.py
- Extend provider-specific tests only for discovered gaps

**Interfaces:** Consume current negotiation_commitment_email and OpenTable no-payment ActionSpecs, exact terms/approval/execution claim, provider receipts and canonical ledger. Produce live synthetic evidence; email delivery is not counterparty agreement; no-payment reservation cannot escalate to payment.

**Acceptance:** Changed preview/destination/terms -> fresh review; expiry/revocation -> no claim; accepted-lost response -> reconcile/uncertain; one provider mutation; exact reservation receipt; no card requirement accepted.

- [ ] **Step 1:** Verify provider consent and synthetic recipients/reservations; never use customer data.
- [ ] **Step 2:** Run wrong-hash rejection and separate correct approval with explicit bounded test authorization.
- [ ] **Step 3:** Execute one authorized provider attempt, then read-only receipt validation and uncertainty scenarios.
- [ ] **Step 4:** Compile capability/activation evidence in existing tools without activating production; retain exact operation/provider binding.
- [ ] **Step 5:** Record live-qualified versus blocked operations and residual provider limitations.

**Verification entry points:**
```bash
uv run --extra coworker python -m scripts.staging_live_restaurant_reservations --help
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-15: Select and qualify one shopping checkout provider

**Dependencies:** CW-02/CW-03; provider/API/commercial access and hosted-flow contract.

**Files:**
- Reuse: services/coworker/shopping_checkout_contract.py, shopping_checkout_adapter.py, shopping_checkout_adapter_conformance.py, hosted_transaction_handoff.py
- Create after provider selection: services/coworker/providers/<selected_provider>_shopping.py
- Modify: services/coworker/action_registry.py, credential_broker.py and registration/release checks only for the reviewed provider
- Extend: tests/test_shopping_checkout_adapter_conformance.py and provider-bound qualification tests

**Interfaces:** Consume current TX-14, TX-23, TX-24, TX-26/TX-27/TX-28 contracts. Produce exactly one selected provider's registered ActionSpec/runtime adapter and hosted user-present handoff; exact callback/read receipt confirms completion. <selected_provider> is a deliberate external choice, not a current callable adapter.

**Acceptance:** Amount/currency/tax/shipping/item/destination change invalidates preview; hosted redirect destination constrained; duplicate/forged/out-of-order callback denied or deduped; expiry; no completion from URL creation; applied charge count one.

- [ ] **Step 1:** Compare real provider capability, geography, access, fees, idempotency and reconciliation; document selection and unsupported cases.
- [ ] **Step 2:** Use existing adapter qualification/conformance and registration change plan; implement only the exact provider if access is available.
- [ ] **Step 3:** Add contract tests for hosted handoff and exact receipt; keep credentials brokered and shopping kill switch off.
- [ ] **Step 4:** Run real provider sandbox cases including accepted-lost response and duplicated completion; compile version-bound evidence.
- [ ] **Step 5:** Record operation-level qualification and activation prerequisite; never fabricate provider code or credentials when selection is blocked.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_shopping_checkout_adapter_conformance.py tests/test_hosted_transaction_handoff.py tests/test_shopping_checkout_provider_qualification.py -q
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-16: Select and qualify one travel booking provider

**Dependencies:** CW-02/CW-03; provider access and supported itinerary/terms contract.

**Files:**
- Reuse: services/coworker/travel_booking_contract.py, travel_booking_adapter.py, travel_booking_adapter_conformance.py, hosted_transaction_handoff.py
- Create after selection: services/coworker/providers/<selected_provider>_travel.py
- Modify reviewed provider registration/credential/release files only
- Extend: tests/test_travel_booking_adapter_conformance.py and provider-bound qualification tests

**Interfaces:** Consume current TX-19/TX-22/TX-25/TX-26/TX-27/TX-28 contracts. Produce provider-specific quote/booking identity and hosted user-present completion with exact booking receipt. Keep traveler data private and scope-bound; no general card storage or transfer authority.

**Acceptance:** Fare/availability/date/timezone/traveler/cancellation-term changes invalidate approval; handoff not booking; precise receipt identity; duplicate callback; provider outage/lost response; one booking/charge per approved identity.

- [ ] **Step 1:** Select a real supported provider based on geography, access, quote expiry, fees, idempotency, hosted completion and reconciliation.
- [ ] **Step 2:** Implement provider-specific registered contract using existing conformance/review tooling; leave booking gate off.
- [ ] **Step 3:** Add immutable fare/traveler/terms and hostile callback regressions.
- [ ] **Step 4:** Run provider sandbox/recovery cases and exact receipt validation; review failure/uncertainty support behavior.
- [ ] **Step 5:** Record precise supported booking scope and qualification evidence; do not expand to all travel sites.

**Verification entry points:**
```bash
uv run --extra coworker pytest tests/test_travel_booking_adapter_conformance.py tests/test_hosted_transaction_handoff.py tests/test_travel_booking_provider_qualification.py -q
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-17: Qualify integrated quality and independent security

**Dependencies:** Relevant M2..M5 capabilities implemented and staging-verified.

**Files:**
- Extend: scripts/core_agent_eval_suite.py, core_agent_multilingual_eval.py and appropriate fixture files
- Extend: tests/test_agent_release_gates.py, test_permission_gateway.py, test_context_memory.py
- Reuse artifact native opening/render/recalculation and browser/sandbox policy suites
- Record human/independent security review references in qualification evidence

**Interfaces:** Consume exact source/model/prompt/tool-schema/configuration identities. Produce per-workflow/per-language counts, human acceptance, artifact checks and adversarial results. New model selection/profile changes require renewed quality evidence; no fine-tuning promise.

**Acceptance:** >=90% proposed human acceptance for selected pilot; preserve stricter fixture thresholds; zero observed unauthorized mutation/cross-owner read/secret leakage/duplicate mutation in suite; text/image/file injection; native artifact quality.

- [ ] **Step 1:** Freeze representative selected tasks, languages and adversarial cases without leaking expected outcomes into evaluators.
- [ ] **Step 2:** Run actual model/route/artifact outcomes and human review; report counts, failures and confidence limits.
- [ ] **Step 3:** Exercise independent credential/grant/egress/isolation controls with adversarial model/tool proposals.
- [ ] **Step 4:** Obtain independent security review for broader browser/code/transaction launch; repair P0/P1 findings and requalify changed evidence.
- [ ] **Step 5:** Retain exact release evidence and report unresolved/unavailable checks transparently.

**Verification entry points:**
```bash
uv run --extra coworker python -m scripts.core_agent_eval_suite --min-scenarios 300
uv run --extra coworker python scripts/core_agent_multilingual_eval.py --min-pass-rate 1.0
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-18: Measure economics, load and 99.9% SLI

**Dependencies:** CW-04 and actual staging samples of selected pilot capabilities.

**Files:**
- Create: docs/COWORKER_SLO.md and docs/COWORKER_LOAD_PROFILE.md
- Reuse: scripts/core_agent_observability.py, cohort_capacity_qualification.py, provider_capacity.py
- Extend budget/concurrency tests only for discovered gaps
- Create load harness only if current capacity tooling cannot express the chosen workload

**Interfaces:** Define eligible API requests/latency/window and separate accepted-run completion/schedule timeliness SLIs. Consume existing operational exports and provider/account/run reservations; produce cost/latency/error-budget reports at declared workload. Do not claim measured 99.9% before the operated observation window.

**Acceptance:** Forecast load plus declared overload; writing protected from slow tool queues; retries charged; unknown usage conservative; nonzero reviewed pricing; bounded quotas; 43.2-minute budget only for a time-based 30-day SLI.

- [ ] **Step 1:** Predeclare denominators, endpoint/latency thresholds, observation window and dependency treatment; keep safety invariants separate.
- [ ] **Step 2:** Set reviewed nonzero pricing inputs and collect model/search/compute/storage/notification/retry costs per accepted outcome.
- [ ] **Step 3:** Run declared concurrency/overload tests using actual services; measure queue wait, p95/p99, provider saturation and budget races.
- [ ] **Step 4:** Repair capacity/observability gaps in bounded PRs; rerun changed workload and preserve raw sensitive data exclusion.
- [ ] **Step 5:** Report observed availability versus target, cost envelope, safe limits and remaining observation time.

**Verification entry points:**
```bash
uv run --extra coworker python -m scripts.core_agent_observability --help
uv run --extra coworker pytest tests/test_core_agent_observability.py tests/test_cohort_capacity_qualification.py -q
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-19: Verify restore, rollback and operated trust boundaries

**Dependencies:** CW-03; relevant launch-capability evidence and CW-17/CW-18.

**Files:**
- Reuse: scripts/staging_backup_restore.py, staging_retention_deletion.py, staging_flag_rollback.py, staging_temporal_recovery.py
- Inspect deployment separation, network policies, Dockerfile.coworker, Dockerfile.sandbox-worker, browser worker deployment
- Update incident/restore/credential-rotation/deletion runbooks and canonical evidence

**Interfaces:** Consume actual non-production API/workflow/browser/sandbox/connector/notification deployments. Produce restored-state integrity, measured RPO/RTO, fresh recovery identity and denied direct egress/secret access. No runtime flag rollback deletes action receipts or old workflow recovery data.

**Acceptance:** Restore from backup into isolated environment; old histories replay; credential rotation/revocation; source deletion not resurrected; workers enforce CPU/memory/network caps; previews have no app cookies; rollback retains uncertainty.

- [ ] **Step 1:** Prepare controlled failure/restore scenarios and secure operator ownership without broad production permissions.
- [ ] **Step 2:** Run backup restoration, worker/API interruption, credential rotation, retention/deletion and rollback using existing tools.
- [ ] **Step 3:** Attempt direct egress/host/socket/secret/cross-owner access from untrusted execution cells; inspect actual deployment enforcement.
- [ ] **Step 4:** Record actual RPO/RTO, cleanup and recovery identity; fix P0/P1 failures and recollect evidence.
- [ ] **Step 5:** Commit operated runbooks/evidence refs; keep failed capabilities disabled.

**Verification entry points:**
```bash
uv run --extra coworker python -m scripts.staging_backup_restore --help
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## CW-20: Review and activate a small production pilot

**Dependencies:** Relevant CW-04..CW-19 gates pass; separately authorized production activation.

**Files:**
- Reuse: scripts/release_contract.py, release_activation_bundle.py, cohort_release_gate.py, cohort_release_ledger.py
- Reuse operation-specific activation verifiers and controlled-cohort runbooks
- Update support/on-call/provider/deletion documentation and PROGRESS.md

**Interfaces:** Consume same-release reviewed provider/model/capability evidence and current activation bundle/ledger. Produce only explicitly authorized operation/cohort activation and observed post-deploy status. Start with safe student/office/calendar pilot; enable payment-bearing providers only when their own gates pass.

**Acceptance:** Small reviewed cohort; rollback/kill switch ready; no stale evidence; exact deployed API/worker identity; alert handling; real successful outcomes and uncertainty support; measured cost/reliability guardrails.

- [ ] **Step 1:** Compile the exact matching release/activation/ledger bundle; deny activation on stale or missing evidence.
- [ ] **Step 2:** Prepare a concrete reviewable rollout with capability/provider/cohort limits, operator, rollback and support commitments.
- [ ] **Step 3:** Obtain production authorization only after the bundle is complete; execute exactly the authorized subset.
- [ ] **Step 4:** Observe the declared canary window and rollback on review thresholds; no unreviewed cohort/operation expansion.
- [ ] **Step 5:** Publish truthful launched capabilities/limits and update status per level; prioritize measured pilot defects before broad parity work.

**Verification entry points:**
```bash
uv run --extra coworker python -m scripts.release_contract_check
```
Expected: focused checks pass with no mandatory safety skips; operational `--help` is preparation only, not a passed scenario. Run the applicable full required CI and record exact revision. New-file commands apply after implementation. Services and external credentials must be available for integration/live checks.

## Beyond the first qualified pilot

After CW-20, evaluate bounded read/compute specialist child runs using the existing task
graph, shared parent budget, explicit source/grant subsets and verified fan-in. Add them
only if outcome/cost/recovery evaluation beats the coordinator baseline. Keep one Temporal
authority and no independent child transaction authority.

Later candidates: broader modalities and evaluated vision, voice/mobile surfaces,
additional real connectors, approved third-party skill packaging, warm or dedicated
secure compute, regional deployment cells and advanced personal transaction families.
Each needs its own specification, concrete provider constraints and qualification gate.
None is required to claim the initial three-workflow pilot works.

## Self-review and scope

This queue covers architecture, core agent, proactive automation, transactions and
production qualification. CW-01/CW-02 close the 16-fault evidence gap first; CW-05..CW-11
close continuity/tool gaps; CW-03/CW-04/CW-12..CW-20 qualify actual operated behavior.
No task creates a duplicate run, notification or external-action truth store.

This kit is an implementation plan, not implemented product functionality. Continue
with CW-01 using CHATBOT_WORKFLOW.md's first-task prompt. Broader runtime execution
requires a subsequent concrete task instruction; preserve the current request's scope.

