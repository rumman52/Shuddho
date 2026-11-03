# Rukh conversation usability implementation plan

**Goal:** Finish the conversation entry flow and expose real Agent progress inside the chat-first workspace.
**Base:** main a8385b5a2849afd01486d86106cfa4ea491f46fd, merged PR #615.
**Architecture:** Reuse owner-authenticated conversation and Agent APIs. Keep saved messages and explicit task dispatch separate. Preserve independent Coworker and Editor builds, warm-neutral/green themes, Bangla text and existing approval controls.
**Spec:** docs/frontend/ARCHITECTURE.md and the user-approved Coworker-first direction.

## Task 1 — Conversation entry and discovery
- [x] Add renderer regressions for an always-visible composer, first-message creation, unchanged lost-response retries, new conversation, history search, starters and keyboard composition.
- [x] Verify regressions fail on base; implement in ConversationWorkspace.tsx.
- [x] Keep initial list loading, rollout-disabled and transient-error states distinct; never create work while list availability is unknown.
- [x] Place errors/notices in the visible thread on mobile. Preserve manual titled creation.

## Task 2 — Inline real Agent progress
- [x] Add tests for owned linked run status, partial completion, tool summaries, failed fetch/retry and stale response isolation.
- [x] Implement ConversationRunStatus.tsx using client.agentRun with abortable refresh; no fabricated assistant text or implicit dispatch.
- [x] Show the exact run's returned message, plan and results, with a route to existing full Agent details/approval controls.

## Task 3 — Visual polish and verification
- [x] Style starters, history search, user messages, run cards and composer with shared theme tokens and 44px touch controls.
- [x] Run full JavaScript tests and affected three frontend builds.
- [ ] Exercise desktop and mobile browser fixtures if browser runtime is available; disclose synthetic data.
- [ ] Update frontend ledger and roadmap handoff; publish a review branch/PR without merging or production activation.

## Review focus
First-message retry after response loss; IME Enter handling; old run responses after conversation changes; rollout errors hiding the composer; body overflow and keyboard focus on phones. Real assistant chat replies, voice/image generation, WhatsApp and secure VM/payment infrastructure need separate backend/provider work and are not claimed by this frontend slice.

## Verification checkpoint
Full root npm test passed: 167 web-editor tests plus standalone Coworker/Editor and other workspace checks. Three frontend builds passed. Browser step blocked by unavailable Chromium and invalid/truncated download; no visual verification claimed. Agent review completed; two Important findings reproduced and fixed (Unicode title boundary and historical-run request fan-out). Minor deferred: optional tool-result JSON presentation. Remote exact-head checks pending.
