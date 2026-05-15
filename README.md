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

Set this environment variable in Vercel so the deployed editor can reach a public backend instead of the local development default:

```text
VITE_API_BASE_URL=https://your-public-backend-tunnel-url
```

If Vercel **Root Directory** is the repository root:

- Framework Preset: Vite
- Install Command: `npm install --include=optional`
- Build Command: `npm run build --workspace @shuddho/web-editor`
- Output Directory: `apps/web-editor/dist`

If Vercel **Root Directory** is `apps/web-editor`:

- Framework Preset: Vite
- Install Command: `npm install --include=optional`
- Build Command: `npm run build`
- Output Directory: `dist`

Keep optional dependencies enabled so Vite/esbuild can install the native binary for the Vercel Linux build environment.
Do not set npm options such as `omit=optional`, `optional=false`, or `ignore-scripts=true` for this deployment.

## Architecture docs

- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Bangla NLP](docs/BANGLA_NLP.md)
- [Local development](docs/LOCAL_DEV.md)
- [Security and privacy](docs/SECURITY_PRIVACY.md)
- [Roadmap](docs/ROADMAP.md)
