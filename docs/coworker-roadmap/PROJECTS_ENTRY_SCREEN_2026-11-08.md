# Projects entry screen — 8 November 2026

- **Objective:** Selecting Projects opens the supplied New project screen directly: the shared workspace sidebar remains visible, the header reads “New project”, and the centered “Create a project” form contains the project name, optional instructions, Cancel and Create project controls.
- **Base:** `main` `0b4263f04bbdf309adc6cba0d439243a6aaed3bc`.
- **Branch:** `fix/rukh-projects-default-create-screen-20261108`.
- **Root cause:** `CoworkerWorkspace` correctly selected the Projects view, but `ProjectWorkspace` initialized with `editing=false`; the first visible screen was the project listing rather than the supplied creation state.
- **Existing interfaces reused:** `ProjectWorkspace`, `CoworkerClient.createProject`, the existing owner-scoped Projects API, and the approved Rukh theme/CSS.
- **Files changed:** `CoworkerWorkspace.tsx`, `ProjectWorkspace.tsx`, `ProjectWorkspace.test.tsx`, and `test/coworker-browser.mjs`.
- **Behavior:** Projects navigation (including direct URL load, reload, repeated selection, and browser back/forward) enters a fresh creation form. Cancel returns to the existing project list; successful creation continues to the saved project detail. The project-list request is deferred while the create form is open.
- **Compatibility:** No database migration, API schema, project record, conversation, file, authorization, provider, or production flag changes.
- **Acceptance:** Confirm the screenshot-matched form is the first Projects screen; verify project creation still persists name/instructions and opens the saved project; verify Cancel reveals the existing project list; verify the full browser route and reload path; run web-editor tests and build.
- **Out of scope:** Changing the other workspace destinations, reintroducing removed Web Editor UI, changing Fly/Writing Assistant, or promoting any production capability.

## Completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Pending exact-head CI | Dedicated branch contains the route-entry fix and regressions. |
| Repository-verified | Pending | Run exact-head frontend unit/build and Coworker browser CI. |
| Staging-verified | Not performed | No matching live staging identity was used. |
| Production-qualified | No | This UI patch does not qualify the wider Rukh release. |
| Activated | No change | No production flag or capability was changed. |

- **Next action:** inspect exact-head CI, review the final diff, then use the existing Vercel project only when its deployment quota/access permits. Do not claim production deployment from a branch preview.
