# Shuddho

Shuddho is a Bangla writing assistant monorepo built around a conservative correction pipeline and an extension-first product surface.

This v1 keeps the existing stack:

- FastAPI backend
- React + TypeScript web editor
- Chrome Extension Manifest V3

The assistant stays intentionally trust-first:

- rules + spell + detector/corrector + ranking remain the foundation
- suggestions are confidence-gated
- rewrites are explicit options, never silent edits
- user feedback, ignore-forever choices, and personal dictionary entries are persisted

## What is in the repo

```text
apps/
  chrome-extension/
  web-editor/
data/
docs/
ml/
services/
  analysis/
  api/
  feedback/
  normalizer/
  rules/
  spell/
  suggestion_manager/
shared/
  fixtures/
  schemas/
  utils/
tests/
```

Note: earlier README text referenced `apps/openrouter-agent`, but that folder is not present in this repo and is not part of the current product.

## Product surfaces

### Chrome extension

The extension is the primary product surface.

Current v1 behavior:

- detects textarea, supported text inputs, and contenteditable editors
- renders inline issue highlighting with an overlay panel
- supports apply, dismiss, ignore forever, add to dictionary, and rewrite actions
- shows tone hints for longer drafts
- stores local extension settings in `chrome.storage`
- degrades gracefully when the backend is unavailable

### Web editor

The web editor is the fastest demo and debugging surface for the backend.

Current v1 behavior:

- analyze text with shared contracts
- inspect runtime/degraded mode state
- edit user preferences
- review tone analysis
- request rewrites for a selection or a suggestion
- manage a personal dictionary

## Backend architecture

Backend entrypoints and core services:

- API: `services/api/shuddho_api/app.py`
- Analysis pipeline: `services/analysis/shuddho_analysis/pipeline.py`
- Ranking: `services/analysis/shuddho_analysis/ranking.py`
- Candidate generation: `services/analysis/shuddho_analysis/candidate_generator.py`
- Feedback + preferences persistence: `services/feedback/shuddho_feedback/store.py`
- Shared Python models: `shared/schemas/python_models.py`
- Shared TypeScript contracts: `shared/schemas/contracts.ts`

Additional assistant services added for v1:

- `services/analysis/shuddho_analysis/tone.py`
- `services/analysis/shuddho_analysis/rewrite_service.py`
- `services/analysis/shuddho_analysis/preferences.py`
- `services/analysis/shuddho_analysis/ui_enrichment.py`
- `services/analysis/shuddho_analysis/incremental_cache.py`

## Run locally

### Backend

From the repo root:

```bash
python -m pip install -e .
python -m uvicorn services.api.shuddho_api.app:app --host 127.0.0.1 --port 8000 --reload
```

Windows helper:

```bat
run_backend_windows.bat
```

Health checks:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/health/deep`

### Web editor

```bash
npm install
npm run dev:web
```

If a deploy or clean install ever fails with a missing Rollup native package such as `@rollup/rollup-linux-x64-gnu`, run a clean reinstall from the monorepo root:

```powershell
Remove-Item -Recurse -Force node_modules
npm install
```

The repo now declares the Linux x64 GNU Rollup binary explicitly for the web editor workspace so Vercel's Linux builds do not depend on npm recovering that optional dependency transitively.

Default local backend URL:

- `http://127.0.0.1:8000`

For deployed frontends, set `VITE_API_BASE_URL` to a public backend URL. The editor now refuses to pretend localhost is valid from a non-local browser origin.

### Chrome extension

```bash
npm install
npm run build:extension
```

Then load `apps/chrome-extension/dist` as an unpacked extension in Chrome.

To point the extension at a non-default backend during build:

```bash
SHUDDHO_EXTENSION_API_BASE_URL=https://your-backend.example npm run build:extension
```

## Extension-first workflow

Typical local flow:

1. Start the FastAPI backend on `http://127.0.0.1:8000`
2. Run the web editor for fast iteration and API debugging
3. Build the extension and load `apps/chrome-extension/dist` in Chrome
4. Use the extension popup to set backend URL, writing goal, tone goal, rewrite toggle, and per-site enablement

## API

### `GET /health`

Reports runtime availability for detector/corrector and the active backend analysis profile.

### `GET /health/deep`

Extends `/health` with backend version, env/runtime metadata, and lexicon details.

### `POST /analyze`

Backward compatible primary analysis endpoint.

Request:

```json
{
  "text": "আমি কিন্তু বাংলা লিখি।",
  "mode": "standard",
  "personal_dictionary": ["রাহুল"],
  "user_id": "writer-1"
}
```

Response highlights:

- `normalized_text`
- `corrected_text`
- `suggestions`
- `analysis_profile`
- `runtime_warnings`
- `used_detector`
- `used_corrector`

### `POST /rewrite`

Returns 1 to 3 high-confidence rewrite options for a selection or full draft.

Request:

```json
{
  "text": "প্লিজ রিপোর্ট পাঠান!!",
  "selection_start": 0,
  "selection_end": 18,
  "intent": "professional",
  "user_id": "writer-1"
}
```

### `POST /tone/analyze`

Returns heuristic-first tone analysis with primary tone, secondary tones, confidence, and quick advice.

Request:

```json
{
  "text": "অনুগ্রহ করে দ্রুত উত্তর দিন!!",
  "user_id": "writer-1"
}
```

### `GET /preferences/{user_id}`

Returns persisted user preferences, including:

- writing goal
- tone goal
- suggestion density
- auto-show tone
- rewrite enablement
- personal dictionary
- suppressed rule keys
- disabled sites

### `POST /preferences/{user_id}`

Upserts the same preference payload.

### `POST /feedback`

Stores user actions such as:

- `accepted`
- `dismissed`
- `ignore_forever`
- `add_to_personal_dictionary`
- `rewrite_accepted`
- `rewrite_dismissed`
- `tone_helpful`
- `tone_not_helpful`

## Local fallback vs backend-enhanced mode

When the backend is reachable, clients use:

- backend analysis
- tone analysis
- rewrite options
- persisted preferences
- feedback-aware ranking

When the backend is unavailable or misconfigured:

- the web editor falls back to local safe checks
- the extension keeps editing surfaces stable and shows backend-unavailable status
- typing is never blocked
- no silent rewrite is performed

## Personal dictionary and ignore forever

Two separate behaviors matter:

- Personal dictionary:
  suppresses false positives for user-approved words and mirrors locally in the extension
- Ignore forever:
  stores a persistent suppression key/rule key so similar suggestions stay hidden for that user

These preferences are backed by SQLite in the existing feedback store area.

## Verification

Commands used for the current repo state:

```bash
python -m pytest
npm run build:web
npm run build:extension
```

## Tests

Main backend coverage includes:

- schema validation
- analyze compatibility
- preferences persistence
- rewrite endpoint behavior
- tone endpoint behavior
- ranking + feedback adaptation
- personal dictionary handling

Frontend and extension coverage in this repo remains lightweight and mostly unit-level around shared helpers and runtime-state logic.

## Current v1 limits

- Rewrite generation is intentionally conservative and heuristic-heavy unless safer local corrections already justify a rewrite candidate.
- Tone analysis is heuristic-first, not a full semantic classifier.
- The extension focuses on Chrome MV3.
- Browser integration tests for the extension are still light; most verification is backend tests plus production builds.
