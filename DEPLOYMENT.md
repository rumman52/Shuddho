# Shuddho competition deployment

Shuddho's only generative runtime is the pretrained instruction-tuned **Gemma 4** model `gemma-4-26b-a4b-it`. The Google Gen AI SDK and Gemini API endpoint are transport infrastructure; the application does not call a `gemini-*` model and does not claim to have trained or fine-tuned Gemma. Deterministic Bangla rules, spelling, dictionaries, punctuation, spacing, and regex checks remain available when hosted inference is unavailable.

## Render: native Python (recommended)

Configure the existing service in the Render dashboard; this repository does not use a Blueprint.

- Runtime: **Python**
- Branch: **main**
- Root Directory: **blank / repository root**
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

The repository includes a Vercel rewrite from `/backend/*` to the Render API.
This same-origin proxy is the production default, prevents browser CORS failures,
and keeps working when `VITE_API_BASE_URL` was omitted at build time. No frontend
environment variable is required for the standard deployment.

For a custom backend deployment, set only these public frontend values:

```dotenv
VITE_API_BASE_URL=https://your-custom-api.example.com
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=false
VITE_COMPETITION_DEMO_MODE=false
```

When `VITE_API_BASE_URL` is set, it intentionally overrides the same-origin proxy,
so the custom backend must allow the exact production frontend origin through
`SHUDDHO_ALLOWED_ORIGINS`. Never add `GOOGLE_API_KEY`, `GEMMA_MODEL`, or
`SHUDDHO_LLM_PROVIDER` to Vercel, frontend source, GitHub, logs, or screenshots.
Broad `https://*.vercel.app` CORS values are invalid. Localhost origins are built
in for local development only.

## Health and verification

`/health` is liveness-only. `/health/deep` reports stored local component/configuration state, and `/api/llm/debug` reports safe booleans/status; neither endpoint calls Gemma. Deep-review failures retain deterministic suggestions and return warnings and diagnostics instead of claiming Gemma was used.

After changing Render settings, choose **Clear build cache & deploy**, wait for
`/health` HTTP 200, then redeploy Vercel and test in an incognito browser. The
standard frontend health URL is `/backend/health`; Vercel forwards it to Render's
`/health` endpoint.

The canonical public competition demo is
`https://shuddho-web-editor.vercel.app`; a protected branch preview is not the
public demo. Remove the stale production dashboard value
`VITE_API_BASE_URL=https://shuddho-api.onrender.com`. Prefer no value; if Vercel
requires one, use only `VITE_API_BASE_URL=/backend`.
