# Coworker token streaming — implementation plan

**Date:** 4 November 2026  
**Base:** PR #627 speech-lifecycle test fix branch  
**Branch:** `feat/coworker-streaming-replies-20261104`

## Goal

Make direct Coworker chat render assistant text as it arrives, with a durable completed reply and safe interruption semantics. Preserve the existing non-streaming endpoint for older clients and keep the feature behind the authenticated runtime capability.

## Boundaries

- Use the existing DeepSeek chat-completions provider, owner-scoped conversation records, daily budget reservation and provider-capacity lease.
- No tools, action execution, file access, browser access, memory mutation or agent dispatch is introduced into direct chat.
- The provider stream must finish with a valid stop reason and `[DONE]`; malformed, tool-call, refused, over-limit or incomplete streams fail closed.
- Persist only a completed final answer. Partial text is transient in the browser; failure clears it and interruption is durably marked.
- Client disconnect, thread change and abort must close the upstream provider stream, release the capacity lease and settle the durable claim.
- Claim/authorization/budget errors must be returned as normal HTTP responses before SSE headers are sent.
- Keep the existing JSON reply endpoint for older clients and expose streaming as an additional capability.

## Acceptance

1. DeepSeek SSE parsing validates UTF-8 deltas, exactly one choice, no tool calls/refusals, output byte limits, `finish_reason=stop` and `[DONE]`.
2. A single durable claim prevents duplicate inference; replay of completed/generating/failed states does not start another provider call.
3. Successful streams persist one completed reply; provider failures persist a redacted failed state with no partial text.
4. Generator close, client abort and cancellation during the threadpool claim mark committed work interrupted and release provider capacity.
5. The API emits authenticated `text/event-stream` with `Cache-Control: no-store` and `X-Accel-Buffering: no`; claim errors retain their HTTP status.
6. Streaming uses the existing authenticated conversation-reply capability; older API deployments fall back to the JSON reply route on a route-level 404, without adding a new release-manifest key.
7. The client parses split UTF-8 SSE frames, authenticates requests, rejects EOF without a final event and forwards deltas.
8. The Coworker UI renders partial Markdown progressively, preserves auto-scroll only while following the latest message, and retains JSON fallback when streaming is not advertised.
9. Backend tests, frontend tests/builds, mandatory Coworker integration, root CI and exact-head verification pass.

## Implementation sequence

- [x] Add backend service/provider/route tests before implementation.
- [x] Add authenticated DeepSeek SSE parsing and durable stream settlement.
- [x] Add the streaming API route and runtime capability.
- [x] Add the authenticated browser SSE client and progressive reply rendering.
- [ ] Run backend and focused frontend tests on the exact branch head.
- [ ] Run full CI including the mandatory Coworker browser/integration job.
- [ ] Update the implementation ledger and Muse parity handoff with exact verification evidence.
- [ ] Obtain review; do not merge or deploy without explicit authorization.

## Known deployment constraints

- Render staging PostgreSQL is suspended after its 31 October expiry.
- The connected Vercel team does not currently expose a Rukh project.
- Production API auto-deployed the earlier merged source commit; no environment or deployment settings are changed by this branch.
