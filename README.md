# Shuddho

Shuddho is an original AI writing assistant monorepo. The new Draft Lab foundation adds a production-shaped hybrid client-cloud architecture while preserving the existing Bangla assistant code and extension assets.

## New AI writing assistant foundation

```text
apps/
  api/                 TypeScript API gateway, orchestration, WebSocket sync boundary
  web/                 Next.js writing editor MVP
  chrome-extension/    Existing extension surface
  web-editor/          Existing Vite editor surface
packages/
  shared/              Shared TypeScript schemas and contracts
  nlp/                 Rule-based and mock AI provider abstractions
  observability/       Structured logs and timing helpers
  config/              Environment config schemas
docs/                  Architecture, API, data flow, security, roadmap
infra/                 Docker Compose and deployment notes
```

## Features in the Draft Lab MVP

- Rich web writing surface with local document state.
- Debounced `POST /api/check` requests.
- Inline underlines and suggestion cards.
- Accept/reject suggestion actions with event tracking.
- Rule-based grammar, spelling, style, spacing, passive-voice, and tone suggestions.
- Mock rewrite provider with a clean provider interface for future hosted or on-device AI.
- API gateway endpoints for check, rewrite, tone, preferences, events, documents, health, metrics, and WebSocket sync.
- PostgreSQL Prisma schema and migration for users, documents, revisions, suggestions, preferences, events, and team settings.
- Redis-ready cache/rate/session placeholder and Docker Compose stack.
- Privacy hooks, request IDs, rate limiting, validation, and structured log redaction.

## Run locally

### One-command container stack

```bash
docker compose -f infra/docker-compose.yml up --build
```

Then open:

- Web app: http://localhost:3000
- API health: http://localhost:4000/health

### Local development

```bash
npm install
npm run dev
```

The root `npm run dev` starts the API on port 4000 and the Next.js web app on port 3000.

Useful commands:

```bash
npm run dev:api
npm run dev:web
npm test
npm run build
```

## Sample text to try

```text
I has teh first draft.  This is terrible due to the fact that it was created in order to test recieve suggestions.
```

The app should detect examples such as `teh` → `the`, `recieve` → `receive`, `I has` → `I have`, repeated spaces, wordy phrasing, passive-voice hints, and harsh tone.

## Architecture docs

- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API.md)
- [Data flow](docs/DATA_FLOW.md)
- [Security](docs/SECURITY.md)
- [Roadmap](docs/ROADMAP.md)

## Existing Python/Bangla stack

The repository still includes the prior FastAPI, Python NLP, datasets, and extension code. Those components remain available for existing tests and future integration with the new TypeScript gateway.
