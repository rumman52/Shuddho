# Shuddho AI-first production guide

This guide documents the production setup for running Shuddho as an AI-first writing assistant with local fallback.

## Recommended strategy

Set the backend to prefer AI review for deliberate checks while preserving local-only quick checks and fallback safety:

```env
SHUDDHO_LLM_ON_CHECK=auto
SHUDDHO_CHECK_STRATEGY=ai_first
SHUDDHO_LOCAL_ENGINE_MODE=fallback
SHUDDHO_LOCAL_CORRECTOR_ON_CHECK=false
```

Behavior:
- `includeLLM=true`: force deep AI review.
- `includeLLM=false`: local-only quick check.
- no explicit `includeLLM`: follows backend strategy (`ai_first` recommended).

## Backend (Render) environment

### OpenAI primary

```env
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=openai
OPENAI_API_KEY=your_real_openai_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_FALLBACK_MODELS=

SHUDDHO_CHECK_STRATEGY=ai_first
SHUDDHO_LOCAL_ENGINE_MODE=fallback
SHUDDHO_LOCAL_CORRECTOR_ON_CHECK=false
SHUDDHO_LLM_ON_CHECK=auto

SHUDDHO_LLM_TIMEOUT_SECONDS=45
SHUDDHO_LLM_MAX_TOKENS=3500
SHUDDHO_LLM_MAX_SUGGESTIONS=40
SHUDDHO_LLM_CHUNK_CHARS=1200
SHUDDHO_LLM_CONTEXT_CHARS=500
SHUDDHO_LLM_MAX_CHUNKS=8
SHUDDHO_MAX_AI_TEXT_CHARS=10000
SHUDDHO_LOG_RAW_TEXT=false

SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,http://localhost:5173,http://127.0.0.1:5173
SHUDDHO_ALLOW_VERCEL_PREVIEWS=false

SHUDDHO_CORRECTOR_ENABLED=auto
SHUDDHO_CORRECTOR_CHECKPOINT=artifacts/corrector/corrector-base
SHUDDHO_DETECTOR_ENABLED=auto
SHUDDHO_DETECTOR_CHECKPOINT=artifacts/detector/detector-base
```

### OpenRouter alternative

```env
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_real_openrouter_key
OPENROUTER_MODEL=openai/gpt-oss-120b:free
OPENROUTER_FALLBACK_MODELS=
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho
```

> Keep API keys on Render only. Never place `OPENAI_API_KEY` or `OPENROUTER_API_KEY` in Vercel frontend envs.

## Frontend (Vercel) environment

```env
VITE_API_BASE_URL=https://shuddho-api.onrender.com
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=false
```

Redeploy after env changes (Vite values are build-time).

## Deploy order

1. Deploy backend on Render (clear build cache + deploy).
2. Redeploy frontend on Vercel.
3. Clear browser override:

```js
localStorage.removeItem("shuddho-api-base-url");
location.reload();
```

## Smoke tests

### Health

```bash
curl -sS https://shuddho-api.onrender.com/health/deep
```

Check for:
- `llm.enabled=true`
- `llm.configured=true`
- `llm.check_strategy=ai_first`
- `llm.local_engine_mode=fallback`

### AI-first default

```bash
curl -sS -X POST https://shuddho-api.onrender.com/api/check \
  -H "Content-Type: application/json" \
  -d '{"text":"গতকাল আমি বাজারে যাযা। সেখানে সব মানুষেরা অনেক জিনিস কিনছিল।","language":"bn"}'
```

### Force AI

```bash
curl -sS -X POST https://shuddho-api.onrender.com/api/check \
  -H "Content-Type: application/json" \
  -d '{"text":"গতকাল আমি বাজারে যাযা। সেখানে সব মানুষেরা অনেক জিনিস কিনছিল।","language":"bn","options":{"includeLLM":true}}'
```

### Local-only

```bash
curl -sS -X POST https://shuddho-api.onrender.com/api/check \
  -H "Content-Type: application/json" \
  -d '{"text":"গতকাল আমি বাজারে যাযা। সেখানে সব মানুষেরা অনেক জিনিস কিনছিল।","language":"bn","options":{"includeLLM":false}}'
```

Confirm these fields in AI paths:
- `llm_requested`
- `llm_attempted`
- `llm_used`
- `llm_status`
- `ai_suggestion_count`
- `correctedText`
- `documentAssessment`
- `warnings`
- `diagnostics`

## Corrector checkpoint note

If `corrector_loaded` is false with `missing_checkpoint`, AI-first still works. To enable local corrector loading, ensure this file exists in deployment:

```text
artifacts/corrector/corrector-base/best_model.pt
```
