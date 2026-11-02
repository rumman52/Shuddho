# Rukh AI frontend implementation plan

> Execution mode: direct repository implementation on the isolated `feat/rukh-ai-frontend-rebuild` branch. The user explicitly directed completion of the supplied frontend brief; no additional design selection is being requested.

## Goal

Deliver two independent Rukh AI frontends while preserving the existing React/Vite editor and Coworker backend contracts.

## Tasks

### 1. Tests first
- Add navigation-route tests for the Coworker application.
- Add API-client tests for safe owner-authenticated reading of text/Markdown artifacts.
- Confirm the new tests fail before implementation.

### 2. Shared foundation
- Add `@rukh/auth`, `@rukh/design-system` and `@rukh/coworker-client`.
- Add independent Vite workspace packages for Coworker and Editor.
- Update npm workspace and lockfile metadata without introducing unnecessary runtime dependencies.

### 3. Coworker application
- Add a responsive three-zone shell: navigation/recent conversations, main conversation/work area and contextual panel.
- Reuse the existing authenticated Coworker gate and all existing workspaces.
- Add explicit initial-view support and route navigation for capabilities already exposed by the API.
- Improve the conversation timeline while preserving message save, explicit Agent dispatch, cancellation, memory review, source binding and delete/redact behavior.
- Show real Agent activity and workspace context; never invent assistant responses or counts.

### 4. Editor application and handoff
- Wrap the existing writing editor in an independent Rukh Editor application.
- Add a real recent-artifact list sourced from owner-authenticated task history.
- Open plain-text/Markdown artifacts through the authenticated artifact content route; download other formats.
- Add explicit Editor-to-Coworker handoff using the existing document upload, workspace manifest and conversation APIs. Do not auto-dispatch Agent work.
- Preserve existing Bangla, multilingual, correction, Deep AI Review, suggestion and export behavior.

### 5. Product integration and qualification
- Update user-facing branding to Rukh AI while retaining internal migration identifiers.
- Add feature-preservation, shared-component, deployment and QA documentation.
- Run `npm ci`, `npm test`, `npm run build` and inspect exact-head GitHub Actions.
- Fix every reproducible frontend regression. Do not merge or deploy without separate authorization and environment verification.

## Acceptance criteria

- `apps/coworker` and `apps/editor` each build independently.
- Both applications use the same validated public Supabase project/session behavior on a shared origin.
- Coworker navigation only exposes implemented capabilities.
- Conversation messages, Agent runs and external approvals remain separate operations.
- Handoff uses authenticated backend ownership and exact document version IDs.
- Existing writing features and coworker workspaces remain reachable.
- Mobile and desktop layouts have no horizontal overflow.
- CI evidence is tied to the final branch commit; a successful local or partial test is not described as full qualification.
