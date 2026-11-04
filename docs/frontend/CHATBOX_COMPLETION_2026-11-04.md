# Rukh AI text chat implementation — 4 November 2026

The Coworker chatbox can save a user message, request an authenticated AI text reply, retain the answer in conversation history, and recover after a lost HTTP response without resending the message or repeating an already claimed inference. The composer stays inside the viewport while history scrolls. Work is on `feat/rukh-conversation-usability-20261104`, continuing local commit `3592fccb` from main `a8385b5a`.

## User-visible behavior

- Composer visible on first entry; first message creates a titled conversation. New chat, title search, English/Bangla starters and IME-safe Enter/Shift+Enter remain available.
- Chat with Rukh and Save only modes appear when the authenticated runtime manifest advertises AI replies. Otherwise users can save a brief and explicitly choose Start task.
- User bubbles, Rukh answers, pending/error/interrupted states and Copy answer. Answers render as escaped plain text; model-generated HTML is never executed.
- Recent complete turns form reply context. If older turns do not fit, the reply discloses that limitation.
- A failed connection offers Check reply again for the same stored message. Definitive failed/interrupted inference requires a new message; it never silently spends another model call.
- Desktop history/context columns and tablet/phone drawers, keyboard focus return, light/dark mode, latest-answer scrolling, Bengali font fallback and visible composer. Reading older messages does not trigger automatic scrolling on unchanged polls.
- Start task still explicitly starts Agent work, including attached documents; chat itself has no tools or file contents.

## Backend contract

Migration `0063` adds nullable `assistant_reply` JSON to `cw_conversation_messages`. `POST /api/v1/conversations/{conversation_id}/messages/{message_id}/reply` requires authentication and `expected_sequence`. Replies and history are owner scoped and uncached. The message, conversation and account are locked before the durable inference claim; no database transaction remains open during the provider request.

The existing DeepSeek transport is called with a backend-only key, no tools, no streaming and a 1,024-token output bound. Context uses the newest 12 whole user turns and completed replies within a 32,000-byte serialized UTF-8 budget. An oversized latest message is rejected explicitly. Empty, incomplete, tool-calling or oversized output is rejected. The existing owner daily budget and shared provider leases reserve a conservative prompt/output allowance, including on uncertain failures.

Completed, failed and interrupted claims replay without inference. A generating claim older than 120 seconds is shown as interrupted after process loss. Finishing inference rechecks account/conversation ownership and deletion. Conversation deletion redacts replies; active provider leases explicitly block account erasure with 409, while expired leases can be removed so account erasure succeeds. Anonymous aggregate provider usage is retained without refund.

## Verification

- Focused conversation/context/dispatch/retention/authenticated-manifest suite: **92 passed, zero skipped**. Tests use migrated SQLite stores and mocked model transport, not live DeepSeek.
- Reply tests: **21 passed**, including active and expired account-erasure leases. Both erasure regressions first reproduced foreign-key failures; the final implementation resolves them.
- Full root JavaScript suite: passing, including **169 web-editor tests**, Coworker **4**, Editor **1**, and existing production API/gateway/shared/NLP checks.
- TypeScript and Vite builds: web-editor, Coworker and Editor pass. Coworker retains the existing bundle-size warning.
- Real Chromium checks of the workspace with a synthetic API: **five viewports pass** (1440×1000, 1366×768, 1024×768, 390×844, 375×812). Checks include the composer fully inside the initial viewport and after replies, no horizontal overflow, send/reply, Shift+Enter, new chat, search, drawer Escape/focus, dark mode and no page errors. The initial laptop visibility assertion failed before the layout correction.
- The browser script is `apps/coworker/test/chat-browser.mjs`; it uses installed Playwright Chromium or `RUKH_BROWSER_EXECUTABLE`. An optional `RUKH_BROWSER_BENGALI_FONT` supplies the same Noto Serif Bengali webfont on offline test hosts. The ordinary Google Fonts import and device fallback remain the production font path.
- Read-only agent review found the account-erasure blocker, verified the correction and independently ran all 21 reply tests. No remaining Critical/Important issue was reported. Provider-capacity wording was also corrected to describe manual chat retry.

Live provider responses, production PostgreSQL races, real signed-in browser sessions, exact branch CI and deployed behavior remain unverified. This implements text chat; it does not establish token streaming, rich Markdown rendering, voice/image generation, file-aware chat or full Muse parity.

## Release handoff

1. Publish and review this branch, then run required remote CI. Publication is currently blocked by the automatic approval review pending explicit permission to push to the public repository.
2. Before starting the new backend version, run `python -m services.coworker.migrate` with the existing `SHUDDHO_COWORKER_DATABASE_URL` to apply migration 0063. The schema must exist even while the new reply feature is off because history queries read the new column.
3. Deploy the backend and frontend with the existing authentication, API base and Coworker configuration. Keep provider keys exclusively in the backend.
4. To enable text replies, configure `SHUDDHO_CONVERSATIONS_ENABLED=true`, `SHUDDHO_CONVERSATION_REPLIES_ENABLED=true` and the existing `DEEPSEEK_API_KEY`. Normal Coworker availability/authentication and owner/shared budgets still apply. No new credentials or production settings were changed in this implementation.
5. Verify the authenticated runtime manifest advertises `conversation_replies`, send a short message, refresh to recover its answer, test mobile composition, and verify another account cannot access the conversation.

The additive column can remain if the feature is disabled or application code is rolled back. Dropping it would erase stored assistant replies and is not part of ordinary rollback.
