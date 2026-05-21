# Shuddho deployment

## Vercel web editor

Set these Vercel environment variables for `https://shuddho-web-editor.vercel.app` in **Production, Preview, and Development**:

```dotenv
VITE_API_BASE_URL=https://shuddho-api.onrender.com
VITE_USE_GATEWAY=true
```

Recommended Vercel settings when the root directory is the repository root:

- Framework Preset: Vite
- Root Directory: repository root
- Install Command: `npm install --include=optional`
- Build Command: `npm run build --workspace @shuddho/web-editor`
- Output Directory: `apps/web-editor/dist`

If the Vercel Root Directory is `apps/web-editor` instead:

- Install Command: `npm install --include=optional`
- Build Command: `npm run build`
- Output Directory: `dist`

### Vercel preview deployments and CORS

Render only allows browser origins listed in `SHUDDHO_ALLOWED_ORIGINS` plus the safe local/extension regex built into the FastAPI app. If you test a Vercel preview URL, add that exact preview origin to `SHUDDHO_ALLOWED_ORIGINS`, for example:

```dotenv
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,https://your-preview-url.vercel.app
```

Do not use a blanket wildcard in production. If preview URLs must be dynamic, implement safe Vercel preview CORS handling that restricts origins to trusted Shuddho preview hostnames.

## Render FastAPI backend

Set these Render environment variables for `https://shuddho-api.onrender.com`:

```dotenv
SHUDDHO_CORRECTOR_ENABLED=auto
SHUDDHO_CORRECTOR_CHECKPOINT=artifacts/corrector/corrector-base
SHUDDHO_DETECTOR_ENABLED=auto
SHUDDHO_DETECTOR_CHECKPOINT=artifacts/detector/detector-base
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app
SHUDDHO_LOG_RAW_TEXT=false
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-3.5-flash
```

The Docker image copies `artifacts/` into `/app/artifacts` when the directory exists in the repository. The sentence-level corrector is optional: if `artifacts/corrector/corrector-base/best_model.pt` is absent or incomplete, `/health/deep` reports `corrector.status = missing_checkpoint`, analysis uses `backend_without_corrector` when the detector is ready, and Shuddho stays online with rules + spelling suggestions. The FastAPI backend must expose `/health`, `/health/deep`, `/api/preferences`, `/api/check`, `/api/rewrite`, `/api/tone`, and `/api/events` so the Vite web editor can call Render directly. Keep `SHUDDHO_LOG_RAW_TEXT=false` in production so raw user text is not logged.

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
