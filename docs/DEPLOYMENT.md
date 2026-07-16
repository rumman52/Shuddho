# Shuddho deployment

## Vercel web editor

The web editor is a static Vite SPA in `apps/web-editor`. Deploy it from the repository root so Vercel uses the checked-in `vercel.json` rewrite and output settings. The editor must render before any backend, Render, OpenAI, or OpenRouter call succeeds. If the backend is down or `VITE_API_BASE_URL` is missing, the page still loads and shows a non-blocking setup or backend-unavailable banner.

### Supported Vercel project settings

Case A — Vercel Root Directory is the repository root:

- Framework Preset: Vite
- Root Directory: repository root
- Install Command: `npm install`
- Build Command: `npm run build:web-editor`
- Output Directory: `apps/web-editor/dist`

Case B — Vercel Root Directory is `apps/web-editor`:

- Framework Preset: Vite
- Root Directory: `apps/web-editor`
- Install Command: `npm install`
- Build Command: `npm run build`
- Output Directory: `dist`

The root `vercel.json` should remain aligned with those settings and includes this SPA fallback so deep links return `index.html` instead of 404s:

```json
{
  "version": 2,
  "buildCommand": "npm run build:web-editor",
  "outputDirectory": "apps/web-editor/dist",
  "installCommand": "npm install",
  "rewrites": [
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ]
}
```

### Frontend Vercel environment variables

Set these on the Vercel frontend project in **Production, Preview, and Development**:

```dotenv
VITE_API_BASE_URL=https://shuddho-api.onrender.com
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=false
```

`VITE_API_BASE_URL` must be the Shuddho backend origin, such as `https://shuddho-api.onrender.com`. It must not be an OpenAI or OpenRouter URL. If it is missing, the deployed frontend intentionally disables server AI review, renders the editor, and shows: “API URL is not configured. Set VITE_API_BASE_URL in Vercel.”

Security note: do **not** add `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, or other private backend secrets to Vercel frontend variables. Browser code must only use public `VITE_*` values and must send AI review requests through the backend.

### Vercel preview deployments and CORS

Render only allows browser origins listed in `SHUDDHO_ALLOWED_ORIGINS` plus the safe local/extension regex built into the FastAPI app. If you test a Vercel preview URL, add that exact preview origin to `SHUDDHO_ALLOWED_ORIGINS`, for example:

```dotenv
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,https://your-preview-url.vercel.app,http://localhost:5173
```

Do not use a blanket wildcard in production. The backend uses credentials-capable CORS, so `*` is ignored by origin parsing. If preview URLs must be dynamic, implement safe Vercel preview CORS handling that restricts origins to trusted Shuddho preview hostnames.


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
OPENROUTER_MODEL=<currently-valid-openrouter-model>
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho

SHUDDHO_LLM_ON_CHECK=manual
SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45
SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS=60
```

Gemini and OpenRouter keys belong only in Render or another private backend runtime. Never add `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or `OPENROUTER_API_KEY` to Vercel; Vercel should contain only public `VITE_*` values. OpenRouter remains configured even while Gemini is primary, and `SHUDDHO_LLM_PROVIDER` / `SHUDDHO_LLM_FALLBACK_PROVIDER` can be reversed without code changes. Use a current Gemini auth key from Google AI Studio. Do not commit real secrets to `.env.example`, README files, `render.yaml`, tests, or source files.

OpenRouter model availability changes. The old `openai/gpt-oss-120b:free` value is not an active default; set `OPENROUTER_MODEL` explicitly after checking the current OpenRouter catalog. The OpenRouter catalog lists current free/router choices such as `openrouter/free`, which routes to available free models, but production deployments should choose and monitor a model appropriate for Bangla writing review.

## Render FastAPI backend

Render start command:

```bash
python -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port $PORT
```

Set these private Render environment variables for `https://shuddho-api.onrender.com`:

```dotenv
SHUDDHO_CORRECTOR_ENABLED=auto
SHUDDHO_CORRECTOR_CHECKPOINT=artifacts/corrector/corrector-base
SHUDDHO_DETECTOR_ENABLED=auto
SHUDDHO_DETECTOR_CHECKPOINT=artifacts/detector/detector-base
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,http://localhost:5173
SHUDDHO_LOG_RAW_TEXT=false
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<secret>
OPENROUTER_MODEL=<currently-valid-openrouter-model>
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho
SHUDDHO_LLM_ON_CHECK=manual
```

The Docker image copies `artifacts/` into `/app/artifacts` when the directory exists in the repository. The sentence-level corrector is optional: if `artifacts/corrector/corrector-base/best_model.pt` is absent or incomplete, `/health/deep` reports `corrector.status = missing_checkpoint`, analysis uses `backend_without_corrector` when the detector is ready, and Shuddho stays online with rules + spelling suggestions. To fully enable the corrector on Render, deployment artifacts must include both `artifacts/corrector/corrector-base/best_model.pt` and `artifacts/corrector/corrector-base/checkpoint`; until then use `SHUDDHO_CORRECTOR_ENABLED=auto` or `SHUDDHO_CORRECTOR_ENABLED=false` so missing checkpoints remain a health warning instead of a hard failure. The FastAPI backend must expose `/health`, `/health/deep`, `/api/preferences`, `/api/check`, `/api/rewrite`, `/api/tone`, and `/api/events` so the Vite web editor can call Render directly. Keep `SHUDDHO_LOG_RAW_TEXT=false` in production so raw user text is not logged.

After merging a fix that removes broken LFS pointers, redeploy Render with **Manual Deploy → Clear build cache & deploy**.

## Corrector checkpoint deployment

### Option A: run without corrector

- No `.pt` files are needed.
- The app uses rules + spelling, and the detector if a valid detector artifact is available.
- Render deploy works because there are no broken Git LFS pointers to download during clone.

### Option B: use Git LFS manually

Only use this from a developer machine that has the real checkpoint files and can upload to GitHub LFS:

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

Then redeploy Render with **Manual Deploy → Clear build cache & deploy**. The `git lfs push --all origin main` step is required; if the Git LFS pointer exists but the object was not uploaded, Render fails during checkout with a smudge error.

### Option C: use external storage

Recommended for production:

- Hugging Face Hub
- AWS S3
- Cloudflare R2
- GitHub Releases
- Google Cloud Storage

Store the model outside the Git repository and download it during build or startup. The backend supports optional `SHUDDHO_CORRECTOR_MODEL_URL`; when set, startup downloads the URL to `artifacts/corrector/corrector-base/best_model.pt` if that file is missing. The checkpoint metadata must still exist at `artifacts/corrector/corrector-base/metadata.json`.

## Training the sentence-level corrector

Train from the repository root before deploying full contextual correction mode:

```bash
python -m ml.corrector.train --config ml/training/configs/corrector.base.json
```

Expected output files:

```text
artifacts/corrector/corrector-base/metadata.json
artifacts/corrector/corrector-base/best_model.pt
artifacts/corrector/corrector-base/last_model.pt
artifacts/corrector/corrector-base/checkpoint
artifacts/corrector/corrector-base/metrics.json
```

Do not commit raw PyTorch `.pt` binaries directly from automation. For full contextual correction, add `best_model.pt` and `last_model.pt` with the Git LFS flow above or publish them to external model storage. Without a loadable `.pt` checkpoint, copying `artifacts/` is still safe, but the backend runs without the sentence-level corrector.

## Manual smoke tests

```bash
curl https://shuddho-api.onrender.com/health
curl https://shuddho-api.onrender.com/health/deep
curl https://shuddho-api.onrender.com/api/preferences
curl -X POST https://shuddho-api.onrender.com/api/check \
  -H "Content-Type: application/json" \
  -d '{"text":"আমি  আমি ভাত খাই।","language":"bn"}'
curl -X POST https://shuddho-api.onrender.com/api/ai/check \
  -H "Content-Type: application/json" \
  -d '{"text":"আমি আজ স্কুলে গেছিলাম।","language":"bn"}'
```

Verify full mode with:

```bash
curl https://shuddho-api.onrender.com/health/deep
```

The corrector is loaded when the JSON contains:

```json
{
  "corrector": { "status": "ready", "loaded": true },
  "analysis_profile": "full_local"
}
```

If the JSON contains `"corrector": { "status": "missing_checkpoint" }`, Render received a reachable backend but not a loadable `artifacts/corrector/corrector-base` artifact.

PowerShell:

```powershell
curl.exe https://shuddho-api.onrender.com/health
curl.exe https://shuddho-api.onrender.com/health/deep
curl.exe https://shuddho-api.onrender.com/api/preferences
curl.exe -X POST https://shuddho-api.onrender.com/api/check `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"আমি  আমি ভাত খাই।\",\"language\":\"bn\"}"
curl.exe -X POST https://shuddho-api.onrender.com/api/ai/check `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"আমি আজ স্কুলে গেছিলাম।\",\"language\":\"bn\"}"
```
