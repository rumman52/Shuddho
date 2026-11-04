# Coworker entry recovery — 4 November 2026

## Contract and reproduced cause

Execute the first dependency of the attached frontend completion prompt: establish what the deployed URL serves and repair the missing workspace entry without activating unqualified execution.

Base: `dce675364ce98b16309731e743ce7b8357eef4e6`. Live browser at `https://rukhai.vercel.app/coworker` rendered RukhHome with disabled Private preview, not CoworkerGate or ConversationWorkspace. The live `/shuddho-rollout-manifest.json` reports the same revision and `coworker_enabled: false`. Vercel production `dpl_owoavYPdcgprbs7hPD1N3cV7hYFw` is READY on that SHA. Render production `dep-dbljsivavr4c73cvs61g` is live on that SHA. This is an entry/rollout condition, not evidence of an old revision or wrong app root.

`getWorkspaceAppRoute` previously mapped every disabled `/coworker` link to home. RukhHome also removed the Coworker link and rendered a disabled button. The authenticated composer exists but is never mounted in this condition.

## Implemented behavior

- Disabled `/coworker` deep links now open an explicitly draft-only workspace with responsive neutral/green design, labelled editable composer, English brief starters, Bangla-capable input, theme control, clipboard copy and recovery feedback.
- Starters appear only while the draft is empty, preventing accidental replacement.
- This surface creates no auth/API client, sends no request, performs no execution and retains no draft after unmount/reload. Its status and helper text disclose these limits. It is not an AI chat implementation or simulated conversation.
- The home navigation now links to the draft workspace rather than presenting a dead button.
- Enabled routes still enter the existing authenticated Coworker application. Disabled OAuth callbacks still return home; preview never consumes callback tokens.
- Backend flags, environment configuration, accounts, providers and deployment state are untouched.

## Requirement matrix

| Requirement | Current evidence | Status / remaining action |
|---|---|---|
| Correct application/revision | Live HTML, rollout manifest, Vercel and Render deployed commit agree | Verified on base revision |
| Missing Coworker entry | Browser reproduces landing page at /coworker; route regression fails before repair | Implemented and unit tested; new live route unverified |
| Professional draft surface | Connected lazy route, shared tokens, responsive composer and meaningful copy action | Implemented; browser visual verification pending |
| Authenticated chat | Existing CoworkerGate and ConversationWorkspace; release flag false | Live blocked by rollout/configuration; no real authenticated session verified |
| Real streaming/persistence | Existing client and reply endpoint source, PR #630 | Source present; real provider, database and cross-account journey unverified |
| Task/files/approvals | Existing workspace surfaces and backend contracts | Preserved; operated qualification unverified |
| Separate Web Editor | Existing /editor route and standalone app | Build checked; real document-save/handoff unverified |
| Required viewport screenshots | CSS covers desktop/mobile; local browser installation failed | Pending actual browser qualification at 1366×768, 1440×900, 375×812, 390×844 and tablet |
| Deployment | Base frontend/backend revision verified read-only | This patch is not deployed or live verified |
| Full master prompt | Requirements exceed this bounded entry task | Incomplete; this document is not a release certificate |

## Verification

- The changed route regression failed against unchanged implementation before the repair.
- Web Editor suite: 204 passed, zero skipped, including route, landing page and new draft tests. New test exercises starters, Bangla editing, successful/failed copy and remount clearing; backend fetch is prohibited in the test.
- Web Editor, standalone Coworker and standalone Editor TypeScript/Vite builds pass. Existing Coworker >500 kB chunk warning remains.
- Read-only independent code review: no Critical/Important finding; Minor starter-overwrite finding fixed by hiding starters when draft is nonempty.
- Local Chromium installation failed with truncated ZIP downloads. No new-layout browser screenshots, mobile keyboard or clipboard device evidence is claimed.
- No backend implementation changed; backend suites were not rerun for this UI-only repair.

## Release and next dependency

1. Review the branch/PR and exact-head CI. This source repair can be reviewed independently of service activation.
2. Deploy through the existing authorized process; verify actual deployed revision and draft route. Rollback is the previous frontend deployment; no schema rollback is needed.
3. To provide real replies, complete the existing auth/environment/migration and operated qualification in CHATBOX_COMPLETION_2026-11-04.md. Verify normal Coworker auth, conversation and reply flags, schema 0063+, backend-only provider configuration and budgets on a matching staging revision.
4. Perform a real authorized-account journey: sign in, send a message, observe response, reload history, verify account isolation, inspect task state and complete document handoff. Do not infer these passes from the source tests.
5. Only then activate the approved cohort through the existing release procedure. This patch does not grant that activation.
