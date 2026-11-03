# Rukh AI Default Coworker Entry and Workspace Switching

**Status:** Approved direction from the user's 2026-11-03 implementation request  
**Scope:** Frontend routing and workspace navigation in the Shuddho repository, now branded Rukh AI.

## Intent

When a user opens the Rukh AI application at `/`, take them directly into the AI Coworker workspace whenever the existing Coworker release flag is enabled. Keep Web Editor as a distinct, independently navigable writing workspace at `/editor`. Preserve a deliberate workspace directory at `/workspaces` rather than making users choose a product on every launch.

The existing Editor is already a separate application using the shared `WritingAssistant` writing surface. This work connects the two workspaces; it does not replace or duplicate the writing engine.

## Goals

- Route `/` to Coworker when `VITE_COWORKER_ENABLED === "true"`.
- Preserve the existing release gate: when Coworker is disabled, `/` and `/coworker` must continue to render the safe workspace home rather than bypassing the gate.
- Expose the existing workspace directory at `/workspaces`.
- Keep `/editor` as the separate Grammarly-style writing workspace.
- Make Coworker and Editor navigation accurately label and link to the workspace directory.
- Preserve existing authentication, conversation persistence, editor content, and explicit Agent execution/approval boundaries.

## Non-goals

- Do not bypass or change the Coworker release gate.
- Do not enable Coworker in production or change Vercel environment variables as part of this code change.
- Do not add a new AI chat backend, assistant-message contract, streaming protocol, or Agent execution behavior.
- Do not rebuild the existing writing editor or claim new grammar features that are not already implemented.
- Do not merge Coworker and Editor into one mixed interface.
- Do not change database schemas, auth policies, Supabase configuration, or transaction/automation capabilities.

## Approaches considered

1. **Coworker-first with a gated fallback (selected):** `/` opens Coworker only when the existing feature flag is enabled; `/workspaces` preserves the workspace directory; `/editor` remains independent. This matches the user's desired first-run experience without bypassing the release gate.
2. **Always route root to Coworker:** rejected because it would make a frontend route change override an intentional default-off release control.
3. **Keep the chooser as the root page:** rejected because it adds an unnecessary decision before the primary Coworker experience on every visit.

## Existing implementation and constraints

- The app is a React 18 + Vite workspace.
- `apps/web-editor/src/WorkspaceShell.tsx` selects the standalone app.
- `apps/web-editor/src/appRoutes.mjs` owns route classification and the Coworker release gate.
- `apps/coworker/src/App.tsx` already has the Coworker top bar and a Web Editor link.
- `apps/editor/src/App.tsx` already mounts the shared writing assistant and supports a Coworker handoff when the feature is enabled.
- `apps/web-editor/src/App.tsx` contains the existing multilingual writing assistant with spelling, grammar, punctuation, spacing, clarity, and rewrite flows.
- The Coworker release flag remains `VITE_COWORKER_ENABLED`; a disabled or missing flag must remain fail-closed.
- No new dependencies are required.

## Navigation behavior

| Path | Coworker enabled | Coworker disabled |
| --- | --- | --- |
| `/` | Coworker | Workspace directory |
| `/coworker` | Coworker | Workspace directory |
| `/editor` | Web Editor | Web Editor |
| `/workspaces` | Workspace directory | Workspace directory |
| Unknown path | Workspace directory | Workspace directory |

The Coworker header's "All workspaces" action and the Editor header's "All workspaces" action must point to `/workspaces`, not `/`, because `/` becomes the Coworker-first entry point.

## Acceptance criteria

- Route tests prove the path/flag matrix above.
- A Coworker-enabled root route renders the Coworker standalone app.
- A disabled Coworker flag cannot be bypassed through either `/` or `/coworker`.
- Coworker and Editor headers provide a working route to `/workspaces`.
- Web Editor remains separately addressable at `/editor` and its existing writing functionality is untouched.
- Existing app tests and builds pass; deployment is not promoted as part of this change.
