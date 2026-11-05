# Rukh approved frontend implementation — 5 November 2026

This change implements the approved Coworker-first design in the existing React/Vite application. It is not a production activation certificate.

## Starting point and confirmed causes

- Repository `rumman52/Shuddho`, base main `065dedfe73a95ddd36d331336e11297d75aa25db`; frontend/build root `apps/web-editor`, npm workspaces. The unrelated runtime lexicon file was preserved.
- The old public address `https://shuddho-web-editor.vercel.app/` redirects to `https://rukhai.vercel.app/`. Browser inspection found the workspace chooser at `/` and a different, centered signed-out composer at `/coworker` without the approved sidebar.
- `getWorkspaceAppRoute()` selects the directory at `/` unless `VITE_COWORKER_ENABLED=true`. Explicit `/coworker` reaches the real authentication application. This UI rollout setting is preserved.
- The public Coworker page reported **Account access is not configured for this deployment**. Public Supabase URL/publishable-key validation therefore prevents sign-in. CSS does not repair that configuration.
- PR #634 implemented only part of the authenticated shell. Its signed-out entry and writing-only Editor did not implement the approved home and website canvas. Earlier source also tied the composer to successful profile metadata; that previous fix remains, and the failure path is exercised again here.
- The connected Vercel API returned 404 for the previous project/deployment and did not list Rukh among accessible projects. GitHub's existing deployment integration is used for branch preview; no substitute hosting project is created.

## Design source

Figma file: https://www.figma.com/design/eIeIHgClMJia6kRi484Xsl

Desktop home `3:181`; mobile home `4:1703`. Figma context and screenshot calls both returned the Starter-plan MCP limit. Implementation therefore uses the supplied `design.json`, `design-tokens.json`, and exported screens. Relevant unmodified exports are retained in [design-reference](design-reference). Inter and Bengali fonts are bundled locally. The exported companion-mark geometry is reused.

## Implemented behavior

| Area | Source and local verification | Live qualification |
|---|---|---|
| Coworker | Approved palette, 248px desktop rail, welcome/three starter cards, mobile two-card layout, visible bottom composer, slide-out navigation, context drawer, accessible account dialog | New preview only; public auth remains a blocker |
| Chat | Existing owner-authenticated API, streamed replies, error/retry/recovery, explicit stop receiving, preserved saved history. The backend may finish a durable reply after stream stop; the UI says so | Real provider reply not certified |
| New chat/history | History search/rename/export/delete retained. New chat from both conversation and section navigation explicitly starts empty. Draft retained through sign-in | Local browser/API fixture |
| Projects | Real project/create/edit/list/detail/link/unlink/delete APIs; links reference existing conversations/documents. Owned IDs, request replay, bounded counts, revision conflicts, erasure cleanup. Project chats and editor saves retain project IDs | Requires migration 0064 and an authorized backend rollout with `SHUDDHO_PROJECTS_ENABLED=true`; defaults off |
| Plugins | Searchable supported-tool catalog; connected/disconnected/unavailable status; actual connection, permission and approval UI. Catalog updates after connection changes | Existing provider/feature configuration remains authoritative |
| Files/Settings | Real source upload/list/delete/search and account writing preferences; theme preference retained | Local API fixture; live auth/config needed |
| Website Editor | Layers, Design/Code/History, sandboxed HTML preview, editable background/spacing, original writing mode retained, explicit verified source-file saves, project links, review handoff and return | Saves website source as `website-source.html.txt`, not a published website |
| Editor safety | Scripts/external navigation removed from preview; opaque sandbox and restrictive CSP; user-keyed editor plus generation guards; saved history/status revalidated by file ID and digest; transient verification failure preserves metadata | Source/unit/browser verified |
| Goals/Automations/approvals | Existing real backend workflows remain accessible inside the shared visual shell; capability-disabled/loading/error states remain honest | Operation still subject to their existing release and infrastructure gates |

The implementation does not claim every one of the 46 illustrative frames or every provider is fully operational. The account dialog retains supported email authentication; the design's illustrative Google account-login button is not fabricated. Unsent public drafts remain in memory; website/writing drafts use user-scoped tab storage. A website preview is not publication.

## Verification

- Root npm workspace tests, including the web-editor suite, standalone Coworker/Editor, shared/gateway/NLP tests.
- TypeScript `--noEmit` and production builds for web-editor, Coworker, and Editor. Bundle-size warnings remain visible; thresholds were not relaxed.
- Combined backend suite: **108 passed, zero skips** across projects, conversations, replies, context, dispatch, and backend-only frontend contracts. Includes additive upgrade from 0063 preserving an existing conversation and account erasure of project records.
- Chromium browser acceptance at **1440×900, 1366×768, 390×844, 375×812** and a shorter keyboard-emulation viewport. This is viewport emulation, not testing on physical phones.
- Browser journey: entry → sign-in/draft preservation → real local API → streamed synthetic model response → reload → project create/link/new chat → website source edit/save/reload → sandbox navigation/script checks → return to Coworker → profile-error composer check.
- The local acceptance fixture uses a real API, JWT verification, SQLite and private local file storage, with explicitly synthetic identity/model responses. It neither proves a live AI provider nor replaces production services.
- Four editor regression tests cover late account-switched saves, missing backing files, transient verification recovery, and restoration racing with a newer save.
- Independent review's security/persistence findings were corrected and reproduced again. No production credentials, paid resources, production flags, or live database changes were made.

The first extended backend attempt encountered a missing SQLite table in a temporary fixture; a focused rerun and the combined 108-test run with a unique explicit temporary directory passed. No application migration was disabled to obtain these results.

### Reproduce local acceptance

```bash
npm ci
uv sync --extra coworker
npm test
npm run build --workspace @shuddho/web-editor
npm run build --workspace @rukh/coworker
npm run build --workspace @rukh/editor
# Install Chromium through Playwright, or set SHUDDHO_TEST_BROWSER to an installed Chromium.
python apps/web-editor/test/run-design-browser.py
```

The supervisor starts the guarded test-only API and Vite in the same network namespace and stops them after testing. It generates isolated disposable test data. Browser measurements and screenshots are under `visual-evidence` when `SHUDDHO_DESIGN_EVIDENCE=docs/frontend/visual-evidence` is set.

## Release and remaining blockers

1. Review the implementation PR and its exact commit checks. Preview deployment and production must be reported separately.
2. Restore access to the existing Rukh Vercel project. Confirm its current name, public alias, source branch, build root, deployed SHA, Supabase public config, and API origin. Do not copy private credentials into frontend variables.
3. Qualify a matching backend with durable application storage, private file storage, the configured provider, and the existing capability/cohort gates. Migration 0064 is additive but is not run against a live database by this work.
4. After an authorized rollout, validate real account login, provider SSE response, refresh/reopen, project/file isolation, editor save and mobile behavior on the actual preview.
5. Only then perform an authorized merge/promotion and verify the production alias/revision and normal root/login journey. Until that happens, production is **not verified**.
