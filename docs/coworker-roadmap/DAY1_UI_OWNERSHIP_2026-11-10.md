# Day 1 B: conversation UI ownership and contract map

Inspected on 10 November 2026 at source revision
`5816cdbbce340b8bd286ec8ea7ab9a57e3e9e735`. This is a source map and local-check
record, not deployed qualification. No application source, capability flag, API
contract, or execution authority changes are included.

## Canonical ownership

| Boundary | Actual owner and export | Current consumers |
| --- | --- | --- |
| Combined application entry | `apps/web-editor/src/main.tsx` imports default `WorkspaceShell` from `WorkspaceShell.tsx` | `WorkspaceShell` lazy-loads default `App` from `apps/coworker/src/App.tsx` or `apps/editor/src/App.tsx` according to `appRoutes.mjs` |
| Coworker shell | `apps/coworker/src/App.tsx`, default `App` | Imports default `CoworkerGate` from `apps/web-editor/src/coworker/CoworkerGate.tsx`; the combined build uses this same shell |
| Authenticated workspace | `apps/web-editor/src/coworker/CoworkerGate.tsx`, default `CoworkerGate`; `CoworkerWorkspace.tsx`, default `CoworkerWorkspace` | Gate constructs the authenticated client; Workspace renders the shared conversation surface for `view === "conversations"` |
| Conversation surface | `apps/web-editor/src/coworker/ConversationWorkspace.tsx`, default `ConversationWorkspace` | Used by `CoworkerWorkspace`; owns composer, history, sources, replies, dispatch, cancellation, steering and inline progress |
| Canonical API implementation | `apps/web-editor/src/coworker/client.ts`, named `CoworkerClient`, `WorkspaceError` and DTO/type exports | Coworker modules and `apps/editor/src/App.tsx` import this file directly |
| Shared client package | `packages/coworker-client/src/index.ts`; package export `@rukh/coworker-client` | Compatibility facade using `export * from "../../../apps/web-editor/src/coworker/client"`; it contains no separate endpoint implementation |
| Writing Assistant shell | `apps/editor/src/App.tsx`, default `App` | Uses the canonical client and shared navigation; does not render `ConversationWorkspace`. Its handoff uploads a source, resolves its version, saves a conversation message and navigates to Coworker without dispatching |
| Reply/progress presentation | Default `ConversationReply` in `ConversationReply.tsx`, default `ConversationRunStatus` in `ConversationRunStatus.tsx` | Conversation surface; reply uses `MarkdownMessage`, progress reads the exact linked `agentRun` |

The reusable conversation component is shared through cross-app source imports,
not through a second conversation package. `apps/web-editor/src/App.tsx` is the
writing/review implementation, not the current route selector.

## Existing controls and wire contracts

Paths below are relative to `apps/web-editor/src/coworker`.

| User control | Existing implementation and contract |
| --- | --- |
| Send/save | `ConversationWorkspace.tsx:413` saves through `appendConversationMessage(id, text, requestKey, selectedResourceIds)`. Empty-thread creation and message retries preserve payload-bound request identities. Saving never calls dispatch |
| Text reply and stop/retry | `ConversationWorkspace.tsx:263` calls `replyToConversationMessageStream` with a non-streaming compatibility fallback. `runtimeManifest().capabilities.conversation_replies` controls chat availability. Attached-source messages are saved without requesting a reply. Stop aborts receiving; the UI discloses that a saved reply may still finish |
| Source attachment | `ConversationWorkspace.tsx:571` reuses `upload(File)` and `workspaceManifest()`. Selection uses available document `version_id` or artifact `artifact_id`, at most five total, passed as `selected_resource_ids`. Saved messages show source labels and disclose that explicit Start task is required to read files |
| Explicit Start task | `ConversationWorkspace.tsx:465` calls `dispatchConversationMessage(id, messageId, sequence, projectId?)`. Client posts `expected_sequence`, `output_language: "auto"`, and optional validated `project_id` to the message's `/dispatch` route. Only the latest unlinked message exposes this control |
| Cancel | `ConversationWorkspace.tsx:477` calls `cancelConversationAgent` with conversation sequence and current activity event sequence; client posts `expected_sequence` and `expected_event_sequence` to the message's `/cancel` route |
| Steer | `ConversationWorkspace.tsx:489` uses `steerConversationAgent` with conversation sequence and current `steering_revision`. Only eligible active Runtime v3 runs expose the form. Instructions do not approve external actions |
| Concurrent progress | `ConversationWorkspace.tsx:770` eagerly loads every active linked run plus the newest linked run; older inactive runs expand on demand. `ConversationRunStatus.tsx` validates exact run ID, polls read-only, shows returned plan/results/instructions and exposes read retry |
| Rename/export | `renameConversation(id, title, expectedUpdatedAt)` uses optimistic revision. `conversationExport.ts` exports named `buildConversationMarkdown`, `buildConversationJson`, `conversationExportFilename`; downloads are local browser actions |

Canonical DTOs are `ConversationRecord`, `ConversationMessageRecord`,
`ConversationActivityRecord`, `AssistantReply`, and `WorkspaceManifest` in
`client.ts`. Activity already includes `steering_revision` and `runtime_version`.
No automatic conversation-to-task delegation is implemented by this mapping.

## Concrete gaps and limits

- **Upload format drift corrected in PR #664:** the source picker previously
  advertised CSV/XLSX/PPTX even though canonical `CoworkerClient.upload` rejects
  them. Its `accept` attribute and visible hint now match the existing supported
  TXT/DOCX/PDF formats and 8 MB client bound. A React regression pins both UI
  contracts. Its test-only parent commit `a8e7a37c6c86892976c7a67ffc4091297e8d308b`
  reproduced the mismatch in GitHub frontend CI: 240 passed, 1 expected failure,
  with actual `.txt,.docx,.pdf,.csv,.xlsx,.pptx` versus required
  `.txt,.docx,.pdf`. Final-head green CI remains to be verified. No upload
  authorization or backend supported-file list was expanded.
- **Steering draft isolation:** the component has one `steeringMessageId` and one
  `steeringDraft` (`ConversationWorkspace.tsx:74`); selecting another run clears
  the draft. Current tests prove one run's revision-bound steering and independent
  progress reads, not independent retained drafts for multiple runs.
- **Historical guidance is not current source evidence:**
  `docs/frontend/ARCHITECTURE.md` still describes replies/projects as unavailable;
  the 9 November continuous-integration plan has unchecked steps for interfaces
  already present. Current source and checks above govern this Day 1 map.
- Runtime/provider availability, authenticated deployed sessions, production
  ownership isolation and live task execution have not been established here.

## Existing coverage and local checks

`apps/web-editor/test/run-tests.mjs` explicitly bundles and imports the existing
React/client tests. It has a fixed test list and does not implement `--run`
filtering. Relevant coverage includes:

| Existing test file | Relevant assertions |
| --- | --- |
| `src/coworker/conversationUsability.test.tsx` | No-dispatch sends, idempotent first send, upload success/failure, five-source limit/labels, chat and streaming replies, generating-state composer lock, reply retry, Runtime v3 steering and concurrent progress |
| `src/coworker/client.test.ts` | Owner token refresh, redirects/base restrictions, signed-out network refusal, optimistic rename, bounded/malformed streaming and source integrity |
| `src/coworker/conversationIdentity.test.tsx` | Exact linked-run navigation and payload-bound lost-response retry identities |
| `src/coworker/conversationRunStatus.test.tsx` | Real returned progress, partial completion, read retry, stale/unrelated run rejection |
| `src/coworker/ConversationReply.test.tsx`, `markdownMessage.test.tsx`, `conversationExport.test.ts` | Partial/disconnected replies, safe Markdown, complete turn/provenance exports |
| `src/coworker/CoworkerGate.test.tsx`, `CoworkerWorkspace.test.tsx`; `test/coworker-app-navigation.test.tsx`, `rukh-responsive-ui.test.tsx` | Auth/draft entry, shell/navigation and responsive shared controls |

Passed locally: `node --test apps/coworker/test/app-shell.test.mjs
apps/coworker/test/navigation.test.mjs apps/editor/test/app-shell.test.mjs`:
**7 passed, 0 failed, 0 skipped**. These checks use Node built-ins; they verify
entry imports, implemented navigation/UUID deep links and Writing Assistant shell
contracts, not mounted React behavior.

After the main worker completed the single coordinated dependency installation,
`npm test --workspace @shuddho/web-editor` passed: **240 passed, 0 failed,
0 skipped**. This is the canonical complete runner, including the React/client
tests mapped above. Log: `/tmp/rukh-day1/ui-tests.log`. The shell checks were
also rerun successfully after installation; log:
`/tmp/rukh-day1/ui-shell-tests.log`. Expected preference-save failure diagnostics
appear in negative tests; the suite exited successfully.

These checks establish local source behavior with test doubles. Existing optional
browser fixture: `apps/coworker/test/chat-browser.mjs` (synthetic API, real
Chromium; not executed for this map). No browser, live-provider, deployed
session, or staging qualification is claimed.
