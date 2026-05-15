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

## Vercel deployment (apps/web-editor)

Use these Vercel project settings for the Vite web editor deployment:

- Framework Preset: Vite
- Root Directory: repo root
- Install Command: `npm install --include=optional`
- Build Command: `npm run build --workspace @shuddho/web-editor`
- Output Directory: `apps/web-editor/dist`

Keep optional dependencies enabled so Vite/esbuild can install the native binary for the Vercel Linux build environment.
Do not set npm options such as `omit=optional`, `optional=false`, or `ignore-scripts=true` for this deployment.


## Render FastAPI backend

The Render backend should be configured with the checked-in model artifact paths:

```dotenv
SHUDDHO_CORRECTOR_ENABLED=true
SHUDDHO_CORRECTOR_CHECKPOINT=artifacts/corrector/corrector-base
SHUDDHO_DETECTOR_ENABLED=true
SHUDDHO_DETECTOR_CHECKPOINT=artifacts/detector/detector-base
SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app
SHUDDHO_LOG_RAW_TEXT=false
```

Train the sentence-level Bangla corrector before deploying full contextual correction mode:

```bash
python -m ml.corrector.train --config ml/training/configs/corrector.base.json
```

This produces `artifacts/corrector/corrector-base/metadata.json`, `best_model.pt`, `last_model.pt`, and `metrics.json`. Add the `.pt` files with Git LFS from a developer machine before redeploying Render. If that artifact is missing, `/health/deep` reports `corrector.status = missing_checkpoint` and Shuddho remains online in rules + spelling degraded mode. See [deployment](docs/DEPLOYMENT.md) and [corrector training](docs/train-corrector.md).

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
