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

- [ ] Add tests for the shared theme control and local preference behavior.
- [ ] Add server-rendered contracts for Coworker mobile panel controls and Editor recent-file control.
- [ ] Add CSS contract checks for the 720px mobile-canvas regression, sheet breakpoints and touch target sizing.
- [ ] Confirm the new tests fail before implementation where the expected controls/behavior are absent.

## Task 2 — Shared visual foundation

- [ ] Update design tokens to the researched warm-neutral/deep-green palette and strengthen dark tokens.
- [ ] Add a shared theme utility and accessible theme toggle.
- [ ] Initialize the theme before mounting each app; persist preference locally.
- [ ] Update browser theme-color and SVG favicon to the new Rukh accent.
- [ ] Replace legacy hard-coded violet accent usage in the Coworker shell with semantic tokens.

## Task 3 — Coworker mobile experience

- [ ] Add a mobile toolbar for Conversations and Context.
- [ ] Turn the existing conversation list and Context inspector into mobile sheets without duplicating data/state.
- [ ] Add Escape/backdrop/close handling, focus return and labelled dialog semantics.
- [ ] Convert the outer workspace navigation to a horizontally scrollable, touch-friendly mobile rail.
- [ ] Keep desktop three-region behavior and the conversation composer intact.

## Task 4 — Editor mobile experience

- [ ] Add a Recent files control and accessible drawer.
- [ ] Keep the editor canvas at the available viewport height rather than a fixed 720px.
- [ ] Restore the existing AI review toggle and use the existing review panel as a mobile bottom sheet.
- [ ] Preserve artifact digest verification, unsaved-text replacement confirmation and Coworker handoff.

## Task 5 — Theme/accessibility polish

- [ ] Add dark-surface overrides for Coworker, Editor, inputs, review cards and sheets.
- [ ] Ensure focus indicators, reduced motion, 44px touch controls and safe-area/viewport behavior.
- [ ] Keep Bangla input/output and direction-aware text rendering unchanged.

## Task 6 — Verification and handoff

- [ ] Run `npm run test --workspace @shuddho/web-editor`.
- [ ] Run `npm run test --workspace @rukh/coworker` and `npm run test --workspace @rukh/editor`.
- [ ] Run the three corresponding production builds.
- [ ] Inspect the exact PR-head GitHub Actions checks; distinguish frontend regressions from failures already present on base `d9b83c7`.
- [ ] Inspect the Vercel preview for this branch. Use protected-deployment access without disabling SSO or changing protection.
- [ ] Verify 1440×900, 1366×768, 390×844 and 375×812, plus keyboard/Escape and theme persistence where browser access permits.
- [ ] Open a draft PR with evidence, blockers and explicit non-production status.

## Known baseline

At base commit `d9b83c7`, the dedicated **Frontend tests and builds** job passed, while `test-and-build`, `coworker`, `governance-audit` and `ci-merge-gate` were failing. Do not attribute those inherited failures to this frontend patch without checking exact-head logs.

## Handoff status

- Implementation: pending.
- Repository verification: pending.
- Preview verification: pending.
- Production qualification/activation: not in scope.
