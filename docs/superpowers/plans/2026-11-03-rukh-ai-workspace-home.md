# Rukh AI workspace home implementation plan

> **Status:** Historical implementation plan for the workspace-directory surface now served at `/workspaces`. The root route is governed by the approved [Coworker-first default-entry plan](2026-11-03-rukh-coworker-default-entry.md); do not restore the chooser as the enabled Coworker root.


> **For agentic workers:** Use the repository's existing React/Vite workspaces. Execute each task with a test-first loop and verify the exact branch head before reporting status.

**Goal:** Replace the current default editor landing route with a polished Rukh AI workspace home that presents Co-workers and Web Editor, while preserving the Coworker release gate.

**Architecture:** Keep the existing monorepo and standalone app routes. Add a small, presentational home component; route the root path to it; keep Coworker behind `VITE_COWORKER_ENABLED`; remove disabled Coworker integration from the Editor render tree.

**Tech Stack:** React 18, TypeScript, Vite, existing CSS design tokens, Node built-in test runner, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-03-rukh-ai-workspace-home-design.md`

## Global constraints

- Keep `VITE_COWORKER_ENABLED=false` as the default.
- Do not change backend, database, auth, transaction, provider or approval boundaries.
- Add no new dependencies or UI libraries.
- Reuse `packages/design-system/src/tokens.css`.
- Preserve Web Editor functionality and owner-bound artifact handling.
- Do not deploy or merge before exact-head CI and release checks.

## Task 1 — Route and gate regression tests

- Update `apps/web-editor/test/app-routes.test.mjs` so `/` and disabled `/coworker` resolve to `home`, while `/editor` remains available and enabled `/coworker` remains accessible.
- Retain the existing `editor-feature-gate.test.tsx` assertions that disabled Coworker controls and recent files are absent.
- Verification: run `npm run test --workspace @shuddho/web-editor` and confirm the route assertions fail before the route implementation changes.

## Task 2 — Rukh AI home surface

- Add `apps/web-editor/src/RukhHome.tsx` and `apps/web-editor/src/rukh-home.css`.
- Present the two products with asymmetric layouts and distinct interface previews; keep Co-workers visibly marked Private preview when disabled.
- Use semantic navigation, inline SVG icons, visible focus, reduced-motion support and mobile stacking.
- Verification: add a server-rendered test for both Coworker flag states and run the web-editor test suite.

## Task 3 — Route integration

- Update `apps/web-editor/src/appRoutes.mjs`, `appRoutes.d.mts` and `WorkspaceShell.tsx`.
- Root and unknown paths render the home. Direct Coworker routes return home when the feature is disabled; Editor routes remain stable.
- Verification: route tests and TypeScript build.

## Task 4 — Enforce the Editor feature gate in rendered UI

- In `apps/editor/src/App.tsx`, derive the feature flag once, avoid creating the Coworker auth/client integration while disabled, guard the handoff handler and conditionally render Coworker actions and the recent-files panel.
- Make the Editor brand return to the home and keep the standalone editor layout full width when the panel is absent.
- Verification: the existing `editor-feature-gate.test.tsx` must pass; test the enabled and disabled branches where the harness supports them.

## Task 5 — Consistent standalone navigation and identity

- Update `apps/coworker/src/App.tsx` and its styles to link back to the home and to Web Editor.
- Use same-origin `/coworker` and `/editor` routes in the integrated workspace; retain `VITE_COWORKER_APP_URL` and `VITE_EDITOR_APP_URL` overrides for separately hosted deployments.
- Open cross-workspace links from an active editor/task in a new tab so unsaved work is not discarded.
- Update standalone HTML titles/descriptions and the web-editor font link to use the established DM Sans / Manrope / Noto Serif Bengali families, removing the stale Inter mismatch.
- Update the Playwright browser flow to verify the two home destinations, desktop/mobile horizontal overflow, and new-tab navigation between standalone workspaces.
- Verification: standalone shell tests and workspace builds.

## Task 6 — Exact-head verification

- Run all required JS tests and `npm run build` through GitHub Actions on this branch.
- Inspect the resulting diff and CI logs.
- Record visual/browser evidence if available. Vercel and ProductOS connector access is currently unavailable; do not claim a deployed or browser-qualified result without evidence.
- Keep the PR open for review; do not merge or alter production flags.
