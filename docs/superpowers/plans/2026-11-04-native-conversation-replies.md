# Native Rukh conversation replies

Continue local commit 3592fccb; remote main remains a8385b5a. Implement one stored assistant response per user message through the existing authenticated conversation API. Frontend presents Chat / Save only modes when runtime manifest advertises chat support, plus per-message reply controls. Chat replies never invoke tools or dispatch Agent work.

- Add nullable assistant_reply JSON to existing messages, migration 0063; redact on conversation deletion and preserve account erasure.
- Default-off SHUDDHO_CONVERSATION_REPLIES_ENABLED requires conversations and backend DeepSeek configuration. Reuse provider capacity and owner daily token budgets; no new orchestrator.
- Atomically claim a message once, reserve budget, release DB transaction before inference, then recheck owner/deletion before publishing. Completed/failed/interrupted claims replay without another model call. Interrupted work requires a new user message, never an implicit provider retry.
- Keep newest 12 messages within a 32 KB serialized prompt budget; current input is never silently truncated. Include completed assistant replies, excluding unfinished output. Attached-source requests use the existing task flow until document context is implemented for chat.
- Use existing bounded DeepSeek transport; reject empty, truncated, tool-calling or oversized output. Plain text rendering prevents executable model markup.
- Test ownership, duplicate calls, changed revisions, budgets, deletion during inference, output errors, bounded context, migration compatibility and frontend retry behavior. Run focused backend tests, full JavaScript suite and affected builds. No live-provider/production-activation claim.

Publication remains blocked by the prior automatic approval decision; this repeated implementation request does not explicitly authorize a public push.

Implemented and locally verified. Browser testing reproduced and corrected a composer pushed below the viewport; source review reproduced and corrected account-erasure foreign-key failures caused by active/expired provider leases. See [final handoff](../../frontend/CHATBOX_COMPLETION_2026-11-04.md) for behavior, evidence, rollout steps and remaining live-verification limits.
