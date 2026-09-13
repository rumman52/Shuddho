# Shuddho deployment

The new writing runtime defaults to **DeepSeek**. This supersedes the earlier competition-only Gemma default; explicit Gemma configuration remains available below. Deterministic Bangla checks continue when hosted inference is unavailable. See [Part 1 verification](docs/PART_1_WRITING_FOUNDATION.md) before releasing this branch.

This change has not been deployed. Use an access-restricted staging service first. The legacy profile ID and in-memory job APIs are not an authenticated multi-user SaaS boundary; Part 2 adds that boundary before a public coworker launch.

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
DEEPSEEK_API_KEY=<backend secret>
DEEPSEEK_MODEL=deepseek-flash
SHUDDHO_LLM_PROVIDER=deepseek
SHUDDHO_ENABLE_LLM=true
SHUDDHO_DEEPSEEK_TIMEOUT_SECONDS=15
SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45
SHUDDHO_LLM_TOTAL_TIMEOUT_SECONDS=50
SHUDDHO_LLM_MAX_COMPLETION_TOKENS=4096
SHUDDHO_MAX_AI_TEXT_CHARS=5000
SHUDDHO_DETECTOR_ENABLED=false
SHUDDHO_CORRECTOR_ENABLED=false
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app
SHUDDHO_LOG_RAW_TEXT=false
```

The disabled ML settings do not disable local analysis or DeepSeek review. Missing credentials are reported as `missing_key` without breaking liveness. There is no automatic cross-provider fallback: a failed DeepSeek call preserves available local suggestions and explains its status.

The DeepSeek adapter uses a whole-response deadline, JSON validation, and a bounded response body. Its 15-second budget is an initial setting to measure in staging, not a latency promise. The 5,000-character input cap applies to AI review; truncation is reported. Long document processing belongs in the Part 2 worker path.

For rollback to the existing Gemma runtime, explicitly select:

```dotenv
SHUDDHO_LLM_PROVIDER=gemma
GOOGLE_API_KEY=<backend secret>
GEMMA_MODEL=gemma-4-26b-a4b-it
SHUDDHO_GEMMA_RESPONSE_MODE=function_call
SHUDDHO_GEMMA_THINKING_LEVEL=minimal
SHUDDHO_GEMMA_TIMEOUT_SECONDS=40
```

Before upgrading an existing Google-only deployment, set `SHUDDHO_LLM_PROVIDER=gemma` if it should keep that runtime. An unset provider now selects DeepSeek. Provider selection is independent of deploying the editor fixes.

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
`SHUDDHO_ALLOWED_ORIGINS`. Provider credentials and model selection belong only
in the backend service, never in Vercel's browser build or source control.
Broad `https://*.vercel.app` CORS values are invalid. Localhost origins are built
in for local development only.

## Health and verification

`/health` is liveness-only. `/health/deep` reports stored local component/configuration state, and `/api/llm/debug` reports safe booleans/status; neither endpoint calls a provider. Deep-review failures retain local suggestions and report warnings and diagnostics. A configured key in health is not proof of valid credentials or successful inference.

Deploy the frontend and backend changes together in staging: preferences now require the explicit `user_id` query parameter, which the updated editor supplies. SQLite preferences survive process restarts only when their database file survives; the current default path is `data/shuddho_feedback.db`. Ephemeral filesystem redeploys can erase that file. Managed durable account storage is Part 2 work.

After changing Render settings, choose **Clear build cache & deploy**, wait for
`/health` HTTP 200, then redeploy Vercel and test in an incognito browser. The
standard frontend health URL is `/backend/health`; Vercel forwards it to Render's
`/health` endpoint.

The canonical public competition demo is
`https://shuddho-web-editor.vercel.app`; a protected branch preview is not the
public demo. Remove the stale production dashboard value
`VITE_API_BASE_URL=https://shuddho-api.onrender.com`. Prefer no value; if Vercel
requires one, use only `VITE_API_BASE_URL=/backend`.
