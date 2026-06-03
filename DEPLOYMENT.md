# Shuddho Deployment

## Web editor on Vercel

The web editor is a Vite React single-page application in `apps/web-editor`. The repository uses npm workspaces with `package-lock.json`; use npm commands for Vercel and local validation.

### Recommended Vercel settings when Root Directory is `apps/web-editor`

Use these settings when the Vercel project is configured to build from the web editor package directory:

- Framework Preset: Vite
- Root Directory: `apps/web-editor`
- Install Command: `npm install`
- Build Command: `npm run build`
- Output Directory: `dist`

Fallback build command also supported:

```bash
npm run build:web-editor
```

`apps/web-editor/vercel.json` pins the app-root deployment to Vite, `npm run build`, `dist`, and an SPA rewrite to `index.html` so direct routes work after deployment.

### Alternative monorepo-root Vercel settings

Use these settings when the Vercel project is configured to build from the repository root:

- Framework Preset: Vite
- Root Directory: repository root
- Install Command: `npm install`
- Build Command: `npm run build:web-editor`
- Output Directory: `apps/web-editor/dist`

The root `vercel.json` is for this monorepo-root deployment shape. The root package script delegates to the `@shuddho/web-editor` npm workspace.

### A. Vercel frontend environment variables

Set only public Vite variables in the Vercel frontend project:

```dotenv
VITE_API_BASE_URL=https://YOUR_RENDER_BACKEND_PUBLIC_URL
VITE_USE_GATEWAY=true
VITE_ENABLE_LOCAL_FALLBACK=false
```

If `VITE_API_BASE_URL` is missing, the frontend still builds and renders, but it shows a configuration warning and keeps backend/AI requests disabled until a valid public backend URL is configured.

Do **not** add these to Vercel frontend environment variables:

```dotenv
OPENAI_API_KEY
OPENROUTER_API_KEY
OPENAI_MODEL
OPENROUTER_MODEL
SHUDDHO_LLM_PROVIDER
```

Those values belong only in the backend environment. Browser code must route AI review through the backend and must not receive private provider keys.


### B. Backend environment variables

For Deep AI Review with the OpenRouter-hosted `openai/gpt-oss-120b:free` model, set these only on the backend service (for example Render), never in Vercel:

```dotenv
SHUDDHO_ENABLE_LLM=true
SHUDDHO_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<secret>
OPENROUTER_MODEL=openai/gpt-oss-120b:free
OPENROUTER_HTTP_REFERER=https://shuddho-web-editor.vercel.app
OPENROUTER_APP_TITLE=Shuddho
SHUDDHO_LLM_ON_CHECK=manual
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,http://localhost:5173,http://127.0.0.1:5173
SHUDDHO_ALLOW_VERCEL_PREVIEWS=false
SHUDDHO_LLM_TIMEOUT_SECONDS=35
SHUDDHO_LLM_INTERACTIVE_TIMEOUT_SECONDS=45
SHUDDHO_LLM_BACKGROUND_TIMEOUT_SECONDS=60
SHUDDHO_MAX_AI_TEXT_CHARS=5000
SHUDDHO_LLM_MAX_CANDIDATES=8
SHUDDHO_LLM_MAX_CANDIDATE_CHARS=2200
SHUDDHO_LLM_MAX_COMPLETION_TOKENS=1400
```

`openai/gpt-oss-120b:free` is an OpenRouter model ID. Do not set it as `OPENAI_MODEL` and do not use it with `SHUDDHO_LLM_PROVIDER=openai`; the OpenAI provider path is only for official OpenAI model IDs such as `gpt-4o-mini`.

### Local validation

From the repository root:

```bash
npm install
npm run build:web-editor
```

From the app directory:

```bash
cd apps/web-editor
npm install
npm run build
npm run build:web-editor
```

Both app-directory build commands produce `dist` inside `apps/web-editor`. The root build command produces the same app output at `apps/web-editor/dist`.

### Manual validation commands

```bash
npm run build:web-editor
npm run build --workspace @shuddho/api
python -m uvicorn services.api.shuddho_api.app:app --host 127.0.0.1 --port 8000 --reload
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/deep
curl http://127.0.0.1:8000/api/llm/debug
curl -X POST http://127.0.0.1:8000/api/check \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"আমি বাংলা লিখি ।। বাংলা বাংলা ভাষা খুব সুন্দর !!\",\"language\":\"bn\",\"options\":{\"includeLLM\":true,\"asyncLLM\":false,\"llmMode\":\"review_candidates\",\"mode\":\"smart\"}}"
```

The check response should include `llm_requested`, `llm_attempted` when the provider is configured, `llm_provider`, `llm_model`, `suggestions`, local/AI suggestion counts, `warnings`, `diagnostics.llm`, and `timings`.
