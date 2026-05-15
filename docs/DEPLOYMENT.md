# Shuddho deployment

## Vercel web editor

Set these Vercel environment variables for `https://shuddho-web-editor.vercel.app`:

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

## Render FastAPI backend

Set these Render environment variables for `https://shuddho-api.onrender.com`:

```dotenv
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app
SHUDDHO_LOG_RAW_TEXT=false
```

The FastAPI backend must expose `/health`, `/api/preferences`, `/api/check`, `/api/rewrite`, `/api/tone`, and `/api/events` so the Vite web editor can call Render directly.

## Manual smoke tests

```bash
curl https://shuddho-api.onrender.com/health
curl https://shuddho-api.onrender.com/api/preferences
curl -X POST https://shuddho-api.onrender.com/api/check \
  -H "Content-Type: application/json" \
  -d '{"text":"আমি  আমি ভাত খাই।","language":"bn"}'
```

PowerShell:

```powershell
curl.exe https://shuddho-api.onrender.com/health
curl.exe https://shuddho-api.onrender.com/api/preferences
curl.exe -X POST https://shuddho-api.onrender.com/api/check `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"আমি  আমি ভাত খাই।\",\"language\":\"bn\"}"
```
