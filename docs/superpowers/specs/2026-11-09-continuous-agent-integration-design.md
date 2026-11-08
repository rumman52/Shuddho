# Continuous Agent Integration Design

**Status:** Approved for implementation by the project owner on 2026-11-09  
**Base:** `main` at `ebc6a3547fbaa6b3e3a1e55396938ecdaecbc192`  
**Implementation branch:** `feat/p2-continuous-agent-integration-20261109`

## Intent

Make a conversation and its Agent runs behave as one continuous Rukh AI coworker experience. A user can start more than one bounded task from a conversation, see each task's progress, steer an active Runtime v3 task, cancel one task without affecting others, and carry explicitly selected project instructions and artifacts into a run.

## Goals

- Preserve the existing conversation-message → AgentRun → AgentOutbox → Temporal workflow path.
- Keep the existing resumable conversation activity projection as the single conversation-level task timeline.
- Support multiple independently linked Agent runs in one conversation within the configured active-run limit.
- Add owner-scoped, optimistic-revision-checked steering for active Runtime v3 runs.
- Apply steering at the next planner checkpoint and prevent a planner decision produced from an older steering revision from committing.
- Snapshot project name, description/instructions, and revision into each new run started from that project.
- Admit selected generated artifacts as immutable, checksum-pinned, untrusted run context alongside document versions.
- Revalidate selected artifacts and their exact message binding at worker entry and before/after object reads.
- Expose per-run steering and cancellation in the conversation UI and keep active runs visible concurrently.

## Non-goals

- Do not auto-dispatch ordinary chat messages. The existing explicit **Start task** action remains the authorization boundary for Agent execution.
- Do not create a second task ledger, Agent runtime, scheduler, or event system.
- Do not make conversation text, project instructions, artifacts, or steering instructions an external-action approval grant.
- Do not broaden project membership, file access, connector grants, or action permissions.
- Do not change default rollout flags or deploy/activate the feature in production.

## Existing architecture

- `ConversationDispatchService` atomically creates an `AgentRun`, initial `AgentEvent`, `AgentCheckpoint`, `AgentOutbox`, and message resource link.
- `ConversationDispatchService.activity` projects message-linked AgentRun state with resumable message cursors.
- Cancellation delegates to `AgentRepository.cancel_in_session`, which preserves the existing Agent cancellation contract.
- `require_current_selected_sources` and `require_admitted_conversation_run_sources` already validate document and artifact source pins, but dispatch and worker context currently only admit document versions.
- Project descriptions already act as saved instructions for direct conversation replies; dispatch currently does not snapshot them into Agent runs.
- Runtime v3 receives planner context through `ContextService.planner_context` and `AgentRuntime.decide_v3`.

## Design decisions

### Run identity and context

Add additive AgentRun fields for `input_artifacts`, `project_context`, `steering_revision`, and `steering_instructions`. Keep `input_versions` unchanged for existing document-version references. Project context is an immutable admission-time snapshot: project ID, name, revision, and description/instructions. Editing or deleting a project later does not silently rewrite an already admitted run.

### Artifact provenance

Only explicitly selected artifact IDs from the originating message are admitted. Validate owner, checksum, expiry, supported extraction format, and the configured upload-size bound. Store artifact IDs separately from document-version IDs. On each conversation-run worker entry, revalidate the original message, exact linked run, selected source pins, and run input IDs. Context extraction verifies object length and SHA-256 and rechecks artifact existence/hash/expiry after reading. Artifacts remain untrusted data and cannot supply tool or approval authority.

### Steering

Add a dedicated `POST /conversations/{conversation_id}/messages/{message_id}/steer` endpoint. The request includes the current conversation sequence, expected steering revision, and a bounded instruction. The service locks the owner and run, verifies the message-to-run link and active Runtime v3 state, appends the instruction, increments the steering revision, and emits a normal Agent event. It never rewrites the original goal or grants permissions.

Runtime v3 includes the ordered steering history in planner dependencies. `commit_v3_decision` compares the steering revision used for inference with the current locked run revision. A stale decision is discarded and replanned within a small bounded retry count. This prevents an in-flight model response from overwriting a newer user instruction.

### Activity, concurrency, and cancellation

Continue using the existing conversation activity projection and Agent event sequence. Add the current steering revision to each activity item. Keep runs independently addressable by their linked message. A steering or cancellation request affects only its selected run. Existing active-run limits, idempotency, event cursors, outbox delivery, and cancellation behavior remain authoritative.

### User experience

The composer remains a chat/save surface. Users explicitly select **Start task** for each message. Project chats pass their project ID during dispatch. Each active run exposes its own progress, **Steer**, and **Cancel Agent work** controls. All active runs load progress eagerly; older completed runs remain expandable. Selected generated artifacts are shown and labeled as untrusted context.

## Security and compatibility

- All new queries remain owner-scoped and use the existing account/run locks.
- Project context is accepted only when the project belongs to the owner and is linked to the conversation.
- Stale conversation revisions, steering revisions, foreign IDs, deleted records, expired artifacts, hash mismatches, and unsupported artifact formats fail closed.
- Existing AgentRun rows receive safe empty defaults through an additive migration.
- Existing `input_versions`, conversation resource links, run IDs, activity cursors, and cancellation semantics remain compatible.
- Runtime v3 and context retrieval remain controlled by their existing settings; implementation does not switch rollout flags on.

## Acceptance criteria

1. A conversation can have two independently running Agent tasks, and cancelling or steering one does not affect the other.
2. Activity refresh/replay returns all linked tasks with their current state and steering revision.
3. Only the owner can steer or cancel a run, and only while it is active and Runtime v3 is enabled for that run.
4. A stale steering revision is rejected; a planner decision inferred against an old steering revision cannot commit.
5. A project run carries the exact project instructions and revision that existed at admission.
6. A selected artifact is pinned to its exact ID and SHA-256 and is revalidated at admission, worker entry, and content read.
7. Deleted, expired, changed, foreign, unsupported, or unlinked sources never reach the planner.
8. Ordinary chat messages never start Agent work automatically; external actions still require their existing explicit approval workflow.
9. Backend and frontend regression tests pass; GitHub Actions reports green checks on the implementation PR.
