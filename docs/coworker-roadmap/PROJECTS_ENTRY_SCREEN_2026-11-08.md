# Projects dashboard entry — 9 November 2026

## Acceptance reference

- User-provided screenshot in the 9 November 2026 conversation.
- Figma file: https://www.figma.com/design/eIeIHgClMJia6kRi484Xsl/Rukh-AI-%E2%80%94-Coworker---Web-Editor-%C2%B7-Laptop---Mobile?node-id=4-226
- Repository export: `docs/frontend/design-reference/design.json`, screen `projects-desktop` (1440×900), plus `design-tokens.json`.
- Figma MCP context was unavailable because the connected Figma service returned its Starter-plan request limit; the implementation uses the user screenshot and committed exports rather than claiming a live Figma inspection.

## Required behavior

1. Selecting Projects or opening `/coworker?view=projects` shows the Projects dashboard, not the creation form.
2. Keep the shared Rukh sidebar visible with Projects selected, the Projects top-bar title, and Activity & context control.
3. Show the Projects page heading, helper text, `+ New project` action, search field, and project cards generated from real owner-scoped API records.
4. Selecting `+ New project` opens the existing Create a project form.
5. Cancel returns to the Projects dashboard without creating a record.
6. Creating a project persists its name and optional instructions, then opens the saved project detail.
7. Selecting a project card opens the project workspace with Overview, Chats, and Files tabs.
8. Search filters actual project names and descriptions.
9. Navigation, direct URL load, refresh, and browser back/forward keep the Projects destination stable.
10. Desktop and mobile layouts do not create horizontal overflow.

The three project names shown in the screenshot are reference content, not seed data. Do not hard-code or fabricate project cards; render the authenticated user's actual project records.

## Root cause

PR #649 introduced `projectCreateMode=true` for Projects navigation and passed `initialCreate` to `ProjectWorkspace`. That made `?view=projects` render the creation form immediately, contrary to both the supplied screenshot and the exported `projects-desktop` frame. PR #653 restores the dashboard as the route's default and makes creation an explicit button action.

## Implementation

- Branch: `fix/projects-dashboard-entry-20261109`.
- PR: https://github.com/rumman52/Shuddho/pull/653
- Dashboard and detail UI continue to use the existing `ProjectWorkspace`, `CoworkerClient`, and owner-scoped project endpoints.
- Removed `initialCreate` from the component contract so a Projects route cannot implicitly open the create form.
- Retained the existing `projectEntryRevision` remount so re-entering Projects from a project detail returns to the dashboard.
- No CSS redesign was required: the committed project layout already matches the exported frame's 248px sidebar, 52px content inset, 3-column card grid, 132px card height, Rukh colors, and spacing.

## Verification evidence

- Red: test-only commit `5c977eb` failed the Coworker Projects entry test because the rendered heading was `New project`, not `Projects`.
- Green: implementation commit `7b2b932` fixed the route state.
- GitHub Frontend tests and builds job: passed. Web-editor suite: 238 passed, 0 failed. Standalone Coworker and Writing Assistant tests/builds: passed.
- Root test-and-build job: passed.
- The broader Coworker CI job must be read from the exact current PR head before marking all CI complete.
- Vercel GitHub integration reported the preview deployment Ready: https://shuddho-web-editor-git-fix-projects-d-6b25b2-rumman52s-projects.vercel.app
- The preview could not be independently opened through the current browser/Vercel API connection, so no claim of visual browser inspection is made.

## Backend and release boundary

The Projects API remains separately gated by the authorized migration `0064` and `SHUDDHO_PROJECTS_ENABLED=true`, as documented in `docs/frontend/FIGMA_IMPLEMENTATION_2026-11-05.md`. This UI PR does not run that migration, enable the flag, change live project records, alter authentication, or promote production. If the backend gate is off, the UI must show the existing explicit unavailable/error state rather than inventing projects.

## Out of scope

- Hard-coded sample projects or demo data.
- Backend migration or production flag activation.
- Changes to Coworker, Fly, Writing Assistant, Plugins, or unrelated workspace routes.
- Production promotion or claims of production qualification.
