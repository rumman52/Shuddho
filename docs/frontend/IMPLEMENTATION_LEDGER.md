# Rukh AI frontend implementation ledger

Updated 4 November 2026 (Asia/Dhaka). This supersedes the stale 2 November pending-source checklist. Source base: main `a8385b5a2849afd01486d86106cfa4ea491f46fd`, merged PR #615. Continuation branch: `feat/rukh-conversation-usability-20261104`.

| Workstream | Source status | Evidence / remaining work |
|---|---|---|
| Architecture and shared packages | Implemented | `ARCHITECTURE.md`, packages/auth, coworker-client and design-system |
| Independent Coworker and Editor apps | Implemented; local builds pass | apps/coworker and apps/editor; same-origin live routing/session still needs operated verification |
| Coworker-first routing and theme | Implemented; base frontend CI passed | PR #615; light/dark, mobile history/context and Editor drawers |
| First-entry conversation composer | Implemented in continuation | Visible before a titled conversation exists; first-message creation, retry identity, search and starters tested |
| Inline linked Agent progress | Implemented in continuation | Real owned run message/plan/tool summaries, partial completion, failure/retry and stale response tests |
| Sources, memory and action approvals | Existing source preserved | Version-bound source selection; reviewable memory; explicit Agent start and external-action approval |
| Cross-app document handoff | Existing source preserved | Owner-bound upload/manifest/artifact contracts; no fresh live auth/storage/provider run claimed |
| Local JavaScript qualification | Passing | Full root npm test; web-editor 169 tests, standalone Coworker 4 and Editor 1, plus gateway/shared/NLP/production API checks |
| Local frontend builds | Passing | TypeScript + Vite: web-editor, Coworker and Editor; Coworker retains >500 kB chunk warning |
| Exact continuation-head CI | Pending | Inspect PR checks after publication |
| Desktop/mobile browser verification | Passing with synthetic API | Real Chromium and real workspace components at 1440×1000, 1366×768, 1024×768, 390×844 and 375×812; composer visibility, send/reply, scroll, history search, drawer focus, new chat and dark mode |
| Live deployment | Not verified by continuation | Base Vercel commit status reports success; that alone does not prove auth, routes, visible chat or current code deployment |
| Native assistant text chat | Implemented; default off | Owned authenticated endpoint, persisted answers, bounded context, duplicate protection, daily/shared model budgets, interrupted recovery; migration 0063 required |
| Full Muse feature parity | Incomplete | Streaming, image/audio generation, native-device products and remaining operated Agent/automation/transaction qualification are outside this text-chat implementation |

[Continuation contract, capability matrix and validation limits](CONVERSATION_USABILITY_2026-11-04.md).
[Native chat implementation and release handoff](CHATBOX_COMPLETION_2026-11-04.md) supersedes the earlier native-chat and browser limitations.

No production environment or database was changed. No provider activation, paid infrastructure or deployment promotion occurred. The new capability defaults off. The full roadmap and production qualification remain incomplete.
