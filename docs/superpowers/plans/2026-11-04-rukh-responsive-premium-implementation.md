# Rukh AI Responsive Premium Frontend — Implementation Plan

**Branch:** `feat/rukh-responsive-premium-ui-20261104`  
**Base:** `main` at `d9b83c70b0b4a4cc2cf4bd641a2811fd44591262`  
**Spec:** `docs/superpowers/specs/2026-11-04-rukh-responsive-premium-design.md`  
**Execution mode:** bounded frontend-only implementation; no production promotion.

## Constraints

- Follow root `AGENTS.md` and the existing Coworker-first product contract.
- Preserve route gating, shared Supabase auth/session behavior, idempotent conversation writes, explicit Agent dispatch/cancellation and external-action approvals.
- Do not alter backend, database, schema/RLS, providers, feature flags, production environment variables, aliases or auth configuration.
- Use no new runtime dependencies.
- ProductOS currently exposes a different project; do not attach or modify that project for this Rukh task.
- Use a feature branch and reviewable PR; do not merge or promote to production in this task.

## Task 1 — Regression contracts (test first)

- [x] Add tests for the shared theme control and local preference behavior.
- [x] Add server-rendered contracts for Coworker mobile panel controls and Editor recent-file control.
- [x] Add CSS contract checks for the 720px mobile-canvas regression, sheet breakpoints and touch target sizing.
- [ ] Capture a separate red-before-implementation CI run; tests were authored first, but that failure was not observed before implementation.

## Task 2 — Shared visual foundation

- [x] Update design tokens to the researched warm-neutral/deep-green palette and strengthen dark tokens.
- [x] Add a shared theme utility and accessible theme toggle.
- [x] Initialize the theme before mounting each app; persist preference locally.
- [x] Update browser theme-color and SVG favicon to the new Rukh accent.
- [x] Replace legacy hard-coded violet accent usage in the Coworker shell with semantic tokens.

## Task 3 — Coworker mobile experience

- [x] Add a mobile toolbar for Conversations and Context.
- [x] Turn the existing conversation list and Context inspector into mobile sheets without duplicating data/state.
- [x] Add Escape/backdrop/close handling, focus return and labelled dialog semantics.
- [x] Convert the outer workspace navigation to a horizontally scrollable, touch-friendly mobile rail.
- [x] Keep desktop three-region behavior and the conversation composer intact.

## Task 4 — Editor mobile experience

- [x] Add a Recent files control and accessible drawer.
- [x] Keep the editor canvas at the available viewport height rather than a fixed 720px.
- [x] Restore the existing AI review toggle and use the existing review panel as a mobile bottom sheet.
- [x] Preserve artifact digest verification, unsaved-text replacement confirmation and Coworker handoff (logic unchanged; still requires live regression verification).

## Task 5 — Theme/accessibility polish

- [x] Add dark-surface overrides for Coworker, Editor, inputs, review cards and sheets.
- [x] Ensure focus indicators, reduced motion, 44px touch controls and safe-area/viewport behavior.
- [x] Keep Bangla input/output and direction-aware text rendering unchanged (no localization or direction logic changed).

## Task 6 — Verification and handoff

- [ ] Confirm the final-head frontend test run after the latest test-only assertion commit.
- [ ] Confirm exact-head Coworker and Editor checks/builds from CI.
- [x] Frontend production builds passed in CI at commit 654c41a; rerun on latest head is pending.
- [x] Inspect exact-head GitHub Actions. Frontend tests/builds passed at 654c41a; a prior run exposed browser-only matchMedia assumptions, now guarded. Python test-and-build failed as it did on base d9b83c7; latest run remains pending.
- [ ] Inspect the latest Vercel preview. Current preview creation is blocked by the free per-day deployment quota (api-deployments-free-per-day); do not bypass protection or quota.
- [ ] Verify 1440×900, 1366×768, 390×844 and 375×812 in a live browser; browser preview is currently unavailable. Unit/SSR/CSS contracts are committed.
- [x] Open PR #615 with evidence, blockers and explicit non-production status; it is open and unmerged.

## Known baseline

At base commit `d9b83c7`, the dedicated **Frontend tests and builds** job passed, while `test-and-build`, `coworker`, `governance-audit` and `ci-merge-gate` were failing. Do not attribute those inherited failures to this frontend patch without checking exact-head logs.

## Handoff status

- Implementation: complete for the scoped frontend changes.
- Repository verification: partial. The dedicated Frontend tests and builds job passed at 654c41a; latest-head CI is pending. The Python test-and-build job is failing on base and feature branch; no Python files were changed here.
- Preview verification: blocked by the Vercel free per-day deployment quota. No current-head live-browser screenshot or production verification is claimed.
- Production qualification/activation: not in scope; PR #615 remains open and unmerged.
- Latest test-only follow-up commit: 4af690f; it adds an assertion that the main app bundle loads the Editor stylesheet.
