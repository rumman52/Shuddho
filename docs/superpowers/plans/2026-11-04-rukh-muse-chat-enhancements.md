# Rukh AI Muse-inspired conversation enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Complete the practical conversation features missing from the current Coworker chat UI while preserving the approved Rukh architecture and execution boundaries.

**Architecture:** Extend the existing owner-authenticated conversation API only for title updates, using the existing conversation row and `updated_at` as an optimistic concurrency token. Implement export and safe Markdown rendering in the frontend, and expose the existing document-upload/source-selection APIs in the conversation context panel. Keep chat replies text-only and separate from Agent dispatch.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, React 18, TypeScript, Vite, existing Node/Python test suites. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-03-rukh-premium-workspaces-design.md`, plus the existing chat contract in `docs/frontend/CHATBOX_COMPLETION_2026-11-04.md`.

## Global Constraints

- Coworker remains the default workspace; Web Editor remains separate at `/editor`.
- Messages are private owner-scoped records. Saving or renaming a message never grants Agent execution authority.
- Agent dispatch and external actions remain explicit and preserve existing approvals.
- Selected files remain untrusted task inputs. Direct text chat does not read file contents.
- No new AI provider, streaming protocol, message schema, database migration, Supabase schema/RLS change, voice/image generation endpoint, or execution authority.
- Use existing design tokens, keyboard focus, reduced-motion behavior, mobile drawers and 44px touch targets.
- Do not change production environment variables, database, auth settings, aliases or deployments. Do not merge this branch.

## Review Focus

- A stale tab must not overwrite a newer conversation title; foreign owners must receive 404.
- PATCH preflight must be permitted for the configured API origin without broadening allowed origins or headers.
- Markdown links must reject javascript/data/file URLs; raw HTML must remain inert text.
- Very long, Unicode and Bangla replies must wrap and remain readable on narrow screens.
- Uploaded files and artifacts must remain owner-scoped, visibly untrusted and limited to five per message; chat must not imply that it can read them.

---

### Task 1: Owner-scoped conversation rename and PATCH CORS

**Files:**
- Modify: `services/coworker/conversation_schemas.py`
- Modify: `services/coworker/conversation_repository.py`
- Modify: `services/coworker/api.py`
- Modify: `services/api/shuddho_api/app.py`
- Test: `tests/test_conversations.py`
- Test: `tests/test_api_app.py`

**Interfaces:**
- Add `ConversationRename(title: str, expected_updated_at: str)`.
- Add `ConversationRepository.rename(owner: str, conversation_id: str, request: ConversationRename) -> dict`.
- Add authenticated `PATCH /api/v1/conversations/{conversation_id}`; return the existing conversation DTO with `Cache-Control: no-store`.
- Keep the existing owner lock order and use the exact returned `updated_at` string as the concurrency token.

- [x] Write repository/API tests for successful rename, stale revision conflict, same-title idempotence and foreign-owner 404.
- [x] Write a CORS preflight test for PATCH using the existing allowed origin.
- [x] Run the focused tests and confirm the new assertions fail before implementation.
- [x] Implement the schema, locked repository update, authenticated route and PATCH method in the existing CORSMiddleware allowlist.
- [x] Run `python -m pytest tests/test_conversations.py tests/test_api_app.py -q`.
- [x] Commit as `feat(coworker): add revision-checked conversation rename`.

### Task 2: Rename controls and complete conversation export

**Files:**
- Modify: `apps/web-editor/src/coworker/client.ts`
- Modify: `apps/web-editor/src/coworker/ConversationWorkspace.tsx`
- Create: `apps/web-editor/src/coworker/conversationExport.ts`
- Test: `apps/web-editor/src/coworker/conversationUsability.test.tsx`
- Test: `apps/web-editor/src/coworker/conversationExport.test.ts`
- Modify: `apps/web-editor/test/run-tests.mjs`

**Interfaces:**
- Add `CoworkerClient.renameConversation(id, title, expectedUpdatedAt): Promise<ConversationRecord>`.
- Add pure Markdown and JSON export builders that consume the selected `ConversationRecord` and the fully paginated `ConversationMessageRecord[]`.
- Provide inline rename with save/cancel and a two-format export menu; downloads stay local to the browser.

- [x] Add tests for rename success, rename conflict feedback, Markdown export and JSON export.
- [x] Run the focused frontend tests and confirm the new assertions fail before implementation.
- [x] Implement the client method, inline rename, and complete-history exports.
- [x] Run `npm test --workspace @shuddho/web-editor`.
- [x] Commit as `feat(frontend): add conversation rename and export`.

### Task 3: Safe Markdown rendering for assistant replies

**Files:**
- Create: `apps/web-editor/src/coworker/MarkdownMessage.tsx`
- Create: `apps/web-editor/src/coworker/markdown-message.css`
- Modify: `apps/web-editor/src/coworker/ConversationReply.tsx`
- Create: `apps/web-editor/src/coworker/markdownMessage.test.tsx`
- Modify: `apps/web-editor/test/run-tests.mjs`

**Interfaces:**
- Render headings, paragraphs, ordered/unordered lists, blockquotes, inline emphasis/code, fenced code blocks, horizontal rules and safe external/mail links.
- Never execute raw HTML. Accept only http, https and mailto link protocols; reject credentials and unsafe schemes.

- [x] Add renderer tests for supported formatting, Bangla text, code blocks, raw HTML and unsafe links.
- [x] Run the focused renderer tests and confirm they fail before implementation.
- [x] Implement the renderer without a new runtime dependency and replace the plain-text reply paragraph.
- [x] Run `npm test --workspace @shuddho/web-editor` and `npm run build --workspace @shuddho/web-editor`.
- [x] Commit as `feat(frontend): render safe Markdown in coworker replies`.

### Task 4: First-class file and artifact attachments

**Files:**
- Modify: `apps/web-editor/src/coworker/ConversationWorkspace.tsx`
- Create: `apps/web-editor/src/coworker/conversation-enhancements.css`
- Test: `apps/web-editor/src/coworker/conversationUsability.test.tsx`

**Interfaces:**
- Reuse `CoworkerClient.upload(File)` and `workspaceManifest()`; do not add an upload endpoint.
- Allow selecting existing uploaded document versions and generated artifacts, with a maximum of five distinct source IDs.
- Show selected source labels on saved messages and disclose that attachments are available to explicit Start task dispatch, not direct AI chat.

- [x] Add tests for upload success/failure, selection limit, attachment labels and chat-vs-task disclosure.
- [x] Run focused frontend tests and confirm the new assertions fail before implementation.
- [x] Implement upload, source selection, removal and message provenance display.
- [x] Run `npm test --workspace @shuddho/web-editor` and `npm run build --workspace @shuddho/web-editor`.
- [x] Commit as `feat(frontend): complete conversation source attachments`.

### Task 5: Handoff and release evidence

**Files:**
- Modify: `docs/frontend/CHATBOX_COMPLETION_2026-11-04.md`
- Modify: `docs/frontend/IMPLEMENTATION_LEDGER.md`
- Create: `docs/frontend/MUSE_CHAT_ENHANCEMENTS_2026-11-04.md`

- [x] Record implemented behavior, tests, commit IDs and remaining capability gaps in `docs/frontend/MUSE_CHAT_ENHANCEMENTS_2026-11-04.md`.
- [ ] Run the complete Python and frontend CI checks on the exact branch head.
- [x] Review the merged source and regression coverage for owner isolation, unsafe Markdown links, source provenance, mobile layout and explicit Agent dispatch.
- [x] Open a documentation handoff review PR; do not merge or deploy.

