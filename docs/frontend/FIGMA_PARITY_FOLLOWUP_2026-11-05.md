# Rukh AI Figma parity follow-up — 5 November 2026

## Source of truth

- Figma file: `eIeIHgClMJia6kRi484Xsl`
- Desktop Coworker: node `3:181`
- Mobile Coworker: node `4:1703`
- Exported screen data and tokens: `docs/frontend/design-reference/design.json`, `design-tokens.json`, and retained SVG exports.
- Figma MCP reads remained rate-limited by the Starter-plan limit. This follow-up is grounded in the checked-in exports; it does not claim fresh live Figma node inspection.

## Follow-up implementation

### Authentication entry

- Replaced the modal with the approved split-screen sign-in page and responsive narrow-screen layout.
- Preserved email sign-in, sign-up, password reset and recovery.
- Added password visibility control.
- Added a real Supabase Google OAuth call. It reports the provider's actual configuration error if Google OAuth is not enabled.
- Preserved unsent first-message drafts in tab session storage so a same-tab OAuth redirect does not lose the draft.

### Workspace entry

- The root workspace now opens Coworker by default.
- Explicit `VITE_COWORKER_ENABLED=false` remains available as a rollback.
- No production rollout or secret/configuration change was made.

### Website Editor

- Added the approved workspace rail with recent Coworker conversations, account identity, theme control and Settings navigation.
- Added the Activity & context drawer with project/conversation context, recent outputs, and a clear statement that saving source does not publish a website.
- Kept Website as the default editor view. Writing remains accessible for Coworker conversation handoffs.
- Matched the central website canvas, layer rail and right inspector proportions more closely to the Figma desktop frame.
- Added functional Layout gap and Typography controls alongside Background and Spacing.
- Preserved sandboxed preview and verified, owner-scoped source-file saves.

### Projects and Plugins

- Matched the Projects page heading and subtitle hierarchy.
- Matched the Plugins page heading and six primary cards from the Figma frame: Google Drive, GitHub, Google Calendar, Gmail, Notion and Slack.
- GitHub, Notion and Slack are visibly marked **Coming soon** because no provider integration exists yet; no fake connected state or access is presented.
- Existing Microsoft 365 and LinkedIn options remain available under More integrations.
- Connection permissions and approvals are collapsed by default, keeping the primary screen aligned with the design while retaining the real controls.

## Verification status

- PR: https://github.com/rumman52/Shuddho/pull/636
- Branch: `feat/rukh-figma-parity-followup-20261105`
- Current validation is running in GitHub Actions on the PR head. Do not treat this document as a green CI report until exact-head checks complete.
- Browser acceptance was updated for full-page sign-in, same-tab Coworker/Editor navigation, editor context, Website inspector controls, and the six plugin cards.
- Local physical-device testing is not claimed.

## Release boundaries

- Google OAuth requires Google provider configuration in the existing Supabase project.
- Public authentication remains dependent on correct deployment-time Supabase URL and publishable key.
- Projects remain gated by the already documented authorized migration `0064` and `SHUDDHO_PROJECTS_ENABLED=true`.
- Real AI provider response, live project isolation, and production alias/revision are not verified by this frontend change.
- The frontend Coworker entry is enabled by default; setting `VITE_COWORKER_ENABLED=false` is the explicit UI rollback. This does not enable backend execution: `SHUDDHO_COWORKER_ENABLED` and the dependent backend service gates remain default-off until separately qualified.
- No production secrets, live database migration, backend provider enablement, paid resource, or production promotion was performed.
- The connected Vercel API still does not expose the existing Rukh project to this connection. Hosted preview and production qualification remain separate release steps.
