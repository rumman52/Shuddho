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
SHUDDHO_CORRECTOR_ENABLED=true
SHUDDHO_CORRECTOR_CHECKPOINT=artifacts/corrector/corrector-base
SHUDDHO_DETECTOR_ENABLED=true
SHUDDHO_DETECTOR_CHECKPOINT=artifacts/detector/detector-base
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app
SHUDDHO_LOG_RAW_TEXT=false
```

The Docker image copies `artifacts/` into `/app/artifacts`, so Render can load checked-in detector and corrector artifacts from the relative checkpoint paths above. The detector artifact is currently expected at `artifacts/detector/detector-base`. The sentence-level corrector artifact is expected at `artifacts/corrector/corrector-base`; if it is absent or incomplete, `/health/deep` reports `corrector.status = missing_checkpoint`, `analysis_profile = backend_without_corrector` when the detector is ready, and Shuddho stays online in degraded rules + spelling mode.

The FastAPI backend must expose `/health`, `/health/deep`, `/api/preferences`, `/api/check`, `/api/rewrite`, `/api/tone`, and `/api/events` so the Vite web editor can call Render directly. Keep `SHUDDHO_LOG_RAW_TEXT=false` in production so raw user text is not logged.

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

Include those artifact files in the Render build context before redeploying. Do not commit raw PyTorch `.pt` binaries directly from automation; add `best_model.pt` and `last_model.pt` from a developer machine with Git LFS enabled. Without the LFS-backed `.pt` files, copying `artifacts/` is not enough for full contextual correction because the backend has no sentence-level corrector checkpoint to load.

## Manual smoke tests

```bash
curl https://shuddho-api.onrender.com/health
curl https://shuddho-api.onrender.com/health/deep
curl https://shuddho-api.onrender.com/api/preferences
curl -X POST https://shuddho-api.onrender.com/api/check \
  -H "Content-Type: application/json" \
  -d '{"text":"আমি  আমি ভাত খাই।","language":"bn"}'
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
```
