# Architecture

## Overview

Shuddho is split into four layers:

1. `apps/web-editor` and `apps/chrome-extension` for user-facing clients
2. `services/*` for real-time analysis and logging
3. `shared/*` for contracts, fixtures, and constants
4. `ml/*` and `data/*` for future custom tokenizer/model training

## Analyze flow

1. Client sends raw text to `POST /analyze`.
2. The API normalizes text through `services/normalizer`.
3. `services/spell` runs lexicon-based checks on normalized text.
4. `services/rules` runs conservative pattern-based checks on raw text.
5. `services/suggestion_manager` maps spell spans back to original text, merges outputs, suppresses weak duplicates, and returns the shared suggestion contract.

## Feedback flow

1. Web editor accept and dismiss actions call `POST /feedback`.
2. `services/feedback` stores the interaction in SQLite.
3. Future ranking work can learn from those logs without coupling UI logic to the storage layer.

## Chrome extension flow

1. Content script detects `textarea`, text-like `input`, and `contenteditable`.
2. Text extraction stays local in the content script.
3. Requests are debounced before calling the backend.
4. Suggestions are mapped to plain-text offsets and rendered as a compact indicator rail above the active field.
5. Unsupported or very large editors fall back to no overlay instead of risky DOM manipulation.

## ML separation

- Inference MVP stays rule/spell based.
- Tokenizer, detector, corrector, ranking, and evaluation live in `ml/`.
- Training code and configs stay out of runtime services.
- No pretrained Bangla or multilingual checkpoints are used.

