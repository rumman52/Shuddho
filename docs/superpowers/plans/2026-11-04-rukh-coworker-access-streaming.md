# Rukh AI Coworker access and streaming integration plan

> Execute task-by-task with test-driven development. Do not claim completion until the exact final head passes the required checks.

**Goal:** Make the Coworker chat path behave like a professional assistant interface by integrating the existing true provider-streaming implementation onto current `main`, repairing OAuth callback routing, and making backend availability states explicit without bypassing release controls.

**Primary acceptance contract:** the user's `writing-block(4).md` master specification (uploaded 4 November 2026). The specification requires a functional Coworker chat, real backend behavior, safe integrations, complete QA, and strict production/staging separation.

**Streaming design:** `docs/superpowers/specs/2026-11-04-rukh-streaming-chat-design.md`.

**Base:** `main` at `a61f158736b6558fc5caa7906f7d3ef48c40505c`.

**Working branch:** `feat/rukh-coworker-access-streaming-20261104`.

## Evidence and root causes

- Production Vercel configuration does not include `VITE_COWORKER_ENABLED`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, or `VITE_COWORKER_API_BASE_URL`. Coworker-enabled values exist only in a branch-scoped Preview configuration.
- `WorkspaceShell` intentionally keeps Coworker fail-closed unless `VITE_COWORKER_ENABLED === "true"`.
- The Preview API points to `shuddho-api-staging.onrender.com`. Its Render staging Postgres database is suspended; the staging API is not on the current source revision and has no configured health-check path.
- The Supabase staging project is healthy and is used for Auth; application conversation data uses the separate Render Postgres database.
- PR #628 implemented provider SSE and incremental UI, but it was merged into `fix/coworker-speech-test-cleanup-20261104`, not `main`. Current `main` still uses the JSON reply path.
- Main CI's mandatory browser job fails during Gmail OAuth verification. `/oauth/google/callback`, `/oauth/microsoft/callback`, and `/oauth/linkedin/callback` are currently treated as unknown routes and fall back to the workspace home.
- Main governance audit fails because GitHub reports `main.protected=false` and required-check enforcement is off.
- PostHog project 675660 reports no ingested events, no events seen in the last 30 days, and zero feature flags. The repository has no PostHog SDK initialization or event capture code.

## Global constraints

- Never merge this branch into `main`, deploy, or enable production features without the required human authorization and release gates.
- Keep `VITE_COWORKER_ENABLED`, `SHUDDHO_CONVERSATIONS_ENABLED`, and `SHUDDHO_CONVERSATION_REPLIES_ENABLED` fail-closed by default.
- Do not modify Production Vercel variables, Render production services, production databases, credentials, feature flags, or aliases.
- Do not restore, recreate, upgrade, delete, or migrate the suspended staging database without explicit authorization and a verified backup/recovery plan.
- Do not route Preview to production data. Do not fabricate a local/mock backend as a substitute for real Coworker access.
- Preserve existing JSON reply compatibility, voice controls, attachments, conversation history, task dispatch, approvals, editor routes, and mobile behavior.
- Direct chat remains tool-free and cannot read attached file contents or execute Agent actions. Explicit Start task and existing approvals remain the only Agent/external-action path.
- Stream actual provider deltas; do not simulate streaming with timers. Persist only a complete validated reply. Never stream provider diagnostics, credentials, private headers, or raw request data.
- Do not log prompts, response contents, access tokens, or sensitive document contents in analytics.
- Keep changes small, reviewable, and covered by regression tests.

## Rulings

1. **Production remains gated.** The master specification wants Coworker as the default experience, but it also prohibits production changes until staging is qualified and explicitly authorized. The stricter safety requirement wins: retain the fail-closed production gate and prepare a Preview-only path. Cost if wrong: production Coworker remains unavailable until the staging dependency is restored and the owner authorizes release.
2. **Port PR #628 rather than merging its old PR.** PR #628 targets a feature branch that diverged from current main. Its file-level implementation and tests will be applied to a fresh main-based branch, preserving the later dictation fix in #629. Cost if wrong: an overlooked overlapping change could be lost; exact-head CI and final review are required.
3. **Do not recover the database in this branch.** The staging database is suspended and no verified restorable backup is available through the current tools. Any paid, destructive, or data-recovery operation requires owner authorization. Cost if wrong: staging remains blocked and no live Coworker qualification can be claimed.

## Task 1 — Integrate true provider streaming (RED → GREEN)

**Source:** existing PR #628 branch `fix/coworker-speech-test-cleanup-20261104`, streaming plan and design spec.

**Files**
- `services/coworker/conversation_replies.py`
- `services/coworker/api.py`
- `tests/test_conversation_replies.py`
- `apps/web-editor/src/coworker/client.ts`
- `apps/web-editor/src/coworker/client.test.ts`
- `apps/web-editor/src/coworker/ConversationWorkspace.tsx`
- `apps/web-editor/src/coworker/ConversationReply.tsx`
- `apps/web-editor/src/coworker/ConversationReply.test.tsx`
- `apps/web-editor/src/coworker/conversationUsability.test.tsx`

- [ ] Port provider streaming tests and verify the current-main implementation fails them.
- [ ] Port authenticated SSE route/service tests and verify RED before implementation.
- [ ] Port the bounded DeepSeek SSE parser; require valid terminal `finish_reason=stop` and `[DONE]`; reject malformed, unsafe, truncated, oversized, timed-out, or non-200 streams.
- [ ] Preserve the existing durable claim, account/conversation locks, budget reservation, provider lease, owner isolation, and JSON reply endpoint.
- [ ] Start a strongly referenced producer before returning SSE headers; browser disconnect must not cancel admitted work; persist only the complete validated reply.
- [ ] Add authenticated POST SSE parsing with chunk/CRLF/UTF-8 handling, bounded buffers, abort support, and JSON fallback.
- [ ] Render partial Markdown and accessible generating state; do not expose copy/read-aloud actions until completion.
- [ ] Run focused Python/frontend tests and the full relevant suites.

## Task 2 — Repair provider OAuth callback routing (RED → GREEN)

**Files**
- `apps/web-editor/src/appRoutes.mjs`
- `apps/web-editor/test/app-routes.test.mjs`

- [ ] Add failing route tests for Google, Microsoft, and LinkedIn callback paths, including query strings.
- [ ] Verify enabled Coworker callbacks resolve to Coworker and disabled Coworker callbacks fail closed to home.
- [ ] Route only the known provider callback paths to Coworker; do not create a general unknown-route bypass.
- [ ] Run route tests and the mandatory Coworker browser workflow; Gmail must complete the callback and show the connected state.

## Task 3 — Make chat availability explicit (RED → GREEN)

**Files**
- `apps/web-editor/src/coworker/ConversationWorkspace.tsx`
- `apps/web-editor/src/coworker/conversationUsability.test.tsx`
- Any small, directly related styles/test files only if required.

- [ ] Add failing tests distinguishing `checking`, `ready`, `disabled`, and `unreachable` states.
- [ ] Show a concise, accessible status near the composer when AI replies are disabled or the runtime manifest cannot be reached.
- [ ] Add a real retry action that re-fetches the runtime manifest; never convert an unreachable API into a false “ready” state.
- [ ] Preserve Save-only behavior when replies are disabled, and preserve the existing disabled composer/retry behavior when conversations cannot load.
- [ ] Do not expose provider secrets or internal infrastructure credentials in the UI.

## Task 4 — Engineering audit and handoff documentation

Create/update:
- `docs/engineering/RUKH_CURRENT_STATE_AUDIT.md`
- `docs/engineering/RUKH_FEATURE_PRESERVATION_MATRIX.md`
- `docs/engineering/RUKH_TECHNICAL_RISK_REGISTER.md`
- `docs/frontend/IMPLEMENTATION_LEDGER.md`
- `docs/frontend/MUSE_CHAT_ENHANCEMENTS_2026-11-04.md`
- `docs/coworker-roadmap/PROGRESS.md`

- [ ] Separate implemented, merged, preview-configured, staging-verified, production-enabled, and production-qualified states.
- [ ] Record exact GitHub SHAs, CI run URLs/conclusions, Vercel env scopes/deployment limits, Render API/database state, Supabase Auth state, and PostHog ingestion evidence.
- [ ] Mark PR #628 as not integrated into main until this branch's changes land; correct all stale “streaming merged” claims.
- [ ] Record every external blocker and the owner action needed; do not mark blocked work complete.

## Task 5 — Verification and final review

- [ ] Run frontend tests and builds.
- [ ] Run root JavaScript tests and build.
- [ ] Run Python lightweight tests and the mandatory Coworker test suite, including the new streaming module.
- [ ] Run the mandatory browser workflow and inspect screenshots/logs for the OAuth callback flow.
- [ ] Verify exact final-head CI; do not use predecessor commits as evidence.
- [ ] Perform a separate whole-branch self-review because no independent reviewer subagent is available in this environment.
- [ ] Open a review PR against `main`; do not merge or deploy.
- [ ] Report staging/production/PostHog blockers separately from source-code completion.

## Completion boundary

Source implementation can be completed in this branch. Live Coworker access cannot be claimed until the owner-authorized staging database recovery/replacement, staging API/worker qualification, Preview environment setup, signed-in browser test, and PostHog event-ingestion verification have passed. Production remains unchanged.
