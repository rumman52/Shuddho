# Shuddho competition deployment

Shuddho's only generative runtime is the pretrained instruction-tuned **Gemma 4** model `gemma-4-26b-a4b-it`. The Google Gen AI SDK and Gemini API endpoint are transport infrastructure; the application does not call a `gemini-*` model and does not claim to have trained or fine-tuned Gemma. Deterministic Bangla rules, spelling, dictionaries, punctuation, spacing, and regex checks remain available when hosted inference is unavailable.

## Render: native Python (recommended)

Configure the existing service in the Render dashboard; this repository does not use a Blueprint.

- Runtime: **Python**
- Build command: `python -m pip install --upgrade pip && python -m pip install --no-cache-dir .`
- Start command: `python -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port "$PORT"`
- Health Check Path: `/health`

Render supplies `$PORT`; do not hard-code it. The base package intentionally excludes PyTorch, CUDA, SentencePiece, and optional ML engines.

Set these backend-only values:

```dotenv
GOOGLE_API_KEY=<real secret>
GEMMA_MODEL=gemma-4-26b-a4b-it
SHUDDHO_LLM_PROVIDER=gemma
SHUDDHO_ENABLE_LLM=true
SHUDDHO_DETECTOR_ENABLED=false
SHUDDHO_CORRECTOR_ENABLED=false
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app
SHUDDHO_LOG_RAW_TEXT=false
```

The disabled ML settings do not disable local deterministic analysis or Gemma review. Do not configure old provider/model/fallback variables or local ML model URLs on this service. Missing `GOOGLE_API_KEY` is reported as `missing_key` without breaking liveness.

## Render: Docker alternative

A plain `docker build .` and `docker build --target production .` both select the lightweight production stage. The optional CPU ML image is available only with `docker build --target ml-cpu .`; it is for offline/local work, not the competition Render service.

## Vercel

- Root Directory: `apps/web-editor`
- Framework: Vite
- Install Command: `npm install`
- Build Command: `npm run build`
- Output Directory: `dist`

The checked-in Vercel rewrite proxies `/backend/*` to Render, so the standard
deployment needs no frontend environment variables and avoids browser CORS.

Only when using a custom backend, set these public frontend values:

```dotenv
VITE_API_BASE_URL=https://your-custom-api.example.com
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=false
VITE_COMPETITION_DEMO_MODE=false
```

When `VITE_API_BASE_URL` is set it overrides the proxy, and the custom backend
must allow the exact frontend origin. Never add `GOOGLE_API_KEY`, `GEMMA_MODEL`,
or `SHUDDHO_LLM_PROVIDER` to Vercel, frontend source, GitHub, logs, or screenshots.
CORS does not accept broad `https://*.vercel.app` values.

## Health and verification

`/health` is liveness-only. `/health/deep` reports stored local component/configuration state, and `/api/llm/debug` reports safe booleans/status; neither endpoint calls Gemma. Deep-review failures retain deterministic suggestions and return warnings and diagnostics instead of claiming Gemma was used.

After changing Render settings, choose **Clear build cache & deploy**, wait for
`/health` HTTP 200, then redeploy Vercel and test `/backend/health` in an incognito
browser.
