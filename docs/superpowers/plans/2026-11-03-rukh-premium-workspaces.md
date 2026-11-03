# Rukh AI Premium Workspace Implementation Plan

**Goal:** Complete a polished, Coworker-first experience with a distinct Web Editor, then qualify it on an isolated Vercel preview using staging authentication.

**Branch:** `feat/rukh-premium-workspaces-20261103`  
**Base:** `main` after merged PR #613  
**Spec:** `docs/superpowers/specs/2026-11-03-rukh-premium-workspaces-design.md`

## Constraints

- Keep Coworker default only behind `VITE_COWORKER_ENABLED=true`; never bypass the release gate in code.
- Use preview-only Vercel variables scoped to this branch and the existing `shuddho-staging` Supabase project.
- Do not change production environment variables, auth settings, database, domains or aliases.
- Preserve the shared auth client and explicit Agent execution/approval boundaries.
- Keep Coworker and Web Editor independently addressable at `/` and `/editor`; retain `/workspaces`.
- Do not add new dependencies or invent unsupported capabilities.

## Task 1 — Specify the experience with failing tests

- [x] Add a server-rendered Coworker navigation and sign-in-story contract test.
- [x] Add an Editor workspace-layout test with Coworker enabled in that test fixture.
- [x] Configure the test runner so only the Editor layout test uses the enabled feature flag.
- [ ] Run the tests and record the expected RED state before implementation.

## Task 2 — Refine the Coworker entry and navigation

- [ ] Replace the narrow report/email sign-in story with accurate persistent-work positioning.
- [ ] Label the Coworker workspace clearly and preserve Web Editor / Workspaces navigation.
- [ ] Keep the signed-in default view as persistent conversations.
- [ ] Preserve explicit message save, Agent dispatch, cancellation and external-action approval.

## Task 3 — Refine Web Editor into a clear three-region workspace

- [ ] Put Recent files on the left, writing canvas in the center and the existing AI review panel on the right.
- [ ] Keep the Editor independent at `/editor` and keep Coworker handoff on the same origin.
- [ ] Preserve draft replacement confirmation, artifact integrity checks and unsaved text.
- [ ] Verify responsive behavior without horizontal overflow.

## Task 4 — Premium shared visual pass

- [ ] Align Coworker navigation, conversation, contextual panels, auth screen and forms to shared design tokens.
- [ ] Improve spacing, typography, hierarchy, focus states, empty/loading/error states and mobile layouts.
- [ ] Keep original Rukh branding; do not copy Muse or another AI product.

## Task 5 — Preview qualification

- [ ] Run the complete web-editor test suite and both app builds.
- [ ] Run the repository CI checks and distinguish existing backend failures from frontend regressions.
- [ ] Confirm preview build is READY on this branch and uses staging-only Supabase configuration.
- [ ] Verify root route, login/session restoration, default conversations, Web Editor, workspace switcher, reset/recovery callback and mobile layout.
- [ ] Verify `rukhai.vercel.app` remains the current branded alias; do not change production aliasing.
- [ ] Report what was verified, what remains blocked, and request approval before production environment changes or promotion.
