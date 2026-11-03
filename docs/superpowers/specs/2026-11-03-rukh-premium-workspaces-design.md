# Rukh AI — Premium Coworker and Web Editor Experience

**Status:** Approved product direction from the user's Rukh AI frontend request on 2026-11-03.  
**Scope:** Frontend experience, workspace navigation, authentication presentation, and preview qualification only.

## Product contract

- The AI Coworker is the default workspace at `/` when `VITE_COWORKER_ENABLED=true`.
- A visitor who is not signed in sees the Coworker sign-in experience at the default entry point.
- After successful sign-in, the user lands in the persistent Coworker conversation workspace. The default view is `conversations`.
- Web Editor remains a separate workspace at `/editor`, available from the Coworker header and from the workspace directory.
- `/workspaces` remains an optional directory; it is not the default entry page.
- Both applications use the same origin and the shared `@rukh/auth` Supabase browser client so the persisted session can be restored in either workspace.
- The existing `rukhai.vercel.app` Vercel alias is the short branded default URL. The legacy `shuddho-web-editor.vercel.app` domain redirects to it.

## Experience architecture

### AI Coworker

Use a calm, professional, conversation-first workspace:

1. **Navigation:** compact, collapsible-feeling workspace navigation for conversations, agent activity, goals, automations, browser, files, approvals and tools.
2. **Conversation:** persistent thread with explicit message saving and explicit Agent dispatch. A message is not itself permission to execute work.
3. **Context:** sources, current Agent activity, and saved memory, each with clear provenance and state.

The interface must preserve the existing execution and approval boundaries. Do not imply that a message automatically authorizes external actions.

### Web Editor

Keep Web Editor independently addressable and Grammarly-style:

- Left: recent generated files/workspace navigation.
- Center: writing surface.
- Right: existing AI review and rewrite panel within the Writing Assistant.

Do not claim that the editor has cloud autosave or a document library if the current backend does not provide those capabilities. Opening a saved artifact must preserve the existing copy semantics and confirmation before replacing unsaved text.

## Visual system

- Original Rukh AI visual identity; take inspiration from the clarity, restraint and spacing of leading AI products without copying another product's branding or layout.
- Reuse the existing DM Sans / Manrope typography, Noto Serif Bengali writing font, and shared design tokens.
- Neutral paper/surface palette, restrained violet accent, consistent borders, radii, focus rings and subtle shadows.
- Accessible contrast, visible keyboard focus, reduced-motion support, responsive layouts and clear loading/error/empty states.
- Avoid emoji or inconsistent text glyphs as primary navigation icons.

## Authentication and routing

- Preserve `getRukhAuthClient`, the shared Supabase storage key, persisted sessions and automatic token refresh.
- Keep the Coworker release gate fail-closed. Missing/false flag must not expose Coworker via `/` or `/coworker`.
- Keep `/editor` available independently.
- Use same-origin routes for session continuity.
- Email confirmation and password recovery continue to redirect to the same origin; verify the preview host is accepted by Supabase Auth before claiming the flow is qualified.

## Deployment and domain boundaries

- Current short Vercel alias: `rukhai.vercel.app`.
- Legacy Vercel alias: `shuddho-web-editor.vercel.app` redirects to the branded alias.
- Preview-only variables for the implementation branch may use the existing `shuddho-staging` Supabase project.
- Do not change production environment variables, production database, production auth settings, or production aliases as part of preview qualification.
- Do not attach an unconfirmed custom domain such as `rukh.ai`. A custom domain migration requires proof of ownership and an explicit final domain choice.
- No production promotion is included in this implementation.

## Non-goals

- No new AI backend, message schema, streaming protocol, or execution authority.
- No Supabase schema/RLS changes.
- No change to Coworker transaction, automation, browser, sandbox or agent safety semantics.
- No fake document autosave, fake AI replies, or fake product functionality.
