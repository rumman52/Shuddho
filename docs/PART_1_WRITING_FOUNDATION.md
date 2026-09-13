# Part 1: writing foundation and DeepSeek

Implementation branch: `codex/shuddho-part-1-writing-deepseek`.
Base inspected: `058afe171e1c14acd7d2e277e0a6506182d3f2e7`.

## What changed and why

| Problem | Change | Main files |
| --- | --- | --- |
| Runtime was tied to the competition Gemma provider | Add configurable DeepSeek review; retain explicit Gemma rollback | `services/api/shuddho_api/llm_provider.py`, `llm_deepseek.py`, `app.py` |
| Slow response bodies could keep the editor waiting after headers arrived | Keep browser timeout/cancellation through the JSON body; enforce a whole-response backend deadline and 1 MiB DeepSeek response limit | `apps/web-editor/src/lib/fetchWithTimeout.ts`, `llm_deepseek.py` |
| Malformed or truncated model output could be confused with no errors | Validate the envelope, completion reason, request ID, schema, and exact suggestions; return precise failure states | `llm_deepseek.py`, `ai_review_schema.py`, `app.py` |
| Empty-string replacement was treated as missing | Preserve deletion through normalization, validation, cards, and batch application | `suggestion_merge.py`, `suggestionAdapter.ts`, `suggestionTransaction.ts`, `SuggestionCard.tsx` |
| Provider full-text previews could contain unexplained or rejected edits | Rebuild previews from validated canonical suggestions | `suggestion_merge.py`, `app.py` |
| Document/profile IDs and writing preferences were dropped by request normalization | Forward IDs, revision, personal dictionary, and writing mode separately from fast/smart execution mode | `api.ts`, `app.py` |
| Editor called `/api/feedback` while FastAPI exposed `/feedback` | Support both routes through the same handler | `app.py` |
| Preferences were stored in one process and commonly shared the demo query ID | Require an explicit profile query, persist editor preferences in SQLite, and surface save errors | `api.ts`, `app.py`, `services/feedback/shuddho_feedback/store.py` |
| UI named Gemma even when a different provider was selected | Use general review status copy and provider-aware diagnostics | `App.tsx`, `api.ts` |
| Existing Python tests could not collect and dependency lock contradicted declared Google SDK version | Repair parametrization and regenerate `uv.lock` to satisfy the existing package declaration | `tests/test_llm_pipeline.py`, `uv.lock` |

## Scope and limits

- This is the writing foundation. No agent workflows, connected accounts, autonomous actions, or paid tiers were added.
- Local deterministic language coverage remains Bangla-focused. The new provider prompt/schema accepts multilingual review, including mixed text; this is not a completed 32-language accuracy evaluation.
- DeepSeek uses `deepseek-flash`, JSON object output, non-thinking mode, one bounded request, and no tools. It uses HTTPX already declared by the project; no OpenAI SDK is required for this adapter.
- The model key stays on the server. The adapter excludes raw provider error bodies, credentials, and reasoning from results. Detailed operational logs should still be reviewed before public release.
- There is no implicit retry or provider switch. The existing process-level circuit and local suggestions remain available on failure. Cross-replica admission control and durable retry scheduling are Part 2/3 work.
- A profile ID is **not authentication**. The new SQLite table prevents accidental profile collisions and survives a process restart on retained storage. It is not tenant security or managed cloud persistence. The older typed preference store still exists; reconcile both during the authenticated migration.
- AI review remains capped at the configured text limit, with truncation reported. This branch is not a long-document processing system.
- Model quality, live credentials, browser staging behavior, production latency, and deployment have not been verified with the real provider in this work.

## Run locally

From the repository root:

```bash
uv sync --frozen --group dev
npm ci
```

Create a local root `.env` using only the backend section below. The existing `.env.example` contains multiple service sections; do not copy all of it verbatim because the optional ML section has different settings.

```dotenv
SHUDDHO_LLM_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_API_KEY=<your backend key>
SHUDDHO_ENABLE_LLM=true
SHUDDHO_DEEPSEEK_TIMEOUT_SECONDS=15
SHUDDHO_LLM_MAX_COMPLETION_TOKENS=4096
SHUDDHO_MAX_AI_TEXT_CHARS=5000
SHUDDHO_DETECTOR_ENABLED=false
SHUDDHO_CORRECTOR_ENABLED=false
SHUDDHO_LOG_RAW_TEXT=false
```

Start the API:

```bash
uv run uvicorn services.api.shuddho_api.app:app --host 127.0.0.1 --port 8000
```

Start the editor in a second terminal, pointing directly to FastAPI:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 VITE_COMPETITION_DEMO_MODE=false npm run dev --workspace @shuddho/web-editor
```

For a no-cost local check, set `SHUDDHO_ENABLE_LLM=false`; rules and dictionaries remain usable. Health/debug routes do not spend inference tokens.

## API compatibility

`POST /api/check` retains existing fields and supports these editor values:

```json
{
  "text": "She go home.",
  "language": "en",
  "documentId": "draft-1",
  "revision": 3,
  "userId": "local-profile-1",
  "personalDictionary": ["Shuddho"],
  "writingMode": "formal",
  "options": {
    "includeLLM": true,
    "asyncLLM": false,
    "mode": "smart"
  }
}
```

`writingMode` controls the existing local writing analysis and is independent of `options.mode`. Personal dictionary and profile values are now delivered to that local path; all style preferences are not yet a full model-personalization system.

Both `GET` and `PUT /api/preferences` now require `?user_id=<profile>`. The server uses this query ID as the legacy storage key. Updated clients send it; older clients omitting it receive 422. Deploy the paired client/backend change to staging together. Both `/feedback` and `/api/feedback` remain supported.

## Automated verification

```bash
uv lock --check
uv run --frozen pytest -q
npm test
npm run build
```

Tests cover real local HTTP body timeouts and cancellation, mocked DeepSeek success/errors/truncation/oversized responses, exact request correlation, Unicode deletion, safe previews, API context, preference persistence, and local fallback. The provider tests use synthetic fixtures and a mock transport; they do not establish multilingual correction accuracy or real endpoint availability.

Verification on 13 September 2026: `uv lock --check` passed; Python reported **289 passed, 2 skipped** (the two optional PyTorch tests require the ML extra). `npm test` passed across all configured workspaces, including **93 editor tests**. `npm run build` passed across all configured workspaces, including editor type checking and Vite bundling. `git diff --check` passed.

## Staging release sequence

1. Select the provider explicitly in an access-restricted staging backend; configure its key there only.
2. Verify `/health`, `/health/deep`, and `/api/llm/debug`. Expect DeepSeek, `json_object`, and disabled thinking when selected.
3. Make an intentional live review with non-sensitive sample text. Check `llm_attempted`, `llm_used`, provider, status, suggestions, and corrected preview. Record model, latency, token use, and result quality.
4. Apply, dismiss, and apply all suggestions after edits, with repeated Bangla text and an emoji before the edited span. Confirm deletion works and stale suggestions do not alter changed text.
5. Verify profile settings after a backend restart; separately confirm the hosting volume survives redeployment. A restart test is not a persistence-volume test.
6. Test missing key, rate limiting, timeout, and invalid output in staging fixtures. Keep the user text editable and expose a useful status.
7. Complete the account/ownership boundary in Part 2 before publicly exposing the coworker to multiple users. Production rollout and observed capacity are separate gates.

Rollback: explicitly select `gemma` with its existing backend key/model settings, or disable hosted review temporarily. Preserve the editor's local path and saved user documents. This work did not change a production environment.
