# Rukh AI Writing Assistant workspace — 6 November 2026

## Design source and fidelity

- Approved Figma file: `eIeIHgClMJia6kRi484Xsl`.
- Existing desktop/mobile Coworker references: `3:181` and `4:1703`.
- The committed `docs/frontend/design-reference/design.json` contains the former Editor desktop/mobile frames and shared Rukh layout tokens, but no dedicated Grammarly-style Writing Assistant frame.
- Live Figma inspection was attempted for this task but the connected Starter plan returned its MCP request-limit response. This implementation therefore uses the committed SVG/JSON exports and `design-tokens.json`; it does not claim a fresh live Figma inspection or an exact pixel match to an unavailable Writing Assistant frame.
- Retained the approved paper-neutral palette, Rukh green `#245A43`, Inter UI typography, spacing, border and radius system.

## Interface delivered

- Persistent Rukh workspace rail with Coworker, Fly, Writing Assistant, recent chats/files and account controls.
- Documents-first Writing Assistant landing page with new-document creation, authenticated file upload, search, recent source documents and generated artifacts, download and owner-scoped removal actions.
- Version history and Trash navigation are present, but their views clearly state that the current workspace API does not expose version browsing or restore; no synthetic history or trash data is shown.
- Dedicated document toolbar with the current artifact title, document word count, runtime status, settings and Deep AI Review.
- Focused center writing canvas with Bangla typography, document status, writing goal and tone controls, inline issue marks and word/character status.
- Separate right-hand suggestions inspector with category filters, source labels, apply/ignore/explain actions, safe batch application, rewrite options and corrected-text preview.
- Category-specific spelling, grammar, clarity, punctuation and spacing visual states. Counts and status are taken from the existing analysis response; no synthetic writing score is displayed.
- Responsive mobile layout with a dedicated review bottom sheet, backdrop, Escape handling, focus containment and focus restoration.
- Current artifact names are shown in the document toolbar when an existing text artifact is opened.

## Preserved behavior and boundaries

- Existing quick local checks, Deep AI Review, backend/provider diagnostics, cancellation and request sequencing remain in the shared writing engine.
- Existing suggestion validation, apply/dismiss, dictionary and rewrite flows are unchanged.
- Existing user-scoped draft storage, owner-authenticated artifact reading, explicit copy-save behavior, and Coworker handoff remain unchanged.
- Added an owner-authenticated source-document content GET route with server-side size and SHA-256 verification; no database schema or migration, provider activation, external permission or API secret was added.
- This UI does not claim cloud autosave; saved artifact copies remain explicit user actions.

## Verification

- Added SSR assertions for the document title, editor canvas, suggestions inspector, review filters, Deep AI Review control and document-library entry points.
- Added client and backend tests for owner-authenticated source-document reads, content integrity and cross-account isolation.
- Added CSS contract assertions for the three-pane desktop layout and mobile review sheet.
- Extended the Chromium browser workflow to open and close the mobile review sheet and check narrow-screen horizontal overflow.
- Exact-head CI and the Vercel preview must pass before merge. A preview build is not production qualification.
