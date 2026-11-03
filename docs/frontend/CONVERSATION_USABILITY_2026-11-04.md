# Rukh AI conversation continuation — 4 November 2026

Historical scope of local commit 3592fccb. The subsequent [native chat handoff](CHATBOX_COMPLETION_2026-11-04.md) supersedes the native-reply and unavailable-browser limitations below; its migration and provider contract are a separate continuation.

## Task contract

Base: main `a8385b5a2849afd01486d86106cfa4ea491f46fd` (merged #615).
Branch: `feat/rukh-conversation-usability-20261104`.

Objective: make the message composer visible on first entry, remove mandatory title creation, and show real linked Agent progress within the conversation. Reuse ConversationWorkspace, CoworkerClient conversation idempotency and owner-authenticated agentRun reads. No new backend, database or provider contract.

Root cause: ConversationWorkspace rendered the textarea only when a selected conversation existed. A fresh workspace therefore had no chat box. Messages were stored as user records and results required navigating to a separate Agent screen. Error notices lived in a history panel hidden on phones.

## Implemented behavior

- Always-visible message composer, disabled during initial load or rollout failure.
- First save creates a conversation named from the brief and appends the message. Creation and append identities survive an unchanged retry after a lost response. No automatic task dispatch.
- New chat without creating an empty server record, history title search, and research/writing/planning/Bangla prompt starters.
- Enter saves, Shift+Enter adds a line; IME composition and keyCode 229 do not submit.
- Errors in the primary thread; manual-title errors also appear in an open Conversations drawer. Initial list errors offer retry.
- Newest linked run loaded eagerly, historical runs expanded on demand. Real linked run message, state, partial-completion label, plan and tool summaries inline. Abortable polling stops for terminal/input/blocked runs, retries are read-only, unrelated/stale run responses are rejected.
- Existing Start task, cancel, full run details, source selection, memory, approval and Editor paths preserved.
- Theme-token styles and touch controls; no new dependencies.

## Feature evidence and remaining work

Official reference reviewed: https://ai.meta.com/muse/ and https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/ . These describe the reference product, not Rukh capability qualification.

| Reference capability | Rukh source surface | Remaining qualification / work |
| --- | --- | --- |
| Conversation-first UI | ConversationWorkspace | This patch removes first-entry friction. Native assistant conversation messages/streamed chat answers are absent from the current conversation API. |
| Task plans and progress | AgentWorkspace, inline ConversationRunStatus | Real workers/provider availability and production qualification remain separate. |
| Goals and proactive ideas | GoalWorkspace | Source exists; this pass does not enable flags or establish operated delivery. |
| Recurring/background work | AutomationWorkspace | Requires persistent scheduler/worker and live delivery verification. |
| Reviewable memory | Saved context and Agent memory proposals | Existing consent/version/delete behavior preserved; no new automatic memory collection. |
| App connections and action approvals | ActionWorkspace | Existing connector/permission paths preserved; no new credentials or authority. |
| Browser and custom compute | BrowserWorkspace, SandboxWorkspace | Existing default-off isolation and release gates preserved; no dedicated production VM provisioned. |
| Documents and writing | Files & drafts, separate Rukh Editor | Existing artifacts and writing review preserved; no new image/audio generation endpoint. |
| Transactions | TransactionWorkspace, NegotiationWorkspace | No live purchase/payment provider activation or purchase protections claimed. |
| WhatsApp / native mobile / glasses | No corresponding inspected frontend contract | Separate products/integrations, not implemented by this web frontend change. |

## Validation and limits

Initial red run: seven conversation entry/discovery regressions failed as expected, 150 existing checks passed. Follow-up transient-list retry and mobile title-error regressions also failed before fixes. Agent status tests initially could not bundle because its production component did not exist; five renderer checks then passed after implementation.

The prior conversation identity tests now expect two reads of the same exact run: the inline projection and the full-details click. They still reject fallback to unrelated recent runs.

Local full JavaScript suite and three frontend build results are recorded in the PR/handoff after final verification. Browser execution is unavailable: no Chromium binary is installed and Playwright browser download returned an invalid/truncated archive. No desktop/mobile screenshot, accessibility conformance, real auth session, real provider dispatch, live deployment or staging test is claimed.

Fresh base GitHub CI: Frontend tests and builds succeeded; both backend jobs failed `tests/test_coworker_quality_eval.py::test_curated_multilingual_quality_fixture_passes` (actual score 0.8333, expected 1.0). Governance audit and merge gate failed. These precede this patch and remain separate work.

Code review found two Important issues: UTF-16 title truncation could split an emoji, and historical messages could trigger thousands of full-run reads. Both were reproduced by failing renderer tests and fixed: title truncation now uses Unicode code points; only the newest run loads eagerly and older results require explicit expansion. Author verification reruns the full JavaScript suite and builds after these fixes. A minor presentation improvement remains deferred: tool summaries use structured JSON inside optional details. This is agent review, not independent human approval. Exact-head remote CI and human review remain required before integration. No merge, production deployment/alias/env change, paid provisioning or capability activation was performed.
