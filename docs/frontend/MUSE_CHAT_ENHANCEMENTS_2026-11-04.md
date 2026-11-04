# Rukh AI Muse-inspired conversation enhancements — 4 November 2026

**Status:** The scoped implementation is merged into `main`. This handoff records source behavior and verification limits; it does not claim complete Muse parity or production qualification.

- Repository: [rumman52/Shuddho](https://github.com/rumman52/Shuddho)
- Main revision: `4db2843e0d43447af5065b04c13b82cf710a1084`
- Review branch for this documentation handoff: `docs/rukh-muse-chat-handoff-20261104`

## Merged implementation

| PR | Merged commit | Scope |
|---|---|---|
| [#616](https://github.com/rumman52/Shuddho/pull/616) | `7b20c1c34217fdfe8ac7952fa6b8c40b5dc611c5` | Coworker-first native text chat, persisted assistant replies, bounded context, retry/idempotency and browser qualification |
| [#617](https://github.com/rumman52/Shuddho/pull/617) | `6546b68acada36bf8a543613afdcec2c9d74ec41` | Owner-scoped rename, PATCH CORS, conversation export, safe Markdown and source attachment controls |
| [#618](https://github.com/rumman52/Shuddho/pull/618) | `56b1678ec92233df45b7a95911808c2fca222ccf` | Corrected attachment-render test and Unicode-safe export filename handling |
| [#620](https://github.com/rumman52/Shuddho/pull/620) | `278b646f05501a19834cc48191785e0986fee1e3` | Coworker-first route and browser-flow regression repair |
| [#622](https://github.com/rumman52/Shuddho/pull/622) | `4db2843e0d43447af5065b04c13b82cf710a1084` | Server-enforced five-source limit and final route/Markdown/browser regression coverage |

## User-visible capabilities

1. **Conversation-first Coworker:** the root route opens Coworker when its release capability is enabled; Web Editor remains separate at `/editor`. A first message can create a titled conversation without a separate setup step.
2. **Native text replies:** authenticated owner-scoped replies persist with conversation history. Chat and Save-only modes are separate from explicit Agent task dispatch. Retry checks the existing reply claim instead of silently sending a second inference.
3. **Conversation management:** inline rename uses the conversation's exact `updated_at` value as an optimistic concurrency token. Stale edits return a conflict; another owner's conversation remains hidden as 404. PATCH preflight uses the existing allowed CORS origin.
4. **Conversation export:** Markdown and JSON downloads include the fully paginated conversation, assistant replies, source labels and message provenance. Downloads are generated locally in the browser.
5. **Safe Markdown:** replies support headings, paragraphs, lists, blockquotes, emphasis, inline/fenced code, tables and horizontal rules. Raw HTML is rendered as text. Links allow only HTTP, HTTPS and mailto; credentials and unsafe schemes are rejected.
6. **First-class sources:** users can upload supported files (up to 8 MB), select existing owned document versions and generated artifacts, and attach up to five distinct resources. The limit is enforced in the frontend and request schema. Sources remain untrusted. Direct chat does not read attachment contents; explicit **Start task** is required for Agent processing.
7. **Responsive interaction:** the existing desktop context/history layout and tablet/phone drawers, theme controls, focus behavior and touch targets remain in place.

## Safety and architecture boundaries

- Saving or renaming a message does not dispatch an Agent run.
- Agent dispatch, cancellation and consequential external actions retain their existing explicit controls and approvals.
- Uploaded files and generated artifacts are owner-scoped, version/provenance bound and marked untrusted.
- No new provider, streaming protocol, image/audio endpoint, approval authority or alternate execution ledger was introduced by this slice.
- The existing native text-reply capability remains default-off. Migration `0063` and the backend-only provider configuration are still required before enabling it.
- No production environment variables, database, authentication configuration, aliases, deployment promotion or provider activation were changed.

## Verification evidence

### Latest main CI snapshot

Exact main SHA: `4db2843e0d43447af5065b04c13b82cf710a1084`.

[GitHub Actions run #41800917260](https://github.com/rumman52/Shuddho/actions/runs/41800917260) was still in progress when this report was prepared:

| Job | Observed state |
|---|---|
| `test-and-build` | Success |
| `Frontend tests and builds` | Success |
| `coworker` | In progress; mandatory PostgreSQL/Temporal/browser qualification had not finished |
| `governance-audit` | Failure: main branch protection is not confirmed |

The GitHub Vercel commit status for this revision is success. That status alone does not prove that the deployed UI, authentication, API routing or live provider behavior works.

### Earlier failures and corrections

PR #617's first CI run exposed two frontend test defects: the attachment renderer test called `toJSON` on the wrong renderer object, and filename sanitization removed Bengali combining marks. Its Python job also failed the existing multilingual quality fixture at 0.8333 against a required 1.0. The renderer assertion and Unicode filename handling were corrected in #618; #622 added server-side source-limit validation and further regression coverage.

The latest main run reports the frontend and `test-and-build` jobs successful. The full Coworker job and governance status must be read from the exact run before making a repository-wide green-CI claim.

### Browser and backend limits

The native chat handoff records synthetic-API Chromium checks across five desktop/tablet/phone viewports, including send/reply, composer visibility, history search, drawers, keyboard focus, dark mode and no page errors. This is not a real signed-in production session or a live DeepSeek provider test. The current main Coworker CI is still the required exact-revision integration evidence.

## Remaining gaps — not full Muse parity

This implementation completes the approved Muse-inspired conversation enhancement plan, not every Muse product capability. The following remain separate work:

- Token streaming and incremental assistant output.
- Voice input/output and audio generation.
- Image understanding and image generation.
- Direct assistant access to attached document contents; attachments currently feed explicit Agent tasks only.
- Native mobile, WhatsApp and operating-system integrations.
- Operated staging and production qualification for the wider Agent, browser/sandbox, automation and transaction capabilities.

These require separate provider/API contracts, persistence and recovery design, privacy/security review, evaluation coverage and explicit rollout approval. They must not be represented as UI-only features.

## Release disposition

| Qualification level | Status |
|---|---|
| Implemented | Yes — scoped code is merged to main |
| Repository-verified | Partial — latest frontend and test-and-build jobs passed; Coworker job was still running; governance audit failed |
| Staging-verified | No fresh staging evidence |
| Production-qualified | No |
| Activated | No — native replies remain default-off |

**Next exact action:** inspect the completion of [CI run #41800917260](https://github.com/rumman52/Shuddho/actions/runs/41800917260), then run and inspect the exact-head checks for this documentation handoff PR. Do not merge or deploy this handoff as a substitute for the outstanding governance and staging gates.
