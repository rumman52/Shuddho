# Rukh AI streaming conversation implementation plan

> Execute task-by-task with test-driven development. Do not claim completion until the exact final head passes the required checks.

**Goal:** Add incremental assistant output to the existing Rukh Coworker text chat without weakening durable reply claims, owner isolation, budgets, or the explicit Agent-action boundary.

**Spec:** docs/superpowers/specs/2026-11-04-rukh-streaming-chat-design.md

**Base:** PR #627 test-cleanup branch fix/coworker-speech-test-cleanup-20261104; stack this work on that branch until PR #627 is merged.

## Constraints

- Preserve the existing JSON reply endpoint.
- Use the existing DeepSeek backend key, transport endpoint, provider lease, daily budget, and conversation reply JSON.
- Do not add a migration, new provider, tools, browser/file permissions, or external-action authority.
- Keep both Coworker and reply capabilities default-off; no Vercel, Supabase, Render, auth, or production configuration changes.
- Do not stream provider errors or sensitive request/provider data.
- Keep partial output in memory only; persist only a complete validated response.
- Keep all existing chat, task dispatch, voice, attachment, history, and mobile behavior intact.

## Task 1 — Provider streaming parser (RED → GREEN)

**Files**
- Modify services/coworker/conversation_replies.py
- Test tests/test_conversation_replies.py

- [ ] Add failing tests for valid split SSE chunks, UTF-8/Bangla deltas, [DONE], missing terminal markers, malformed JSON, non-200 responses, finish_reason=length, tool-call/refusal deltas, and 16 KB output bound.
- [ ] Verify the tests fail for the expected missing streaming behavior.
- [ ] Implement DeepSeekReplyModel.stream(messages) using httpx.AsyncClient.stream, an overall deadline, bounded bytes, no tools, and strict terminal validation.
- [ ] Keep generate(messages) and its existing JSON response contract unchanged.
- [ ] Run focused provider tests.

## Task 2 — Durable service producer and SSE route

**Files**
- Modify services/coworker/conversation_replies.py
- Modify services/coworker/api.py
- Test tests/test_conversation_replies.py

- [ ] Add tests proving one claim/reservation, ordered delta events, persisted final reply, provider lease release, duplicate request replay, owner isolation, deletion-during-generation rejection, and provider failure handling.
- [ ] Add a strongly referenced background producer with a bounded 16 KB output and in-memory event queue. Browser disconnect must not cancel already-admitted generation; process loss continues to use the existing interrupted-claim timeout.
- [ ] Reuse claim, finish, and release; never hold a database transaction while waiting for provider output.
- [ ] Add the authenticated /reply/stream route. Perform claim admission before returning StreamingResponse so 409/429/404 remain normal HTTP errors.
- [ ] Emit snapshot, delta, final, and generic error events with no-store and anti-buffering headers.
- [ ] Run focused service/API tests and existing reply tests.

## Task 3 — Authenticated frontend SSE client

**Files**
- Modify apps/web-editor/src/coworker/client.ts
- Test apps/web-editor/src/coworker/client.test.ts

- [ ] Add failing tests for authenticated POST headers, content type validation, arbitrary chunk boundaries, CRLF framing, multiple data lines, snapshot/delta/final handling, malformed frames, incomplete streams, abort, and JSON compatibility.
- [ ] Verify the tests fail for the expected missing stream method/parser.
- [ ] Implement a bounded fetch-based SSE parser. Do not use EventSource or put tokens in URLs.
- [ ] Emit typed AssistantReply snapshots as partial text arrives; keep the existing JSON method for fallback.
- [ ] Run the client tests.

## Task 4 — Incremental reply rendering

**Files**
- Modify apps/web-editor/src/coworker/ConversationWorkspace.tsx
- Modify apps/web-editor/src/coworker/ConversationReply.tsx
- Test apps/web-editor/src/coworker/ConversationReply.test.tsx
- Test apps/web-editor/src/coworker/conversationUsability.test.tsx if needed

- [ ] Add failing tests for partial Markdown rendering, generating accessibility state, final read-aloud availability, stream failure, and conversation-switch isolation.
- [ ] Verify RED before implementation.
- [ ] Update the current assistant reply as deltas arrive; preserve stale-conversation isolation and existing polling recovery.
- [ ] Render partial content with a truthful “Rukh is replying…” state. Do not expose copy/read-aloud actions until completion.
- [ ] Preserve the existing JSON fallback for older test doubles.
- [ ] Run all web-editor tests and build.

## Task 5 — Exact-head verification and handoff

**Files**
- Modify docs/frontend/CHATBOX_COMPLETION_2026-11-04.md
- Modify docs/frontend/MUSE_CHAT_ENHANCEMENTS_2026-11-04.md
- Modify docs/frontend/IMPLEMENTATION_LEDGER.md

- [ ] Run focused Python and frontend tests.
- [ ] Run the complete root Python and JavaScript checks, web-editor build, and mandatory Coworker browser job.
- [ ] Verify the exact final commit SHA and all required CI conclusions.
- [ ] Record any governance, deployment, migration, provider, or activation blocker separately.
- [ ] Open a review PR against the correct base. Do not merge or deploy as part of this slice.
