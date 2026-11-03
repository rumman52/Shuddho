# Rukh AI Coworker-First Workspace Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AI Coworkers the default Rukh AI entry point when its existing release flag is enabled, while keeping Web Editor separate and preserving the workspace directory at `/workspaces`.

**Architecture:** Keep route resolution in the existing pure `appRoutes.mjs` helper. `WorkspaceShell` continues to lazy-load the existing Coworker and Editor apps. The Coworker feature gate remains authoritative; the existing writing editor remains unchanged except for navigation links.

**Tech Stack:** React 18, TypeScript, Vite, Node test runner, existing GitHub Actions and Vercel preview pipeline.

**Spec:** `docs/superpowers/specs/2026-11-03-rukh-coworker-default-entry-design.md`

## Global Constraints

- `VITE_COWORKER_ENABLED === "true"` is the only condition that enables Coworker routing.
- A missing or false Coworker flag must fail closed and must not expose Coworker through root or direct routes.
- `/` is the Coworker-first entry point only when the flag is enabled.
- `/workspaces` is the explicit workspace directory; `/editor` remains independent.
- Do not change Agent execution semantics, authentication, backend APIs, Supabase policies, or document content behavior.
- Do not add dependencies or deploy/promote to production in this implementation.

## Review Focus

- Missing or false `VITE_COWORKER_ENABLED`: root and direct Coworker paths must remain gated.
- Root path with trailing slash, query string, or hash: still resolves to the default entry point.
- `/workspaces` with trailing slash or query: still resolves to the directory.
- Unknown paths: must not accidentally enter Coworker.
- Workspace navigation from the Editor: must preserve the existing Editor tab/document by opening the directory separately, rather than silently discarding in-memory text.

---

### Task 1: Make the root route Coworker-first without bypassing the release gate

**Files:**
- Modify: `apps/web-editor/test/app-routes.test.mjs`
- Modify: `apps/web-editor/src/appRoutes.mjs`

**Interfaces:**
- Consumes: `getStandaloneAppRoute(pathname)` and `getWorkspaceAppRoute(pathname, coworkerEnabled)`.
- Produces: route helper returns `"coworker"` for `/` only when enabled, `"home"` for `/workspaces`, and preserves fail-closed behavior for direct Coworker routes.

- [x] **Step 1: Write the failing route tests**
  - Assert `getStandaloneAppRoute("/workspaces")` and `getStandaloneAppRoute("/workspaces/?from=editor")` return `"home"`.
  - Assert `getWorkspaceAppRoute("/", true)` and `getWorkspaceAppRoute("/?from=bookmark", true)` return `"coworker"`.
  - Assert `getWorkspaceAppRoute("/", false)`, `getWorkspaceAppRoute("/coworker", false)`, and `getWorkspaceAppRoute("/coworker?conversation=abc", false)` return `"home"`.
  - Assert `getWorkspaceAppRoute("/workspaces", true)`, `getWorkspaceAppRoute("/editor", true)`, and `getWorkspaceAppRoute("/unknown", true)` retain their separate route behavior.

- [x] **Step 2: Run the focused route test and confirm RED**
  - Run: `node --test apps/web-editor/test/app-routes.test.mjs`
  - Expected: FAIL because root currently resolves to `"home"` even when Coworker is enabled and `/workspaces` is not classified as the workspace directory.

- [x] **Step 3: Implement the minimal route helper change**
  - In `getStandaloneAppRoute`, classify `/workspaces` and its nested paths as `"home"`.
  - In `getWorkspaceAppRoute`, classify the normalized root path as `"coworker"` only when `coworkerEnabled` is true; retain the current gated fallback for `/coworker`.
  - Keep unknown paths mapped to the workspace directory.

- [x] **Step 4: Re-run the focused route test and confirm GREEN**
  - Run: `node --test apps/web-editor/test/app-routes.test.mjs`
  - Expected: all route tests pass.

- [x] **Step 5: Commit**
  - Commit message: `feat(frontend): make coworker the gated default entry`.

### Task 2: Make workspace switching clear and preserve Editor drafts

**Files:**
- Modify: `apps/coworker/src/App.tsx`
- Modify: `apps/editor/src/App.tsx`
- Modify: `apps/web-editor/test/editor-feature-gate.test.tsx`
- Create: `apps/web-editor/test/coworker-app-navigation.test.tsx`
- Modify: `apps/web-editor/test/run-tests.mjs`

**Interfaces:**
- Coworker "All workspaces" points to `/workspaces`; Coworker "Web Editor" continues to point to `/editor`.
- Editor "All workspaces" points to `/workspaces`; Editor-to-Coworker handoff and direct Coworker link remain available only when the Coworker flag is enabled.
- Editor directory links open a separate tab so unsaved in-memory editor text is not discarded.

- [ ] **Step 1: Write failing server-rendered navigation tests**
  - Add a Coworker app test asserting its header links target `/workspaces` for "All workspaces" and `/editor` for "Web Editor".
  - Extend the Editor feature-gate test to assert the "All workspaces" link targets `/workspaces`, and keep Coworker-only controls absent when the flag is disabled.
  - Add the new test to `apps/web-editor/test/run-tests.mjs`.

- [ ] **Step 2: Run the focused tests and confirm RED**
  - Run: `npm run test --workspace @shuddho/web-editor`
  - Expected: fail because the current headers point "All workspaces" to `/`, which will become the Coworker-first entry point.

- [ ] **Step 3: Update only the navigation destinations**
  - Change the Coworker "All workspaces" link from `/` to `/workspaces`.
  - Change the Editor "All workspaces" link from `/` to `/workspaces`.
  - Keep the Editor directory link opening a new tab to protect the current in-memory draft.
  - Do not change Coworker auth, the Editor writing assistant, or the explicit draft handoff.

- [ ] **Step 4: Re-run the focused workspace tests and confirm GREEN**
  - Run: `npm run test --workspace @shuddho/web-editor`
  - Expected: all web-editor tests pass.

- [ ] **Step 5: Commit**
  - Commit message: `fix(frontend): keep workspace navigation distinct`.

### Task 3: Verify the integrated workspaces and prepare review

**Files:**
- Verify: `apps/web-editor/src/WorkspaceShell.tsx`
- Verify: `apps/web-editor/src/RukhHome.tsx`
- Verify: `apps/coworker/src/App.tsx`
- Verify: `apps/editor/src/App.tsx`
- Verify: `apps/web-editor/test/app-routes.test.mjs`
- Verify: `apps/web-editor/test/editor-feature-gate.test.tsx`
- Verify: `apps/web-editor/test/coworker-app-navigation.test.tsx`

- [ ] **Step 1: Run the complete web-editor test suite**
  - Run: `npm run test --workspace @shuddho/web-editor`
  - Expected: exit code 0.

- [ ] **Step 2: Run application builds**
  - Run: `npm run build --workspace @shuddho/web-editor`
  - Run: `npm run build --workspace @rukh/editor`
  - Expected: both exit with code 0.

- [ ] **Step 3: Verify the route matrix and header navigation**
  - Confirm root, direct Coworker, Editor, workspace directory, query-string and unknown-path behavior.
  - Confirm no Coworker flag bypass and no accidental changes to the Editor content surface.

- [ ] **Step 4: Create a draft pull request and inspect CI / preview results**
  - Required checks must be evaluated on the final PR head, not on an earlier commit.
  - A Vercel preview marked READY proves only deployment readiness; browser route and UI behavior must also be checked.
  - Do not merge or promote to production as part of this plan.

- [ ] **Step 5: Record verification and review findings**
  - Report exact commands, results, failures and any baseline failures separately.
  - Commit message for any final review fix must follow its own RED-to-GREEN test cycle.
