# Continuous Agent Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete conversation-to-Agent continuity with revision-safe steering, concurrent activity, and pinned project/artifact context.

**Architecture:** Extend the existing AgentRun and conversation activity path. Use additive persistence for project snapshots, selected artifact IDs, and steering revisions; feed these into the existing Agent Runtime and ContextService. Keep the existing conversation activity projection and explicit Start task action.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, Temporal, PostgreSQL/SQLite test fixtures, React, TypeScript, Vitest/node test runner.

**Spec:** `docs/superpowers/specs/2026-11-09-continuous-agent-integration-design.md`

## Global Constraints

- Preserve the existing AgentRun, AgentOutbox, Temporal, AgentEvent, AgentCheckpoint, and conversation message-link contracts.
- Keep explicit Start task; ordinary message append must never dispatch work.
- Never infer external-action approval from chat, project instructions, artifacts, or steering.
- Keep owner scoping, account-before-run lock ordering, idempotency, source provenance, and revision checks.
- Keep Runtime v3 and context-retrieval rollout flags unchanged and default-off.
- Do not modify the separate Long-Running repository or unrelated product tabs.

## Review Focus

- A user steers while the planner is in-flight; stale inference must not commit over the newer instruction.
- An artifact is deleted, expires, or changes between admission and object read; its bytes must not reach the planner.
- A project is edited or deleted after dispatch; the run must retain the exact admission-time snapshot.
- Existing conversation AgentRun records are replayed after the additive migration; empty new fields must preserve behavior.
- Two tasks approach the active-run limit and one is cancelled; the other run and its outbox must remain unaffected.

---

### Task 1: Persist and deliver project and artifact context

**Files:**
- Modify: `services/coworker/models.py`
- Create: `services/coworker/migrations/versions/0065_continuous_agent_context.py`
- Modify: `services/coworker/conversation_schemas.py`
- Modify: `services/coworker/conversation_dispatch.py`
- Modify: `services/coworker/conversation_context.py`
- Modify: `services/coworker/context.py`
- Modify: `services/coworker/agent_repository.py`
- Modify: `services/coworker/agent_runtime.py`
- Test: `tests/test_conversation_dispatch.py`
- Test: `tests/test_conversation_context.py`
- Test: `tests/test_coworker_projects.py`

**Interfaces:**
- `ConversationDispatchService.dispatch(owner, conversation_id, message_id, *, expected_sequence, output_language="auto", project_id=None)` returns the existing `(run_payload, created)` tuple.
- New AgentRun fields: `input_artifacts: list[str]`, `project_context: dict`, `steering_revision: int`, `steering_instructions: list[dict]`.
- `project_context` snapshot shape: `{project_id, name, revision, instructions}`.
- `input_artifacts` stores artifact IDs only; document version IDs remain in `input_versions`.

- [ ] **Step 1: Write failing project-context admission tests**
  - Add `test_project_instructions_are_snapshotted_for_conversation_run`: dispatch from a project-linked conversation and assert exact project ID/name/revision/instructions are stored on the AgentRun.
  - Add `test_dispatch_rejects_project_not_linked_to_conversation`: a foreign or unlinked project returns not-found and creates no run.
- [ ] **Step 2: Run the two tests and verify expected failures**
  - Run: `pytest tests/test_conversation_dispatch.py -k 'project_instructions_are_snapshotted or project_not_linked' -q`
  - Expected: FAIL because dispatch does not accept or persist project context.
- [ ] **Step 3: Write failing artifact-admission tests**
  - Add `test_selected_artifact_is_pinned_on_conversation_agent_run`: a supported owned artifact is stored in `input_artifacts`, not `input_versions`.
  - Add `test_artifact_admission_rejects_unsupported_and_oversized_sources`: unsupported extension or size over `settings.max_upload_bytes` is rejected without creating a run.
  - Add `test_worker_entry_rejects_deleted_or_changed_selected_artifact`: original message binding and exact artifact ID/hash must match.
- [ ] **Step 4: Run artifact tests and verify expected failures**
  - Run: `pytest tests/test_conversation_dispatch.py tests/test_conversation_context.py -k 'artifact' -q`
  - Expected: FAIL because dispatch currently rejects artifacts and worker validation only compares document versions.
- [ ] **Step 5: Implement additive persistence and dispatch**
  - Add the four AgentRun fields with safe empty defaults.
  - Create migration `0065` after `0064`; use non-null empty JSON defaults and steering revision zero.
  - Extend `ConversationDispatchCreate` with optional `project_id`.
  - Validate project ownership and conversation membership through `ProjectResource`; snapshot `Project.name`, `Project.revision`, and `Project.description`.
  - Revalidate selected sources; split document-version IDs into `input_versions` and artifact IDs into `input_artifacts`.
  - Validate supported artifact extensions (`txt`, `docx`, `pdf`, `csv`, `xlsx`, `pptx`) and size against `settings.max_upload_bytes`.
  - Include project snapshot and selected pins in new-run idempotency fingerprint; preserve replay of pre-migration runs with no project/artifact context.
- [ ] **Step 6: Implement worker-entry and content revalidation**
  - Extend `require_admitted_conversation_run_sources` to compare exact document and artifact IDs against the original message pins.
  - Extend `ContextService._run_and_sources` and `_source_current` to load owner-scoped artifact metadata and revalidate expiry, size, and SHA-256 before and after storage reads.
  - Extract artifacts with the existing isolated `extract_in_subprocess` parser, using the validated filename extension.
  - Add the immutable project snapshot to planner context with explicit precedence below the current user request and with no permission authority.
  - Return artifact IDs and project snapshot in owner-visible AgentRun/worker DTOs.
  - For legacy runtimes, include the pinned project instructions in the planner goal context; Runtime v3 receives structured project context through planner dependencies.
- [ ] **Step 7: Run focused context tests**
  - Run: `pytest tests/test_conversation_dispatch.py tests/test_conversation_context.py tests/test_coworker_projects.py -q`
  - Expected: PASS; existing project and document behavior remains unchanged.
- [ ] **Step 8: Commit Task 1**
  - Commit message: `feat: persist project and artifact context for conversation runs`.

### Task 2: Add revision-safe Runtime v3 steering

**Files:**
- Modify: `services/coworker/conversation_schemas.py`
- Modify: `services/coworker/conversation_dispatch.py`
- Modify: `services/coworker/api.py`
- Modify: `services/coworker/agent_repository.py`
- Modify: `services/coworker/agent_runtime.py`
- Test: `tests/test_conversation_dispatch.py`
- Test: `tests/test_agent_v3_decision_recovery.py`

**Interfaces:**
- New request schema `ConversationSteerRequest(expected_sequence, expected_steering_revision, instruction)`; instruction length 1–4000 characters.
- New service method `steer(owner, conversation_id, message_id, *, expected_sequence, expected_steering_revision, instruction)`.
- New route: `POST /api/v1/conversations/{conversation_id}/messages/{message_id}/steer`.
- `AgentRepository.commit_v3_decision(..., expected_steering_revision)` rejects decisions inferred against a stale revision.

- [ ] **Step 1: Write failing steering service and HTTP tests**
  - Add `test_steer_appends_instruction_to_only_the_linked_active_v3_run`: revision increments once and another run remains unchanged.
  - Add `test_steer_rejects_stale_revision_foreign_owner_and_terminal_run`: each invalid request fails closed without appending an instruction.
  - Add `test_http_conversation_steer_contract`: authenticated endpoint validates payload and returns the new revision.
- [ ] **Step 2: Run steering tests and verify expected failures**
  - Run: `pytest tests/test_conversation_dispatch.py -k 'steer' -q`
  - Expected: FAIL because the schema, service method, and route do not exist.
- [ ] **Step 3: Implement the steering endpoint**
  - Lock owner, conversation, message, and linked AgentRun using existing lock order.
  - Require exact message-to-run ownership, current conversation sequence, expected steering revision, Runtime v3, and an active run state.
  - Append an ordered instruction with revision and timestamp; do not mutate the original goal.
  - Emit an Agent event and update activity revision.
- [ ] **Step 4: Write failing stale-inference test**
  - Add `test_v3_discards_decision_when_steering_changes_during_inference`: a planner that triggers a steering append before commit must be called again and only the decision using the latest steering revision may persist.
  - Add `test_v3_commit_rejects_stale_steering_revision`: direct commit with an old revision raises `agent_steering_changed`.
- [ ] **Step 5: Run stale-inference tests and verify expected failures**
  - Run: `pytest tests/test_agent_v3_decision_recovery.py -k 'steering' -q`
  - Expected: FAIL because planner commits do not bind a steering revision.
- [ ] **Step 6: Implement planner revision binding**
  - Return steering history/revision from `worker_run`.
  - Include ordered steering instructions in Runtime v3 planner dependencies.
  - Require the same revision in `commit_v3_decision` under the run row lock.
  - On a stale revision, discard the decision and retry inference at most twice within the existing deadline and planner budget.
  - Settle every actual planner attempt, including discarded stale attempts.
  - Reject steering for Runtime v1/v2 rather than implying it can alter an already materialized legacy plan.
- [ ] **Step 7: Run focused steering and recovery tests**
  - Run: `pytest tests/test_conversation_dispatch.py tests/test_agent_v3_decision_recovery.py -q`
  - Expected: PASS; replay, cancellation, planner budget, and terminal-finality tests remain green.
- [ ] **Step 8: Commit Task 2**
  - Commit message: `feat: add revision-safe steering for conversation agent runs`.

### Task 3: Integrate steering and concurrent run activity in the UI

**Files:**
- Modify: `apps/web-editor/src/coworker/client.ts`
- Modify: `apps/web-editor/src/coworker/ConversationWorkspace.tsx`
- Modify: `apps/web-editor/src/coworker/ConversationRunStatus.tsx`
- Modify: `apps/web-editor/src/coworker/conversation-enhancements.css`
- Test: `apps/web-editor/src/coworker/conversationUsability.test.tsx`
- Test: `apps/web-editor/src/coworker/conversationRunStatus.test.tsx`
- Test: `apps/web-editor/src/coworker/client.test.ts`

**Interfaces:**
- Extend `ConversationActivityRecord` with `steering_revision: number`.
- Extend `dispatchConversationMessage(id, messageId, sequence, projectId?)`.
- Add `steerConversationAgent(id, messageId, sequence, expectedSteeringRevision, instruction)`.
- `ConversationWorkspace` keeps one independent steering draft/open state per selected message.

- [ ] **Step 1: Write failing client/UI tests**
  - Assert project chat dispatch includes its project ID.
  - Assert an active run exposes its own steering form and sends the current activity revision plus instruction.
  - Assert a stale steering response triggers an activity/message refresh and displays the server conflict.
  - Assert two active runs both load progress eagerly and each exposes independent cancel/steer controls.
  - Assert ordinary message send still does not call dispatch.
- [ ] **Step 2: Run frontend tests and verify expected failures**
  - Run: `cd apps/web-editor && npm test -- --run src/coworker/conversationUsability.test.tsx src/coworker/conversationRunStatus.test.tsx src/coworker/client.test.ts`
  - Expected: FAIL because the steering client method and controls do not exist and only the latest run loads eagerly.
- [ ] **Step 3: Implement client and conversation controls**
  - Add project ID to dispatch requests only when the current conversation is in a project.
  - Add the typed steering request.
  - Render a per-run Steer form only for active Runtime v3 runs; preserve Cancel Agent work.
  - Send the current conversation sequence and steering revision; refresh the conversation after success or revision conflict.
  - Eagerly load every active run while retaining lazy expansion for older completed runs.
  - Keep the composer independent of active Agent execution so a second task can be started while the first is running.
- [ ] **Step 4: Implement progress rendering**
  - Display ordered steering instructions/revision in the corresponding run status.
  - Keep progress and cancellation bound to each message's exact run ID.
  - Do not make one run's loading/error state hide another run's activity.
- [ ] **Step 5: Run frontend tests**
  - Run: `cd apps/web-editor && npm test -- --run src/coworker/conversationUsability.test.tsx src/coworker/conversationRunStatus.test.tsx src/coworker/client.test.ts`
  - Expected: PASS; chat-only and explicit Start task behavior remains unchanged.
- [ ] **Step 6: Commit Task 3**
  - Commit message: `feat: expose per-run steering and concurrent activity in conversations`.

### Task 4: Verify end-to-end continuity and document qualification

**Files:**
- Modify: `tests/test_conversation_dispatch.py`
- Modify: `tests/test_conversation_context.py`
- Modify: `tests/test_agent_v3_decision_recovery.py`
- Modify: `apps/web-editor/src/coworker/conversationUsability.test.tsx`
- Create: `docs/coworker-roadmap/P02_CONTINUOUS_AGENT_INTEGRATION_QUALIFICATION_2026-11-09.md`

**Interfaces:**
- No new production interfaces. This task verifies the interfaces produced by Tasks 1–3.

- [ ] **Step 1: Add the multi-run isolation test**
  - Add `test_two_conversation_runs_progress_and_cancel_independently`: admit two runs in one conversation, confirm two activity records, cancel one, and assert the other run/outbox remains active and unchanged.
- [ ] **Step 2: Add the project/artifact persistence regression**
  - Admit a project run with a selected artifact; edit the project and expire/delete the artifact after admission. Assert the run retains its project snapshot while the artifact is invalidated before content reaches the planner.
- [ ] **Step 3: Run focused backend and frontend suites**
  - Run: `pytest tests/test_conversation_dispatch.py tests/test_conversation_context.py tests/test_coworker_projects.py tests/test_agent_v3_decision_recovery.py -q`
  - Run: `cd apps/web-editor && npm test -- --run src/coworker/conversationUsability.test.tsx src/coworker/conversationRunStatus.test.tsx src/coworker/client.test.ts`
  - Expected: PASS.
- [ ] **Step 4: Run repository CI-equivalent suites**
  - Run the repository's documented backend and frontend test commands from CI; capture exact pass/fail/skip counts and lint/typecheck/build outcomes.
  - Expected: all required checks green; any pre-existing failures are named, not hidden.
- [ ] **Step 5: Write qualification evidence**
  - Record branch/commit SHAs, migration, test commands/results, CI run links, remaining rollout prerequisites, and explicit status that no production flags were activated.
- [ ] **Step 6: Commit Task 4**
  - Commit message: `test: qualify continuous conversation agent integration`.

## Completion contract

- All four tasks have failing-test evidence followed by passing focused tests.
- Existing conversation, Agent runtime, activity cursor, cancellation, context-security, and frontend tests remain green.
- GitHub Actions checks on the PR head are green.
- The branch is reviewable and a preview URL is reported if the repository's Vercel integration creates one.
- No production deployment, merge, or rollout-flag activation occurs without separate approval.
