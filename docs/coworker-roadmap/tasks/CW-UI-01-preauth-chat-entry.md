# CW-UI-01 task contract

- Objective and user-visible behavior: Show a usable first-message composer on unauthenticated `/coworker`; on send, open the existing sign-in flow as an accessible modal when auth is configured; preserve the draft through auth and place it in the real authenticated composer without auto-sending. If auth configuration is absent, preserve the draft and explain that it has not been sent.
- Dependency tasks and current evidence: Main `0578ef9b7197c5f8565f914238b4275fc80c8b96`; PRs #615, #616, #628, #631 and #632 merged. Production Vercel deployment is READY on this SHA. Visible Vercel environment inventory has `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` only on preview targets; no production entries were returned.
- Base branch/SHA: `main` / `0578ef9b7197c5f8565f914238b4275fc80c8b96`.
- Work branch/PR: `feat/rukh-first-chat-entry-20261104` / draft PR to be opened after the test-only commit.
- Existing interfaces to reuse: `CoworkerGate`, `getRukhAuthClient`, `CoworkerWorkspace`, `ConversationWorkspace`, `CoworkerClient`, current conversation create/append/reply stream APIs.
- Exact files to create/modify: `CoworkerEntry.tsx`, `coworker-entry.css`, `CoworkerGate.test.tsx`; modify `CoworkerGate.tsx`, `CoworkerWorkspace.tsx`, `ConversationWorkspace.tsx`, `conversationUsability.test.tsx`, `test/run-tests.mjs`; update `docs/coworker-roadmap/PROGRESS.md`, `docs/frontend/IMPLEMENTATION_LEDGER.md`; create this task contract and the plan.
- New interface signatures / schema and compatibility: `CoworkerGate({ authClientFactory? })`; `CoworkerWorkspace({ initialDraft?, onInitialDraftChange? })`; `ConversationWorkspace({ initialDraft?, onInitialDraftChange? })`. Existing call sites remain valid because all additions are optional.
- Acceptance scenarios and assertions: composer renders before auth; starter fills without sending; missing auth shows blocked status and keeps draft; configured auth opens/closes dialog without clearing draft; successful auth displays the same draft in the existing composer; editing and accepted send synchronize/clear parent draft; no auto-send or Agent dispatch.
- Reproduction / initial failure: current CoworkerGate returns only the sign-in card when there is no session; with production auth vars absent, there is no message composer to use.
- Expected failure outcomes: missing auth config prevents sending with an explicit message; auth/API failures do not discard the draft; no unauthenticated request reaches CoworkerClient.
- Tests and required CI commands: `npm run test --workspace @shuddho/web-editor`; `npm run build --workspace @shuddho/web-editor`; full root `npm test` when the exact-head workflow permits.
- Secrets / owner / grant / approval / egress boundaries: no credentials or service keys added; no unauthenticated API access; existing owner-bound server checks remain authoritative; no external action or Agent dispatch.
- Budget / timeout / cancellation / revocation behavior: unchanged; this UI slice does not add provider calls, retries or runtime work.
- Default-off gate and rollback: no new backend capability flag; revert this frontend PR to roll back. Existing backend conversation/reply gates remain unchanged.
- External prerequisites: production public auth config and a working authenticated backend mount/database remain external blockers; not modified here.
- Out of scope: Render/backend deployment, Vercel env changes, production alias/promotion, database/schema/migration, provider credentials, Projects, Plugins, image/audio generation, Agent/transaction activation.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Pending | |
| Repository-verified | Pending | |
| Staging-verified | Not performed | |
| Production-qualified | Not performed | |
| Activated | No | |

- Test pass/fail/skip counts:
- Exact-head CI links:
- Review findings and resolution:
- Residual risks:
- Next exact action:
