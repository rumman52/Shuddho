# Shuddho

Shuddho is a Bangla writing assistant monorepo with a conservative rule-and-lexicon MVP today and clean interfaces for future custom ML models trained from scratch.

The current app keeps a hybrid backend architecture. Suggestions come from normalization, rules, the spell engine, detector-backed suspicious span analysis, optional OpenRouter analysis for context-sensitive Bangla issues, ranking, and confidence gating inside the backend API.

## What is implemented

- React + TypeScript + Tiptap web editor in `apps/web-editor`
- FastAPI backend in `services/api`
- Bangla normalizer, spell engine, rule engine, and suggestion merger
- SQLite feedback logging for accept and dismiss events
- Chrome Extension Manifest V3 scaffold with backend integration in `apps/chrome-extension`
- docs, fixtures, evaluation script, corpus utilities, and ML scaffolding for future custom training

## Repository shape

```text
apps/
  chrome-extension/
  web-editor/
data/
  corpus/
  datasets/
docs/
ml/
  corrector/
  detector/
  evaluation/
  ranking/
  tokenizer/
  training/
services/
  api/
  feedback/
  normalizer/
  rules/
  spell/
  suggestion-manager/
  suggestion_manager/
shared/
  constants/
  fixtures/
  schemas/
  utils/
tests/
```

## Run

### Backend

Create a repo-root `.env` from `.env.example` before starting the API:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

On this repo, the backend reads only the repo-root `.env`, for example [`C:/Projects/Shuddho/.env`](C:/Projects/Shuddho/.env). A frontend app-level `.env` does not configure OpenRouter or detector startup for the API. If backend behavior looks unchanged after editing a frontend `.env`, check the repo-root `.env` and restart FastAPI.

Then install and run the backend:

```bash
pip install -e .
uvicorn services.api.shuddho_api.app:app --reload
```

#### Run backend locally

On Windows, install and start the API from the repo root with:

```bat
py -m pip install -e .
py -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000
```

Or run [run_backend_windows.bat](C:/Projects/Shuddho/run_backend_windows.bat), which first switches into the repo root so it still works when launched from another directory.

Test the backend at `http://127.0.0.1:8000/health`.

Keep that terminal open while the backend is running. If you close it, the FastAPI server stops.

Warnings about Python `Scripts` paths not being on `PATH` are not blocking here because `py -m ...` runs the installed modules directly.

The backend loads the repo-root `.env` and can run in two modes:

- Local-only fallback: no `OPENROUTER_API_KEY` set, so only local rules, spelling, and detector-backed logic run.
- Hybrid mode: `OPENROUTER_API_KEY` is set, so suspicious Bangla sentences may be sent to OpenRouter and then validated locally before suggestions are returned.

Relevant backend variables:

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `OPENROUTER_TIMEOUT_SECONDS`
- `SHUDDHO_ALLOWED_ORIGINS`
- `SHUDDHO_DETECTOR_ENABLED`
- `SHUDDHO_DETECTOR_CHECKPOINT`
- `SHUDDHO_DETECTOR_THRESHOLD`

Detector defaults are now local-dev friendly:

- `SHUDDHO_DETECTOR_ENABLED=auto` tries to load the detector automatically.
- If `SHUDDHO_DETECTOR_CHECKPOINT` is unset, Shuddho falls back to `artifacts/detector/detector-base`.
- Set `SHUDDHO_DETECTOR_ENABLED=false` only when you explicitly want to disable detector-backed analysis.

The default `OPENROUTER_MODEL` is `nvidia/nemotron-3-super-120b-a12b`. For lower-cost testing you can switch it to `nvidia/nemotron-3-super-120b-a12b:free` in your local `.env` or hosting environment.

### OpenRouter troubleshooting

- Create a repo-root `.env` from `.env.example` and set a real `OPENROUTER_API_KEY`.
- Restart the backend after changing `.env` so the client is re-initialized.
- Open `http://127.0.0.1:8000/health` and confirm `openrouter_configured`, `openrouter_available`, `openrouter.status`, and `openrouter.reason`.
- Test with suspicious Bangla sentences that need context, not isolated dictionary words.
- Use `strict` mode first when verifying OpenRouter, because `standard` mode remains intentionally lower-noise.
- Check backend logs for OpenRouter startup status, suspicious sentence counts, issues returned, and issues filtered out.

### Why suggestions may look generic or empty

- The editor may be in explicit degraded mode. Check the UI banner first:
  - `Backend unreachable — local fallback only` means you are seeing browser-only safe checks, not full backend analysis.
  - `Backend live but detector disabled` means the API is running, but detector-backed contextual routing is degraded.
  - `Backend live but OpenRouter unavailable` means backend rules and spelling still work, but contextual LLM suggestions are unavailable.
- The backend status is most explicit at `http://127.0.0.1:8000/health`. Check:
  - `analysis_profile`
  - `degraded_reasons`
  - `detector.status` and `detector.reason`
  - `openrouter.status` and `openrouter.reason`
- The backend reads only the repo-root `.env`. If detector or OpenRouter settings changed, restart the backend after editing `.env`.
- `standard` mode is still lower-noise than `strict` or `formal`. If you are validating contextual Bengali corrections, compare all three modes.
- If the repo contains `artifacts/detector/detector-base` but health still shows the detector unavailable, inspect `detector.reason` and backend startup logs for the exact checkpoint or load failure.

### Web editor

```bash
npm install
npm run dev:web
```

The editor expects the API at `http://127.0.0.1:8000`. Override with `VITE_API_BASE_URL` if needed.
Copy `apps/web-editor/.env.example` to `apps/web-editor/.env.local` to keep a local override in the app workspace.
The frontend calls only the Shuddho backend and does not contain any secret or direct OpenRouter call.

### Chrome extension

```bash
npm install
npm run build:extension
```

Then load `apps/chrome-extension/dist` as an unpacked extension in Chrome.

## Local Public Testing

Run the backend locally from the repo root:

```bash
python -m uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port 8000
```

Expose the local backend with a temporary Cloudflare Quick Tunnel:

```bash
cloudflared tunnel --url http://localhost:8000
```

Copy the generated `https://...trycloudflare.com` URL and point the clients at it:

- Web editor: set `VITE_API_BASE_URL=https://your-random-name.trycloudflare.com`
- Chrome extension: build with `SHUDDHO_EXTENSION_API_BASE_URL=https://your-random-name.trycloudflare.com npm run build:extension`

`SHUDDHO_ALLOWED_ORIGINS` controls which frontend origins may call the API, not which backend URL the API is exposed on.

- Local Vite origins such as `http://127.0.0.1:5173` and `http://localhost:5173` are allowed by default for development.
- Chrome extension origins are allowed by default.
- If a public frontend calls the tunneled backend, set `SHUDDHO_ALLOWED_ORIGINS` to the frontend origin, for example `https://shuddho-web-editor.vercel.app`.
- Multiple frontend origins can be allowed with a comma-separated list, for example `SHUDDHO_ALLOWED_ORIGINS=https://shuddho-web-editor.vercel.app,https://your-preview.vercel.app`.

The trycloudflare URL is temporary, so update the frontend or extension config again whenever Cloudflare gives you a new tunnel address.

## Deployment

Railway should deploy the FastAPI backend only. This repo also contains the `apps/web-editor` and `apps/chrome-extension` workspaces, but they are not server processes and should not be imported as Railway services.

- Railway: build from the root `Dockerfile` and run only the Python API
- Web editor: deploy `apps/web-editor` separately from Railway
- Chrome extension: build locally with `npm run build:extension` and distribute separately, such as through the Chrome Web Store
- Service Source: GitHub repo `rumman52/Shuddho`
- Root Directory: `/`
- Build Command: leave empty
- Start Command: leave empty if the Dockerfile `CMD` is used
- Healthcheck Path: `/health`

Required Railway variables:

- `SHUDDHO_ALLOWED_ORIGINS=https://your-frontend-domain`
- `SHUDDHO_DETECTOR_THRESHOLD=0.82`
- `SHUDDHO_DETECTOR_CHECKPOINT=...` only if a real checkpoint exists

### Lexicon import

The lexicon import assets live in `data/imports/lexicon/`:

- `words_clean.csv` for accepted lexicon rows
- `words_review_flagged.csv` for review-only rows
- `cleaning_summary.txt` for import metadata and reporting

Run the importer from the repo root:

```bash
python scripts/import_lexicon_to_sqlite.py
```

This rebuilds `data/shuddho_lexicon.db` through a temporary file and replaces it only after a successful import. The importer creates these tables:

- `words_clean`
- `words_review_flagged`
- `import_reports`

The feedback database remains separate in `data/shuddho_feedback.db`.

At runtime, the spell engine now uses `data/imports/lexicon/words_clean.csv` as its main source of truth and loads it once at backend startup.

- runtime accepted words: canonical `normalized_word` values from active, trusted rows where `word != normalized_word`
- runtime direct correction map: active, trusted `word -> normalized_word` pairs from `words_clean.csv`
- runtime candidate pool: the same curated canonical target set loaded from `words_clean.csv`
- `words_review_flagged.csv` stays review-only and is never loaded into the active spell runtime
- `cleaning_summary.txt` remains report metadata only and is never loaded into the active spell runtime
- sqlite import remains offline tooling only; the backend runtime does not depend on `data/shuddho_lexicon.db`
- generic fuzzy suggestions are conservative and precision-first; if there is no strong candidate, no suggestion is returned

If `data/imports/lexicon/words_clean.csv` is missing, the spell engine falls back to `services/spell/data/seed_lexicon.txt` as a legacy development fallback only.

You can still refresh the legacy seed file from the imported clean lexicon for offline tooling:

```bash
python scripts/import_lexicon_to_sqlite.py --export-seed-lexicon
```

After updating `data/imports/lexicon/words_clean.csv`, restart the FastAPI backend so the in-memory spell engine reloads the latest runtime lexicon.

## API

### `GET /health`

```json
{
  "status": "ok",
  "detector_loaded": false,
  "detector_checkpoint": "artifacts/detector/detector-base",
  "allowed_origins": [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://shuddho-web-editor.vercel.app"
  ],
  "openrouter_configured": false,
  "openrouter_available": false,
  "openrouter_model": "nvidia/nemotron-3-super-120b-a12b",
  "detector": {
    "enabled": true,
    "loaded": false,
    "status": "missing_checkpoint",
    "reason": "Detector checkpoint could not be loaded from 'artifacts/detector/detector-base': ...",
    "checkpoint": "artifacts/detector/detector-base",
    "checkpoint_exists": false,
    "backend_name": "disabled",
    "threshold": 0.92
  },
  "openrouter": {
    "configured": false,
    "available": false,
    "status": "missing_api_key",
    "reason": "OPENROUTER_API_KEY is missing from the repo-root environment.",
    "model": "nvidia/nemotron-3-super-120b-a12b",
    "api_key_present": false,
    "timeout_seconds": 20
  },
  "analysis_profile": "backend_rules_and_spell_only",
  "degraded_reasons": [
    "detector_missing_checkpoint",
    "openrouter_missing_api_key"
  ]
}
```

### `POST /analyze`

Request:

```json
{
  "text": "আমি  বাংলা লিখি  ।। বাংলা বাংলা ভাষা খুব সুন্দর !!"
}
```

Sample response:

```json
{
  "text": "আমি  বাংলা লিখি  ।। বাংলা বাংলা ভাষা খুব সুন্দর !!",
  "normalized_text": "আমি বাংলা লিখি।। বাংলা বাংলা ভাষা খুব সুন্দর!!",
  "suggestions": [
    {
      "id": "rule_...",
      "category": "punctuation",
      "subtype": "space_before_punctuation",
      "span_start": 15,
      "span_end": 18,
      "original_text": "  ।",
      "replacement_options": ["।"],
      "confidence": 0.95,
      "explanation_bn": "বিরামচিহ্নের আগে অতিরিক্ত ফাঁকা আছে।",
      "explanation_en": "There is unnecessary whitespace before punctuation.",
      "source": "rule",
      "severity": "low",
      "status": "open"
    }
  ]
}
```

### `POST /feedback`

```json
{
  "suggestion_id": "rule_example",
  "action": "accepted",
  "text": "আমি  বাংলা লিখি  ।।",
  "replacement": "।"
}
```

## Tests and evaluation

```bash
pytest
pytest tests/test_lexicon_import.py
python -m ml.evaluation.precision_eval
```

## Bangla sample inputs

- `আমি  বাংলা লিখি  ।। বাংলা বাংলা ভাষা খুব সুন্দর !!`
- `Bangla editor এ  spelling আর grammar check করা দরকার , তাই না ?`
- `শুদ্ধ বাংলা ব্যকরণ আর বংলা বানানভুল ঠিক করা দরকার।`

## Known MVP limits

- The web editor currently keeps a single paragraph to simplify offset mapping.
- The extension renders a compact overlay rail and badge instead of true inline underlines inside arbitrary third-party editors.
- Spell coverage is intentionally small and conservative because the lexicon is seed-only.
- ML modules are scaffolds only. No model quality is claimed.

