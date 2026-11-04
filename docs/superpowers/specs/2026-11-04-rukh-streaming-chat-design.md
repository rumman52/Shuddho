# Rukh AI streaming conversation design — 4 November 2026

## Status

Proposed implementation contract for the next Coworker chat slice. This expands the previously approved text-only chat contract; it does not enable the feature in any environment or claim full Muse parity.

## Goal

Make direct Coworker chat feel responsive like modern assistant products by rendering provider output as it arrives, while retaining the existing durable message claim, owner isolation, provider budget, and explicit Agent-action boundary.

## User experience

- A sent user message immediately receives a visible assistant response area.
- Text appears incrementally as the provider emits content; Bangla and Unicode remain intact.
- The response remains marked as generating until the provider sends a complete, validated terminal result.
- A completed response is persisted and recoverable from conversation history.
- A second request for the same message never starts a second inference. Existing completed/failed/interrupted replies replay; an active claim returns its current generating snapshot.
- Existing JSON reply endpoint remains available for compatibility.
- Composer, history, attachments, Chat/Save-only modes, voice dictation, and explicit Start task behavior remain unchanged.

## Architecture

1. Add an authenticated POST endpoint at /api/v1/conversations/{conversation_id}/messages/{message_id}/reply/stream using server-sent events.
2. Reuse the existing ConversationReplyService claim, owner/account/conversation locks, DailyUsage reservation, shared provider lease, and finish persistence. No migration or new table.
3. Add a DeepSeek streaming adapter using the existing backend-only API key and endpoint. Request stream=true; never send tool definitions. Parse OpenAI-compatible data frames, enforce response/output bounds, and require a valid finish_reason=stop plus [DONE].
4. Emit only snapshot, delta, final, and generic error events. Do not emit provider headers, error bodies, raw request content, or credentials.
5. Keep a bounded maximum generated response of 16 KB UTF-8, matching the current durable reply contract. Partial text is sent to the browser but is not written to the database. Only a complete validated result is persisted.
6. Run the provider producer as a strongly referenced task owned by the service. If the browser disconnects, the already-authorized generation continues and persists; process loss still uses the existing 120-second interrupted-claim recovery. The producer always releases its provider lease.
7. The frontend uses authenticated fetch (not EventSource, because the endpoint is POST and requires a bearer token), parses SSE incrementally, updates the existing assistant reply in place, and preserves the current JSON fallback for test doubles/older API deployments.

## Safety and non-goals

- Chat remains tool-free and cannot dispatch Agent runs or external actions.
- Streaming does not add browser access, file-content access, memory authority, or action approval.
- Attachments remain task-only; direct chat with selected sources remains blocked.
- No image understanding/generation, provider-generated audio, real-time voice, new provider, database migration, schema/RLS change, production configuration, or deployment activation in this slice.
- Do not bypass VITE_COWORKER_ENABLED, SHUDDHO_CONVERSATIONS_ENABLED, or SHUDDHO_CONVERSATION_REPLIES_ENABLED.
- Do not merge or deploy until exact-head CI, review, migration/provider readiness, and release governance are satisfied.

## Failure handling

- Non-200, malformed SSE, provider timeout, network loss, refusal/tool-call frames, truncation, missing terminal marker, empty output, or output above 16 KB produce a generic failed reply and release the lease.
- A browser disconnect does not cancel the server producer. A process crash leaves the existing generating claim to become interrupted after the current timeout.
- Conversation deletion during inference prevents late output from being stored; the client receives a generic unavailable error if still connected.
- Existing daily budget and provider-capacity admission remain authoritative.

## Verification

- Unit tests for SSE framing, split UTF-8 chunks, terminal markers, finish reasons, tool/refusal rejection, timeouts and output bounds.
- Service tests for one durable claim, incremental deltas, final persistence, lease release, duplicate replay, owner isolation, deletion races and disconnect continuation.
- API tests for authenticated owner-scoped SSE, cache/proxy headers, validation and foreign-owner 404.
- Frontend tests for chunk boundaries, partial rendering, final state, stream failure, abort, and JSON fallback.
- Full Python suite, web-editor tests/build, root test-and-build, mandatory Coworker browser job and exact-head governance check.
