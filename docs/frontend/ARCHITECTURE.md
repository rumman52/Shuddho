# Rukh AI frontend architecture

**Status:** implementation baseline derived from the user-approved frontend brief, 2 November 2026.

## Product surfaces

Rukh AI has two independently buildable browser applications:

- **Rukh AI Coworker** — conversation-led work, Agent runs, goals, automations, browser sessions, files, approvals and connected tools.
- **Rukh Editor** — multilingual writing, correction, Deep AI Review, suggestions and text/Markdown editing.

The existing `apps/web-editor` React/Vite code is the current source of truth for writing and coworker API behavior. The `apps/web` Next.js app is a separate legacy/preview implementation; it is not silently substituted for the production-capable editor. Existing applications remain available during migration.

## Architecture decisions

1. Add `apps/coworker` and `apps/editor` as independent Vite builds. Keep existing application entry points intact for rollback.
2. Share a small design-system package, a Supabase browser-auth package and a typed coworker-client facade. Existing API types and safety checks remain canonical; do not duplicate endpoint contracts.
3. Use the same Supabase project and default browser storage key on the same origin. The intended production routes are `/coworker` and `/editor`; deployment routing must be configured and verified before claiming cross-app session sharing.
4. Preserve the backend's explicit authorization boundaries. Saving a conversation message does not dispatch an Agent run. External actions still require their existing approval path.
5. Conversation records currently contain user-authored messages and separate Agent activity/run records. The UI must not fabricate assistant replies. Show run status, phase, plan and results from the real Agent API.
6. Editor-to-Coworker handoff uploads the draft as an owner-scoped source document, resolves the exact available document version from the workspace manifest, creates a conversation, and attaches that version. It does not automatically start Agent work. Access tokens never appear in URLs.
7. Coworker-to-Editor opening is supported for plain-text and Markdown artifacts only. Other formats remain downloadable; PDF/DOCX parsing is not claimed unless a verified parser is added.
8. No backend schema, production feature flag, provider authority, billing, deployment, or secrets are changed by this frontend work.

## Shared package boundaries

- `@rukh/design-system`: design tokens, mark, icons, buttons and status badges.
- `@rukh/auth`: validated public Supabase configuration and a browser client using the existing default session storage behavior.
- `@rukh/coworker-client`: typed facade over the existing owner-authenticated coworker API client.

## Explicitly unsupported or deferred

- Project-management objects and document folders/rename are not exposed by the inspected backend contract; do not add fake navigation or controls.
- Conversation assistant messages are not exposed by the current conversation API; Agent execution is a separate explicit operation.
- PDF and DOCX in-browser editing is not implemented by this slice; users can download those artifacts.
- Same-origin Vercel path routing, domain assignment, environment variables and live deployment require a separate verified deployment operation.
