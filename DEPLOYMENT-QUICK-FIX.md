# Shuddho Deployment Quick Fix

Use this checklist to repair the production “AI review is temporarily unavailable” loop without exposing secrets.

## Render backend

### Build command

```bash
uv sync --frozen || uv sync
```

If Render does not have `uv`, use:

```bash
python -m pip install -e '.[dev]'
```

### Start command

```bash
python -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port $PORT
```

The service must bind to Render's `$PORT`.

### Environment variables

Set these only on Render/backend:

```bash
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=gemini
GEMINI_API_KEY=<Google AI Studio secret>
GEMINI_MODEL=gemini-2.5-flash
SHUDDHO_LLM_FALLBACK_PROVIDER=openrouter
OPENROUTER_API_KEY=<OpenRouter secret>
OPENROUTER_MODEL=openrouter/free
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho
SHUDDHO_LLM_ON_CHECK=manual
SHUDDHO_LLM_TOTAL_TIMEOUT_SECONDS=50
SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45
SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS=50
SHUDDHO_GEMINI_TIMEOUT_SECONDS=30
SHUDDHO_OPENROUTER_TIMEOUT_SECONDS=18
SHUDDHO_MAX_AI_TEXT_CHARS=5000
SHUDDHO_LLM_MAX_CANDIDATES=8
SHUDDHO_LLM_MAX_CANDIDATE_CHARS=2200
SHUDDHO_LLM_MAX_COMPLETION_TOKENS=1400
SHUDDHO_LLM_CACHE_TTL_SECONDS=86400
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,http://localhost:5173,http://127.0.0.1:5173
SHUDDHO_LOG_RAW_TEXT=false
```

`GEMINI_API_KEY` is canonical. `GOOGLE_API_KEY` is accepted only as a legacy alias. If both are set, Shuddho uses `GEMINI_API_KEY` and reports a safe warning.

### Delete from Render if present

```bash
GOOGLE_API_KEY=<stale duplicate>
GEMINI_MODEL=gemini-3.5-flash
OPENROUTER_MODEL=openai/gpt-oss-20b:free
SHUDDHO_ALLOWED_ORIGINS=https://*.vercel.app
```

Do not use wildcard Vercel origins. Add exact preview origins only when needed.

## Vercel frontend

### Project settings

- Framework preset: Vite
- Root directory: `apps/web-editor`
- Install command: `npm install`
- Build command: `npm run build`
- Output directory: `dist`

### Environment variables

Set these only on Vercel/frontend:

```bash
VITE_API_BASE_URL=https://shuddho-api.onrender.com
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=false
VITE_COMPETITION_DEMO_MODE=false
```

### Delete from Vercel if present

```bash
GEMINI_API_KEY
GOOGLE_API_KEY
OPENROUTER_API_KEY
OPENAI_API_KEY
GEMINI_MODEL
OPENROUTER_MODEL
OPENAI_MODEL
SHUDDHO_LLM_PROVIDER
SHUDDHO_LLM_FALLBACK_PROVIDER
```

Never place backend API keys in Vercel. Any `VITE_` variable is browser-visible.

## Redeployment order

1. Update Render environment variables.
2. Redeploy Render backend.
3. Wait for Render health to pass.
4. Update Vercel environment variables.
5. Redeploy Vercel frontend.
6. Hard-refresh the browser.

## Health-check commands

```bash
curl -i https://shuddho-api.onrender.com/health
curl -s https://shuddho-api.onrender.com/api/llm/debug | python -m json.tool
curl -i -X OPTIONS https://shuddho-api.onrender.com/api/check \
  -H 'Origin: https://shuddho-web-editor.vercel.app' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

Expected health: HTTP 200 with `ok: true`. Expected LLM debug: `enabled: true`, `provider: gemini`, `model: gemini-2.5-flash`, and `api_key_present: true` without revealing the key.

## AI Review verification

Use the frontend Deep AI Review button with Bangla text. Expected successful `/api/check` response includes:

```json
{
  "llm_requested": true,
  "llm_attempted": true,
  "llm_used": true,
  "llm_provider": "gemini",
  "llm_status": "completed",
  "suggestions": [],
  "warnings": [],
  "provider_attempts": []
}
```

If Gemini fails and OpenRouter succeeds, expect `llm_provider: "openrouter"`, `llm_status: "completed"`, and warnings containing `primary_provider_failed:gemini` and `fallback_provider_used:openrouter`.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| 401 | Invalid provider key | Rotate `GEMINI_API_KEY` or `OPENROUTER_API_KEY` on Render only. |
| 403 | Key forbidden, project restriction, or API not enabled | Verify Google AI Studio key/project permissions; keep the key server-side. |
| 404 | Unsupported model | Set `GEMINI_MODEL=gemini-2.5-flash`; verify `OPENROUTER_MODEL` in OpenRouter catalog. |
| 429 | Quota or rate limit | Wait, enable billing/credits, or rely on fallback provider. |
| Timeout | Render cold start or slow provider | Retry once; keep bounded timeout variables above. |
| CORS | Origin missing from backend | Add exact Vercel origin to `SHUDDHO_ALLOWED_ORIGINS`, redeploy Render. |
| Malformed provider response | Model did not return valid schema | Backend returns `invalid_json` or `invalid_schema`; local suggestions remain visible. |
