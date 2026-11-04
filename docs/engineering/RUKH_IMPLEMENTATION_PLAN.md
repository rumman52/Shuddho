# Rukh AI implementation plan — 4 November 2026

This is a phased plan for the user-supplied Rukh AI engineering specification. Do not treat a source change or passing unit suite as production qualification.

| Priority | Workstream | Current evidence | Next action |
|---|---|---|---|
| P0 | Coworker conversation and default entry | PR #617 merged; authenticated Coworker source defaults to conversations after sign-in; root entry remains feature-gated | Verify deployed env/config and browser flow after staging is available; do not activate production flags here |
| P0 | Quality gate | PR #619 draft; numeric-fact fix implemented; lightweight Python and frontend CI passed | Wait for heavy Coworker job, review exact head and preserve draft until independently reviewed |
| P0 | Main governance | Main governance audit failed: protection not confirmed | Repository owner/admin must configure and verify native branch protection and required checks |
| P0 | Render staging | Workspace discovered but not user-confirmed | Ask user to confirm the `Rumman` workspace before service/database inspection |
| P0 | Staging database continuity | Not inspected in this turn | Confirm resource, backup/export, expiry and restore path before any migration or recovery |
| P1 | Agent execution and approvals | Separate dispatch, cancellation and activity APIs exist in source | Verify real worker, API/worker revision parity, recovery and approval journeys in staging |
| P1 | Rukh Editor | Separate route/app and existing writing workflows | Verify editor persistence, review/suggestion application, export and Coworker handoff in browser |
| P1 | PostHog | Active project reports no ingested events in the last 30 days | Add privacy-safe instrumentation only after confirming consent, env configuration and ingestion plan |
| P1 | Streaming | Direct assistant reply provider uses `stream: false`; task progress has a separate SSE path | Design a separate reply-stream contract and persistence/reconnect semantics before implementation |
| P2 | Visual/accessibility/performance | Existing responsive UI tests pass in CI; deployed browser audit not performed | Run exact preview browser checks at the specified viewports and WCAG checks |

## Release rule
Production remains unchanged. Do not merge, deploy, migrate production, enable flags, provision paid resources or change secrets without the required authorization and staging evidence.
