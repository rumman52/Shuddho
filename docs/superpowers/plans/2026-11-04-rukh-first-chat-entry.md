# Rukh First-Chat Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the real Coworker chat composer visible before sign-in, preserve the first draft through authentication, and hand it to the existing authenticated conversation flow.

**Architecture:** Keep authentication and message admission unchanged. Add a focused unauthenticated entry surface in the existing CoworkerGate, show the existing auth form as an accessible modal only when the user chooses to send/sign in, and pass the draft into the existing CoworkerWorkspace/ConversationWorkspace after authentication. If public auth configuration is absent, show an explicit blocked message and never pretend to send.

**Tech Stack:** React 18, TypeScript, Vite, existing @rukh/auth, existing CoworkerClient, node:test, react-test-renderer.

**Spec:** `docs/superpowers/specs/2026-11-04-rukh-responsive-premium-design.md`, `docs/frontend/REAL_CHAT_INTEGRATION_2026-11-04.md`, and the user's approved Coworker-first / first-chat scope.

## Global Constraints

- Reuse the existing authenticated conversation API, durable reply/persistence path and idempotency keys.
- Do not add a second chat backend, database schema, provider, runtime dependency or local fake reply.
- Do not send messages before an authenticated session exists.
- Preserve owner-scoped server authorization and explicit Agent dispatch boundaries.
- Do not change Render, Vercel environment variables, production aliases, databases, auth settings or deployment promotion.
- Keep Projects and Plugins out of this first-chat slice.
- Keep Bangla text, direction-aware input, keyboard/IME behavior, light/dark design tokens and mobile layouts intact.

## Review Focus

- Missing public auth configuration: composer remains visible but sending is explicitly blocked and no API request is made.
- Sign-in/signup/reset/recovery failures: the original draft remains unchanged.
- Session becomes available after sign-in: the draft is handed to the real conversation composer without automatic submission.
- User edits or clears the draft before sending: the latest text, not a stale initial value, is preserved.
- Existing session: authenticated users bypass the entry screen and retain the current Coworker route behavior.

---

### Task 1: Pin first-chat entry and draft-handoff behavior with tests

**Files:**
- Create: `apps/web-editor/src/coworker/CoworkerGate.test.tsx`
- Modify: `apps/web-editor/src/coworker/conversationUsability.test.tsx`
- Modify: `apps/web-editor/test/run-tests.mjs`

**Interfaces:**
- Consumes: current `CoworkerGate`, `ConversationWorkspace`, and test harness.
- Produces: regression tests for visible pre-auth composer, auth-modal draft preservation, and initial draft handoff.

- [ ] **Step 1: Write failing tests** for no-auth composer visibility and honest blocked send, configured-auth modal open/close with draft preservation, and initial draft transfer into ConversationWorkspace.
- [ ] **Step 2: Run the focused web-editor test suite through GitHub Actions** and confirm the new assertions fail because the pre-auth composer/transfer is absent.
- [ ] **Step 3: Record the exact failing CI run and failure reason** before implementation.

### Task 2: Implement the smallest first-chat entry and draft transfer

**Files:**
- Create: `apps/web-editor/src/coworker/CoworkerEntry.tsx`
- Create: `apps/web-editor/src/coworker/coworker-entry.css`
- Modify: `apps/web-editor/src/coworker/CoworkerGate.tsx`
- Modify: `apps/web-editor/src/coworker/CoworkerWorkspace.tsx`
- Modify: `apps/web-editor/src/coworker/ConversationWorkspace.tsx`
- Modify: `apps/web-editor/src/coworker/CoworkerGate.test.tsx`
- Modify: `apps/web-editor/src/coworker/conversationUsability.test.tsx`

**Interfaces:**
- `CoworkerGate` accepts an optional auth-client factory for deterministic tests; production defaults to `getRukhAuthClient`.
- `CoworkerWorkspace` accepts `initialDraft?: string` and `onInitialDraftChange?: (draft: string) => void`.
- `ConversationWorkspace` accepts the same draft props, initializes the existing composer from `initialDraft`, and reports edits/accepted sends back to the gate.

- [ ] **Step 1: Implement the pre-auth composer** with starter prompts, clear account-access status, mobile-safe sizing and the existing Rukh tokens.
- [ ] **Step 2: Move the existing sign-in/signup/reset/recovery form into an accessible modal**; open it only when auth is configured and the user requests to send/sign in. Keep the draft controlled by CoworkerGate.
- [ ] **Step 3: Transfer the draft into the authenticated conversation composer** without automatically submitting it; clear the parent copy only when the existing message admission succeeds.
- [ ] **Step 4: Keep the no-auth path honest**: preserve the draft, show an explicit configuration error on send, and make no API request.
- [ ] **Step 5: Run focused tests and the complete web-editor test/build commands** through exact-head CI.

### Task 3: Review, evidence and handoff

**Files:**
- Modify: `docs/coworker-roadmap/PROGRESS.md`
- Create: `docs/coworker-roadmap/tasks/CW-UI-01-preauth-chat-entry.md`
- Modify: `docs/frontend/IMPLEMENTATION_LEDGER.md`

- [ ] **Step 1: Verify exact-head frontend tests and builds**; report unrelated CI failures separately.
- [ ] **Step 2: Review the diff** for draft loss, unintended message dispatch, auth regressions, keyboard/accessibility issues and mobile overflow.
- [ ] **Step 3: Update the task contract, implementation ledger and progress checkpoint** with exact branch/SHA/PR/checks and the remaining production auth/backend blockers.
- [ ] **Step 4: Leave the PR unmerged and draft**; production configuration and activation are outside this task.
