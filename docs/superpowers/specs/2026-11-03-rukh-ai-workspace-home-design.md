# Rukh AI workspace home — design specification

## Brief

- **Audience:** Professionals who need a focused place to write and a reliable AI teammate for multi-step work.
- **Category:** AI work platform with two connected workspaces: Co-workers and Web Editor.
- **Adjectives:** composed, capable, clear.
- **Anti-adjectives:** noisy, gimmicky, generic.
- **Distinctive:** Rukh pairs a multilingual writing surface with persistent, approval-aware AI work execution.

## Intent

Make the root route a clear Rukh AI workspace home. It should present exactly two primary destinations: **Co-workers** and **Web Editor**. The product should feel like one considered workspace with two distinct ways to work.

## Reference and visual direction

- Keep Rukh's existing identity: the lowercase “r” mark, DM Sans UI family, warm neutral surfaces, charcoal text and restrained violet interaction accent from `packages/design-system/src/tokens.css`.
- Use the quiet, conversation-first product framing of [Muse AI](https://muse.ai/) as a reference for clarity and spaciousness. Do not reproduce its logo, wording, exact composition or proprietary assets.
- Direction: quiet editorial workspace. The page should feel calm and operational, with one clear headline, a generous reading measure and two asymmetrical product surfaces.
- Use the existing design tokens; do not introduce another component library or external imagery.
- No gradient blobs, neon effects, fake activity metrics, emoji icons, numbered card labels or decorative glass effects. Use small inline SVG line icons and product-specific interface previews.

## Information architecture and behavior

- `/` always renders the Rukh AI workspace home.
- `/editor` and `/editor/*` always open Web Editor.
- `/coworker` and `/coworker/*` open Co-workers only when `VITE_COWORKER_ENABLED=true`.
- When Co-workers is disabled, its home card remains visible with a truthful **Private preview** state and a disabled action. Direct Coworker routes return to the home page. The feature flag remains default-off.
- The Web Editor card remains active and links to `/editor`.
- Both standalone workspaces provide a consistent route back to the Rukh AI home and a link to the other workspace only when that destination is available.

## Product content

### Co-workers
Describe the persistent AI teammate: it can keep a task brief, source files and conversation together; prepare multi-step work; and return drafts for human review. Do not imply that the feature is production-enabled when the flag is off.

### Web Editor
Describe the multilingual writing workspace: spelling, grammar, clarity and contextual AI review alongside the draft. Preserve the existing editor behavior and saved-document boundaries.

## Constraints and non-goals

- Preserve Supabase authentication, owner-scoped artifact reads, SHA-256 checks, file download behavior, explicit action approvals and all backend safety boundaries.
- Do not change backend services, database schemas, provider settings, billing, transaction permissions or production environment flags.
- Do not deploy to production or merge this work without fresh CI and release qualification.
- Do not copy Muse AI branding, logos, screenshots, exact text or proprietary assets.
- Do not remove existing writing, review, upload, download or authentication functionality.

## Accessibility and responsive behavior

- Semantic header, navigation, main and section landmarks.
- All enabled links and controls are keyboard reachable with visible focus.
- Disabled preview state is conveyed in text and with native disabled semantics.
- Minimum 44px interactive targets; no horizontal overflow at 320px.
- Comfortable body text (at least 16px), readable line length and WCAG AA text contrast.
- Respect `prefers-reduced-motion`; hover transitions must not carry essential meaning.
- Product surfaces stack on narrow viewports and retain a clear reading order.

## Acceptance criteria

1. Root route displays the Rukh AI home with exactly two primary workspaces.
2. Co-workers is shown as private preview when the flag is false and opens only when true.
3. Web Editor remains available at `/editor`.
4. Editor does not render Coworker handoff controls or recent Coworker files while the feature is disabled.
5. Both standalone applications have consistent navigation back to the home.
6. Existing auth, editor and Coworker behavior remains unchanged when the relevant feature is enabled.
7. Route, feature-gate, app-shell and workspace tests pass; all workspaces build.
8. Desktop and mobile browser verification is recorded. If a browser or deployment is inaccessible, state that limitation rather than claiming visual qualification.
