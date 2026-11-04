# Rukh AI feature-preservation matrix — 4 November 2026

| Feature | Source status | Qualification boundary |
|---|---|---|
| Coworker standalone app | Implemented | Root entry remains feature-gated |
| Coworker authentication/session restoration | Implemented in source | Live Supabase/Vercel auth not verified |
| Conversation create/list/open/switch | Implemented in source | Live staging flow not verified |
| Persistent message history | Backend API and pagination implemented | Live refresh/reopen not tested in this turn |
| Assistant text reply | Authenticated backend reply route implemented | Non-streaming; real provider execution not re-tested here |
| Agent dispatch | Separate explicit dispatch operation | Requires worker and staging qualification |
| Agent progress/activity | Existing activity and SSE task progress surfaces | Live worker parity/recovery not verified |
| Message Markdown | Headings, lists, tables, code, links and emphasis renderer present | Browser accessibility/edge cases need deployed review |
| Conversation rename/delete/search/export | Existing UI/client support | Live persistence not re-tested here |
| Attachments | Existing task/source upload flows and PR #618 correction | Direct chat attachment semantics remain distinct |
| Memory/context | Existing Coworker memory and context surfaces | RLS/owner-isolation staging audit pending |
| Rukh Editor | Separate application route and existing writing workflows | End-to-end handoff/persistence not verified here |
| Streaming direct replies | Not implemented; provider uses `stream: false` | Requires a new tested backend transport contract |
| Voice/image generation in direct chat | Not established by current text-reply route | Do not display fake or unsupported controls |

Preservation rule: do not replace or simplify existing Agent, automation, connector, browser, sandbox, transaction, document, or Editor workflows while repairing the conversation surface.
