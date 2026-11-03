# Rukh AI Responsive Premium Frontend — Design Specification

**Status:** Approved implementation direction from the user's 2026-11-04 request.  
**Repository:** `rumman52/Shuddho`  
**Scope:** Frontend visual system, Coworker mobile navigation/context, Editor mobile workspace, theme preference and accessibility polish.

## Product contract

- Keep AI Coworker as the default route at `/` only when `VITE_COWORKER_ENABLED=true`.
- Keep `/coworker`, `/editor` and `/workspaces` independently addressable under the existing route contract.
- Keep Web Editor separate from Coworker and preserve the current same-origin session and artifact handoff behavior.
- Preserve all existing conversation, Agent activity, goals, automation, browser, sandbox, file, approval, transaction and writing-review capabilities.
- A saved message is not an Agent dispatch. External actions still require their existing deterministic approval controls.

## Visual direction

Use the new research recommendation: warm neutral surfaces, restrained deep-green accent, consistent outlined controls, low-noise borders, subtle elevation and system-consistent typography. This supersedes the violet accent values in the 2026-11-03 visual spec only; it does not replace the existing component architecture or product contract.

| Token | Light | Dark |
|---|---|---|
| Background | `#F7F7F5` | `#171916` |
| Surface | `#FFFFFF` | `#20231F` |
| Muted surface | `#F1F1EE` | `#262A25` |
| Border | `#E3E3DE` | `#373D35` |
| Text | `#171816` | `#F0F2EC` |
| Muted text | `#6C706A` | `#B1B8AE` |
| Accent | `#176B5B` | `#78CDBB` |
| Accent soft | `#E6F2EF` | `#20382F` |

Retain DM Sans / Manrope for interface text and Noto Serif Bengali for Bengali writing. Keep user-provided text direction-aware (`dir="auto"`). Do not use gradients, emoji or copied competitor branding as structural UI.

## Desktop behavior

- Keep the existing Coworker workspace navigation, conversation list, thread and Context inspector as distinct regions.
- Use a flexible center column; keep conversation history and Context independently scrollable.
- Keep the message composer reachable at the bottom of the conversation pane.
- Keep Editor's recent-file library, writing canvas and existing AI review panel as separate work regions.
- Maintain comfortable reading widths at 1366×768 and 1440×900.

## Mobile behavior

At 720px and below, do not stack all desktop side panels into the main reading flow.

- Coworker: keep the conversation thread as the primary surface. Expose Conversations and Context through accessible sheets/drawers; keep the workspace navigation horizontally scrollable with 44px minimum controls. Drawers close by close control, backdrop or Escape and restore focus to their trigger.
- Editor: keep the writing canvas as the primary surface. Recent files open in a drawer; AI review opens as a bottom sheet using the existing review toggle. Remove the fixed 720px editor canvas that currently forces desktop-sized scrolling on phones.
- Avoid horizontal overflow at 375×812 and 390×844. Respect virtual keyboards, safe viewport height and reduced-motion preferences.

## Theme behavior

- Add a light/dark toggle to Coworker, Editor and the workspace directory.
- Persist the preference locally, defaulting to the system preference when no saved choice exists.
- Apply the existing `data-rukh-theme` token contract before app render where possible.
- Ensure core surfaces, form controls, drawers, review panels and focus rings remain legible in both themes.

## Accessibility

- Target WCAG 2.2 AA; verify contrast for actual token pairings rather than assuming hex values prove conformance.
- Use semantic buttons, labelled navigation, `aria-expanded`, `aria-controls`, dialog semantics for mobile sheets and visible focus.
- Use Escape dismissal, focus return and keyboard navigation for sheets.
- Use at least 44px primary mobile control heights; preserve reduced-motion behavior.
- Do not announce every streaming token; existing status/error messages remain concise.

## Explicit non-goals

- No API, database, Supabase schema/RLS, authentication-provider, Agent, transaction, browser or automation semantics changes.
- No new runtime dependencies.
- No production environment, production alias, domain, database, auth setting or deployment promotion changes.
- No fabricated chat responses, autosave, files, activity or capabilities.
- Full translation of every feature surface is a separate localization milestone; this pass preserves Bangla content entry/output and direction-aware rendering.

## Acceptance criteria

1. Coworker default routing and the Editor handoff/session contract remain unchanged.
2. At 1440×900 and 1366×768, Coworker and Editor have no horizontal overflow or clipped primary actions.
3. At 390×844 and 375×812, Coworker conversation remains primary; Conversations and Context open/close as accessible sheets.
4. At the same mobile sizes, Editor remains usable without a fixed 720px canvas; Recent files and AI review are reachable as drawers/sheets.
5. Theme preference persists across route reloads; light and dark states have readable text, surfaces and focus indicators.
6. Existing app tests and builds pass; the PR's frontend CI job passes. Inherited backend/governance failures are reported separately.
7. No production environment or deployment setting is changed.
