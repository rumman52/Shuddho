# Rukh AI frontend implementation ledger

Updated 4 November 2026 (Asia/Dhaka). Source base: `main 4db2843e0d43447af5065b04c13b82cf710a1084`. Relevant merged work: PRs #615, #616, #617, #618, #620 and #622.

| Workstream | Source status | Evidence / remaining work |
|---|---|---|
| Architecture and shared packages | Implemented | `docs/frontend/ARCHITECTURE.md`, `packages/auth`, `packages/coworker-client` and `packages/design-system` |
| Independent Coworker and Editor apps | Implemented | `apps/coworker` and `apps/editor`; same-origin live routing/session still needs operated verification |
| Coworker-first routing and theme | Implemented | PR #615 and route/browser correction #620; root opens Coworker when enabled, Editor remains at `/editor` |
| First-entry conversation composer | Implemented | First-message creation, stable retry identity, history search, prompt starters and IME-safe keyboard submission |
| Inline linked Agent progress | Implemented | Real owned run message/plan/tool summaries, partial completion, failure/retry and stale-response isolation |
| Native assistant text chat | Implemented; default off | PR #616; owner-scoped persisted replies, bounded context, duplicate-claim protection, budget reservations and interrupted recovery; migration 0063 and existing backend configuration required |
| Conversation rename | Implemented | PR #617; authenticated owner-scoped PATCH, optimistic `updated_at` revision, stale conflict and CORS preflight |
| Conversation export | Implemented | PR #617/#618; complete paginated history to local Markdown or JSON, including replies, source labels and provenance; Unicode-safe filenames |
| Safe Markdown replies | Implemented | PR #617; inert raw HTML, safe HTTP/HTTPS/mailto links, headings, lists, tables, blockquotes and code |
| Source attachments | Implemented | PR #617/#618/#622; existing upload/manifest APIs, five-source limit enforced in UI and schema, owner-scoped untrusted inputs; direct chat does not read files |
| Sources, memory and action approvals | Existing source preserved | Version-bound source selection, reviewable memory and explicit Agent start/external-action approval remain canonical |
| Cross-app document handoff | Existing source preserved | Owner-bound upload/manifest/artifact contracts; fresh live auth/storage/provider run not claimed |
| Frontend CI on latest main | Passing | CI run #41800917260: `Frontend tests and builds` succeeded |
| Python `test-and-build` on latest main | Passing | CI run #41800917260: `test-and-build` succeeded |
| Mandatory Coworker CI on latest main | Pending at handoff | CI run #41800917260: `coworker` was still in progress; inspect its final exact-head result |
| Governance audit | Failing | CI run #41800917260 reports main branch protection is not confirmed; this is separate from the chat UI implementation |
| Browser evidence | Synthetic API checks recorded | Native chat Chromium evidence covers five viewports and composer/send/reply/history/drawer/theme behavior; no real signed-in production session claimed |
| Live deployment | Not verified | Vercel commit status is success; that alone does not verify current routes, auth, API or provider behavior |
| Full Muse parity | Incomplete | Streaming, voice/audio, image capabilities, direct file-aware chat, native integrations and operated Agent/automation/transaction qualification remain separate work |

[Native text-chat contract and rollout requirements](CHATBOX_COMPLETION_2026-11-04.md).
[Muse-inspired enhancement scope, evidence and remaining gaps](MUSE_CHAT_ENHANCEMENTS_2026-11-04.md).

No production environment, database, auth configuration, provider credential, alias or deployment was changed. Native replies remain default-off. The full roadmap and production qualification remain incomplete.
