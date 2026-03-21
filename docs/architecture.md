# Architecture

## Overview

Shuddho is split into four layers:

1. `apps/web-editor` and `apps/chrome-extension` for user-facing clients
2. `services/*` for runtime analysis, ranking, and feedback storage
3. `shared/*` for contracts, fixtures, constants, and cross-runtime helpers
4. `ml/*` and `data/*` for detector training, offline evaluation, and future model work

## Analyze flow

1. Client sends raw text to `POST /analyze`.
2. The API delegates to `services.analysis.shuddho_analysis.pipeline.AnalysisPipeline`.
3. `services/normalizer` produces normalized text plus offset mapping back to the original input.
4. `services/rules` runs conservative pattern-based checks on raw text.
5. `services.analysis.shuddho_analysis.detector.DetectorService` receives raw text, normalized text, and rule suggestions.
6. `services/spell` runs lexicon-based checks on normalized text.
7. `services.analysis.shuddho_analysis.candidate_generator.CandidateGenerator` combines rule, spell, detector, and future model candidates into one candidate set.
8. `services.analysis.shuddho_analysis.ranking.SuggestionRankingPipeline` applies deterministic ranking signals such as source, confidence, overlap, and feedback history.
9. `services.suggestion_manager` maps normalized spans back to the original text, dedupes overlaps, assigns response ids, and returns the shared suggestion contract.

The current runtime stays conservative and Bangla-first. Rules and lexicon-backed spelling remain the highest-precision layers, while detector and ranking hooks are intentionally incremental.

## Feedback flow

1. Web editor accept and dismiss actions call `POST /feedback`.
2. `services/feedback` stores the interaction in SQLite.
3. Ranking can consume aggregate accept and dismiss statistics without coupling UI logic to storage.
4. Future learned reranking can be layered on top of the same feedback store.

## Web editor flow

1. The editor uses Tiptap and a newline-aware text surface instead of a single-paragraph text extraction path.
2. Suggestions are rendered as issue marks plus a focused suggestion card.
3. Navigation and accept/dismiss actions stay span-anchored to the shared suggestion contract.

## Chrome extension flow

1. Content script detects `textarea`, text-like `input`, and `contenteditable`.
2. Text extraction stays local in the content script.
3. Requests are debounced before calling the backend.
4. Simple `textarea` and text-like `input` fields use a mirrored inline overlay for visible issue decoration.
5. Complex `contenteditable` editors keep a safe badge and rail fallback instead of risky DOM mutation.
6. Position sync is kept in the extension layer during typing, scrolling, resizing, and selection changes.

## ML separation

- Runtime remains safe even when no trained detector checkpoint is present.
- Tokenizer, detector, corrector, ranking, and evaluation live in `ml/`.
- `ml/detector/train.py` provides a lightweight from-scratch training entrypoint for span-aware token labeling.
- Detector inference is optional and checkpoint-gated; the corrector stays offline-only for now.
- No pretrained Bangla or multilingual checkpoints are used.
