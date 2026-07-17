# Shuddho

Shuddho is an original Bangla grammar, spelling, rewriting, and writing-assistant app. The repaired monorepo now uses a hybrid architecture: clients call a common TypeScript API gateway, and the gateway routes Bangla linguistic work to the existing Python FastAPI Bangla engine with a conservative Bangla-only fallback.

## Folder structure

```text
apps/api/                 TypeScript API gateway, providers, stores, WebSocket sync
apps/web/                 Experimental Next editor MVP
apps/web-editor/          Existing Vite Bangla editor, now gateway-aware
apps/chrome-extension/    Existing extension, now gateway-aware
packages/shared/          Canonical contracts, adapters, Unicode/span utilities
packages/nlp/             Bangla fallback provider abstraction
services/api/             Existing Python FastAPI Bangla API
services/analysis/        Existing Bangla analysis pipeline
services/rules/           Existing Bangla rule engine
services/spell/           Existing Bangla spell engine
shared/schemas/           Legacy and canonical Python/TS schemas
infra/                    Docker Compose with Postgres and Redis
```

## Install

```bash
npm install --include=optional
```

## Run locally

Start Python Bangla API:

```bash
python -m uvicorn services.api.shuddho_api.app:app --host 127.0.0.1 --port 8000 --reload
```

Start TypeScript gateway:

```bash
npm run dev --workspace @shuddho/api
```

Start Vite web editor:

```bash
npm run dev --workspace @shuddho/web-editor
```

Optional Next app:

```bash
npm run dev --workspace @shuddho/web
```

## Test

```bash
npm test --workspace @shuddho/shared
npm test --workspace @shuddho/api
.venv/bin/python -m pytest -m "not slow"
```


## LLM provider configuration

Shuddho always runs the local spelling/rule/dictionary engine first. When LLM review is enabled, the backend sends the full text, sentence spans, local suggestions, and candidate incorrect sentences to the configured provider, validates exact spans, then merges AI and local suggestions. If the provider is unavailable, times out, or returns invalid JSON, local suggestions still return with a non-blocking diagnostic warning.

Use OpenRouter for OpenRouter model IDs such as `openai/gpt-oss-120b:free`:

```dotenv
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-oss-20b:free
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho
SHUDDHO_LLM_ON_CHECK=manual
SHUDDHO_LLM_TOTAL_TIMEOUT_SECONDS=50
SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45
SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS=50
```

Use the official OpenAI provider only with official OpenAI model IDs:

```dotenv
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

Operational safeguards:

- Keep `OPENROUTER_API_KEY` and `OPENAI_API_KEY` only in backend environment variables.
- Never use `VITE_*` variables for private provider keys because Vite exposes them to browser code.
- Free OpenRouter models can be slower, unavailable, or rate-limited; Shuddho's local fallback must always remain enabled.
- `SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45` gives free OpenRouter reasoning models enough time for manual Deep AI Review, while `SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS=50` allows queued background reviews more time.
- Set `SHUDDHO_MAX_AI_TEXT_CHARS=5000` and `SHUDDHO_LLM_CACHE_TTL_SECONDS=86400` to bound request size and avoid repeated unchanged reviews.


### Gemini primary with OpenRouter fallback

Render backend environment variables for production Deep AI Review:

```bash
SHUDDHO_ENABLE_LLM=true

# Primary provider
SHUDDHO_LLM_PROVIDER=gemini
GEMINI_API_KEY=<render-secret>
GEMINI_MODEL=gemini-3.5-flash

# Automatic fallback
SHUDDHO_LLM_FALLBACK_PROVIDER=openrouter
OPENROUTER_API_KEY=<existing-render-secret>
OPENROUTER_MODEL=openai/gpt-oss-20b:free
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho

SHUDDHO_LLM_ON_CHECK=manual
SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45
SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS=50
```

Gemini and OpenRouter keys belong only in Render or another private backend runtime. Never add `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or `OPENROUTER_API_KEY` to Vercel; Vercel should contain only public `VITE_*` values. OpenRouter remains configured even while Gemini is primary, and `SHUDDHO_LLM_PROVIDER` / `SHUDDHO_LLM_FALLBACK_PROVIDER` can be reversed without code changes. Use a current Gemini auth key from Google AI Studio. Do not commit real secrets to `.env.example`, README files, `render.yaml`, tests, or source files.

OpenRouter model availability changes. The old `openai/gpt-oss-120b:free` value is not an active default; set `OPENROUTER_MODEL` explicitly after checking the current OpenRouter catalog. The OpenRouter catalog lists current free/router choices such as `openrouter/free`, which routes to available free models, but production deployments should choose and monitor a model appropriate for Bangla writing review.

## Vercel deployment (apps/web-editor)

Use these Vercel project settings for the Vite web editor deployment:

- Framework Preset: Vite
- Root Directory: repo root
- Install Command: `npm install --include=optional`
- Build Command: `npm run build:web-editor`
- Output Directory: `apps/web-editor/dist`

Keep optional dependencies enabled so Vite/esbuild can install the native binary for the Vercel Linux build environment.
Do not set npm options such as `omit=optional`, `optional=false`, or `ignore-scripts=true` for this deployment.



### Required production environment split

Vercel frontend should contain only browser-safe Vite variables:

```dotenv
VITE_API_BASE_URL=https://YOUR_RENDER_BACKEND_PUBLIC_URL
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=false
```

Never put provider secrets or provider model configuration in Vercel frontend variables: `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `GEMINI_MODEL`, `OPENROUTER_MODEL`, `OPENAI_MODEL`, or `SHUDDHO_LLM_PROVIDER`.

Render/backend should contain the private OpenRouter configuration when using `openai/gpt-oss-120b:free`:

```dotenv
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<secret>
OPENROUTER_MODEL=openai/gpt-oss-20b:free
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho
SHUDDHO_LLM_ON_CHECK=manual
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,https://shuddho-web-editor-luqrebd0p-rumman52s-projects.vercel.app,http://localhost:5173,http://127.0.0.1:5173
SHUDDHO_ALLOW_VERCEL_PREVIEWS=false
SHUDDHO_LLM_TOTAL_TIMEOUT_SECONDS=50
SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45
SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS=50
SHUDDHO_MAX_AI_TEXT_CHARS=5000
SHUDDHO_LLM_MAX_CANDIDATES=8
SHUDDHO_LLM_MAX_CANDIDATE_CHARS=2200
SHUDDHO_LLM_MAX_COMPLETION_TOKENS=1400
```


### Competition Demo · Local Engine (Vercel only)

For a competition/demo deployment that must run the prepared Bangla examples fully offline in the browser, set this public build-time Vite variable in the Vercel frontend project:

```dotenv
VITE_COMPETITION_DEMO_MODE=true
```

Use the exact lowercase string `true`. Configure it in Vercel, not Render, because it controls the Vite frontend bundle. Redeploy Vercel after changing it; Vite variables are baked in at build time. If you use both Vercel Production and Preview environments, set the variable separately in each environment. Do not put Gemini, OpenRouter, OpenAI, or any other secret provider keys in Vercel; keep the existing backend provider configuration on Render or another private backend runtime.

## Render FastAPI backend

The Render backend can deploy without the optional sentence-level corrector checkpoint. Use `auto` so the backend loads a checkpoint only when the files are actually present:

```dotenv
SHUDDHO_CORRECTOR_ENABLED=auto
SHUDDHO_CORRECTOR_CHECKPOINT=artifacts/corrector/corrector-base
SHUDDHO_DETECTOR_ENABLED=auto
SHUDDHO_DETECTOR_CHECKPOINT=artifacts/detector/detector-base
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app
SHUDDHO_LOG_RAW_TEXT=false
```

If the corrector checkpoint is missing, `/health/deep` reports `corrector.status = missing_checkpoint`, analysis runs in `backend_without_corrector` mode when the detector is ready, and Shuddho stays online with rules + spelling suggestions. After merging a deployment fix, redeploy Render with **Manual Deploy → Clear build cache & deploy**.

### Corrector checkpoint deployment

Option A: run without corrector:

- No `.pt` files are needed.
- The app uses rules + spelling, and the detector if a valid detector artifact is available.
- Render deploy works because there are no broken Git LFS pointers to smudge during clone.

Option B: use Git LFS manually from a developer machine that has the real checkpoint files:

```bash
git lfs install
git lfs track "*.pt"
git add .gitattributes
git add artifacts/corrector/corrector-base/best_model.pt
git add artifacts/corrector/corrector-base/last_model.pt
git commit -m "Add corrector model checkpoints"
git push origin main
git lfs push --all origin main
```

Then redeploy Render with **Manual Deploy → Clear build cache & deploy**. Do not skip `git lfs push --all origin main`; otherwise Render may clone a pointer whose object is missing from GitHub LFS storage.

Option C: use external storage, recommended for production:

- Hugging Face Hub
- AWS S3
- Cloudflare R2
- GitHub Releases
- Google Cloud Storage

Store the model externally and download it during build or startup. The backend supports an optional `SHUDDHO_CORRECTOR_MODEL_URL` that downloads `best_model.pt` into `artifacts/corrector/corrector-base/best_model.pt` if that file is missing; metadata must still exist at the checkpoint path.

Train the sentence-level Bangla corrector before deploying full contextual correction mode:

```bash
python -m ml.corrector.train --config ml/training/configs/corrector.base.json
```

This produces `artifacts/corrector/corrector-base/metadata.json`, `best_model.pt`, `last_model.pt`, and `metrics.json`. Do not commit generated binary checkpoint files from automation. See [deployment](docs/DEPLOYMENT.md) and [corrector training](docs/train-corrector.md).

## Architecture docs

- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Bangla NLP](docs/BANGLA_NLP.md)
- [Local development](docs/LOCAL_DEV.md)
- [Security and privacy](docs/SECURITY_PRIVACY.md)
- [Roadmap](docs/ROADMAP.md)

### Alternate Vercel root directory

If Vercel Root Directory is set to `apps/web-editor` instead of the repository root, use:

- Framework Preset: `Vite`
- Install Command: `npm install --include=optional`
- Build Command: `npm run build`
- Output Directory: `dist`

### Deployed Vercel frontend with a local backend

The deployed frontend must not call `http://localhost:4000` or `http://localhost:8000`. In a browser, `localhost` means the visitor's machine, not the developer computer running Shuddho. For local-backend testing, expose only the TypeScript gateway (`localhost:4000`) through a public HTTPS tunnel and set this Vercel environment variable:

```bash
VITE_API_BASE_URL=https://your-public-backend-tunnel-url
```

See [Run the Shuddho backend locally behind a Vercel frontend](docs/LOCAL_BACKEND_WITH_VERCEL.md) for ngrok, Cloudflare Tunnel, CORS, and manual `curl` test commands.

## Canonical deployment and model-readiness notes

Canonical production path: Vite web editor (`apps/web-editor`) calls the Python FastAPI backend (`services/api/shuddho_api`), which returns local rules/spelling suggestions and uses Gemini as primary Deep AI Review with OpenRouter as an explicitly configured fallback.

Secrets belong only in Render/backend environment variables. Never configure `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, or `OPENAI_API_KEY` in Vercel or any `VITE_*` variable. Vercel should use only `VITE_API_BASE_URL`, `VITE_USE_GATEWAY`, and `VITE_ENABLE_LOCAL_FALLBACK`.

If OpenRouter returns HTTP 401 in Render, rotate/create the OpenRouter key, update only Render `OPENROUTER_API_KEY`, verify `OPENROUTER_MODEL` against the current OpenRouter model catalog, and redeploy Render. Do not paste secrets into logs, source files, issues, screenshots, or status reports.

Current local ML artifacts are not production-quality sentence correction. Missing corrector checkpoints are health warnings; low-quality detector/corrector metrics must remain visible in diagnostics and must not supersede deterministic rules. Production promotion requires a representative Bangla dataset, clean train/validation/test splits, coverage across spelling/grammar/punctuation/fluency/dialect/formal writing, measured precision/recall/F1 and correction accuracy, and checkpoint integrity validation.
