# Real authenticated chat integration — 4 November 2026

## Contract

Replace the draft-only workspace with the existing authenticated conversation application. Connect chat to the explicitly configured supported model provider. Preserve owner isolation, durable reply claims, budget/lease admission, no automatic inference replay, backend feature/cohort checks, safe Markdown and separate approval-controlled actions.

Base: main `9ebd961c238339051188b2a758ba5df54d10fa1e`, including merged entry repair #631. This supersedes the draft-only UX direction in ENTRY_RECOVERY_2026-11-04.md.

## Actual deployment findings

- Production frontend had no Supabase browser auth variables. Those variables existed only on the older premium-workspaces preview branch. The production frontend rollout manifest had Coworker false.
- Production `/health/deep` identifies explicit `gemma` with a configured Google key. Existing chat admission/capability/adapter demanded DeepSeek regardless of this explicit configuration.
- Production `/api/v1/runtime-manifest` returns 404. The deployed Render service build command is `pip install -e .`; the authenticated Coworker dependency extra is not installed through that command.
- Render staging PostgreSQL `dpg-dav98hfpn0mc739mndvg-a` is suspended after its 31 October expiry. Staging API remains on 2 October source. It is not a valid persistence verification target.
- Existing Supabase project `bsmbvjenpvcyfjzwtuax` is healthy; read-only schema inventory found no application tables. Its presence is not proof that Coworker schema, DSN, storage or server authorization is configured.

## Implemented

- `/coworker` and provider OAuth callbacks always reach the real authentication application, independently of the landing-page preference flag. Removed the draft-only component and its route. Backend auth, capability, cohort and execution gates remain authoritative.
- Workspace directory always offers Open AI Coworker. Production no longer needs a frontend visibility flag just to reach sign-in.
- Signup and password recovery return to `/coworker`, where the auth callback can be consumed even if `/` remains the directory.
- Chat provider follows `SHUDDHO_LLM_PROVIDER`, default DeepSeek; explicit Gemma uses backend-only `GOOGLE_API_KEY` and `GEMMA_MODEL`. No cross-provider fallback. Existing editor provider-family validation governs chat admission/capability too; unsupported models/providers fail closed.
- Added Gemma SDK streaming with bounded context/output, deadline, one candidate, text-only parts, thought suppression, clean STOP requirement, explicit httpx transport and one HTTP attempt. The existing durable claim/persistence path handles streaming, replay and ownership checks.
- Stream connection failure preserves already displayed partial text and exposes saved-reply recovery without an endless busy state. Invalid provider output is still rejected and discarded.
- Corrected an existing deletion regression to check the repository's actual soft-delete/redaction contract: no text, reply, sources or resource links remain, and owner API access fails.

## Verification

- Web Editor suite: 204 passed, zero skips, including route behavior and partial-output recovery.
- Web Editor, standalone Coworker and standalone Editor TypeScript/Vite builds passed; existing Coworker chunk-size warning remains.
- Backend conversation replies/context/dispatch plus existing provider-policy checks: 92 passed, zero skips.
- An actual google-genai SDK request through HTTP mock transport exercises the owned SSE API, Bangla reply persistence, replay without a second request, history retrieval and foreign-owner rejection. This verifies application integration, not a live paid-provider response.
- Independent read-only review identified model-family and newer tool-part validation gaps; both were fixed with regressions. Independent re-review approved the corrected source with no remaining findings and independently passed 16 focused checks.
- Browser access to protected Vercel previews was denied through the connected-account fetch path; no real signed-in provider/UI run is claimed. Existing local Chromium downloads failed; no new screenshot claim.

## Configuration work and remaining release requirements

Public Supabase URL/publishable key were copied from the existing Rukh preview configuration to this integration branch's preview only. No service-role key or backend secret was requested or exposed. Production configuration, databases, provider flags and external-action permissions were not changed.

A real deployed chat release requires these concrete dependencies:

1. An accessible durable PostgreSQL DSN in Render `SHUDDHO_COWORKER_DATABASE_URL`, with current Coworker migrations applied using `python -m services.coworker.migrate`. Do not substitute ephemeral SQLite or recreate/delete the expired database to conceal missing persistence.
2. Install Coworker dependencies in the target service, e.g. `pip install -e '.[coworker]'`, before enabling its mount. Preserve existing writing runtime settings.
3. Configure the existing auth issuer/audience and private storage required by Settings. Use the existing Supabase project only when its intended ownership and server credentials are confirmed. Credentials must be entered through the hosting secret controls.
4. Enable only normal Coworker conversations/replies for the authorized cohort: SHUDDHO_COWORKER_ENABLED, SHUDDHO_CONVERSATIONS_ENABLED, SHUDDHO_CONVERSATION_REPLIES_ENABLED. Preserve all independent task/browser/code/transaction/action gates. Explicit provider configuration must match available credentials.
5. Configure public browser auth for the intended release environment and authorized callback origins, then deploy the matching frontend/backend revision.
6. Verify sign-in, actual provider response, refresh/history, cross-account denial and mobile composer on the deployed URL. Until then, production chat is not live verified.

The available Render connector can merge environment values but does not expose an existing database password or a safe way to derive one. No database password, service-role key, DSN or storage secret was invented, reset or printed. Missing infrastructure is not repaired by the source integration tests.

## Rollback

Revert this source change or restore the previous frontend/backend deployments. Existing schema is additive and unchanged by this patch. Remove only the new branch-specific public auth variables if abandoning the preview. No destructive schema rollback or user-data deletion is needed.
