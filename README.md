# Shuddho

Shuddho is a Bangla writing assistant monorepo with a conservative rule-and-lexicon MVP today and clean interfaces for future custom ML models trained from scratch.

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

```bash
pip install -e .
uvicorn services.api.shuddho_api.app:app --reload
```

### Web editor

```bash
npm install
npm run dev:web
```

The editor expects the API at `http://127.0.0.1:8000`. Override with `VITE_API_BASE_URL` if needed.

### Chrome extension

```bash
npm install
npm run build:extension
```

Then load `apps/chrome-extension/dist` as an unpacked extension in Chrome.

## API

### `GET /health`

```json
{
  "status": "ok"
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

