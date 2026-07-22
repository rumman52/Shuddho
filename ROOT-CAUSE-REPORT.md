# Shuddho Root-Cause Report

## Confirmed root causes from repository audit

1. **Stale model names in deployment examples.** Several deployment examples referenced `gemini-3.5-flash`, which is not the stable documented default used by the backend. Official Google AI docs list `gemini-2.5-flash` as a supported Flash model, and the backend default is `gemini-2.5-flash`.
2. **OpenRouter examples relied on a brittle free model alias.** Docs and examples referenced `openai/gpt-oss-20b:free`; OpenRouter model availability changes. The safer routing example is `openrouter/free`, while production should choose a monitored model from the catalog.
3. **Gemini key precedence was ambiguous in tests/docs.** The backend already treats `GEMINI_API_KEY` as canonical and `GOOGLE_API_KEY` as a legacy fallback. Tests still expected the stale `GOOGLE_API_KEY` value to win, which would keep a rotated Gemini key from being used.
4. **Asynchronous LLM job terminal statuses missed `content_filter`.** A provider safety/content-filter response could be coerced to a generic failed state instead of preserving the specific terminal status.
5. **Backend Python test environment was incomplete in this container.** The local virtualenv lacks `httpx`, and network package installation was blocked by the environment proxy, so FastAPI TestClient-based tests could not run here. Frontend tests and builds passed.
6. **Live read-only verification was blocked by this execution environment.** `curl` to the Render URL failed with a CONNECT tunnel 403 before reaching the service, so live `/health` could not be verified from here.

## Evidence collected

- Repository search found AI failure status handling across `services/api/shuddho_api/app.py`, `llm_gemini.py`, `llm_openrouter.py`, and frontend status mapping in `apps/web-editor/src/lib/api.ts` and `apps/web-editor/src/lib/llmStatus.ts`.
- Frontend tests verify production base URL handling, localhost rejection on deployed hosts, polling status merge behavior, duplicate/stale request protection, local-suggestion preservation after AI failure, and fallback success messaging.
- Provider tests mock OpenRouter and Gemini success/failure cases without paid API calls.
- Official documentation checked on 2026-07-22: Google AI Gemini model docs list `gemini-2.5-flash`; OpenRouter docs use `/api/v1/chat/completions` with Bearer auth and provide model catalog APIs.

## Fixes made

- Updated deployment examples to use `GEMINI_MODEL=gemini-2.5-flash`.
- Updated OpenRouter examples to use `OPENROUTER_MODEL=openrouter/free` where a generic fallback routing example is needed.
- Updated Gemini config tests to assert `GEMINI_API_KEY` precedence and default `gemini-2.5-flash` behavior.
- Added `content_filter` to backend LLM terminal statuses so asynchronous jobs preserve that terminal category.
- Made the async job safety-net failure payload use the configured provider/model instead of hard-coding Gemini.

## Remaining external blocker

If production still returns `auth_or_forbidden`, code cannot repair that secret. Rotate or replace the backend-only provider key in Render, verify the selected model is enabled for that account/project, and redeploy Render before redeploying Vercel.
