# Architecture

## Overview

Shuddho is an extension-first Bangla writing assistant built as a layered monorepo:

1. `apps/chrome-extension` is the primary user product for inline feedback on real text surfaces.
2. `apps/web-editor` is the debug, demo, and contract-validation surface.
3. `services/api` exposes stable HTTP endpoints for analysis, feedback, preferences, tone, and rewrites.
4. `services/analysis` keeps correction logic conservative with deterministic ranking, UI enrichment, tone, and rewrite services layered on top.
5. `services/feedback` persists user interactions and per-user preferences in SQLite.
6. `shared/schemas` keeps Python and TypeScript contracts aligned.
7. `ml/*` and `data/*` remain offline training and evaluation space for detector and future model work.

The runtime stays Bangla-first and precision-oriented. Rules, spell checks, detector hooks, and deterministic ranking remain the foundation. Tone guidance and rewrite actions are additive, opt-in layers.

## Shared contracts

`shared/schemas/python_models.py` and `shared/schemas/contracts.ts` define the cross-runtime API surface for:

- analyze requests and responses
- enriched suggestions
- feedback events
- tone analysis
- rewrite requests and responses
- user preferences

Backward compatibility matters. Existing `POST /analyze` consumers can continue using the original shape while new clients read richer optional fields such as `short_title`, `ui_group`, `ranking_score`, `rewrite_intents`, and `tone_labels`.

## Analyze flow

1. A client sends raw text plus optional mode and preference context to `POST /analyze`.
2. `services/api/shuddho_api/app.py` resolves persisted preferences, merges request-level overrides, and checks the incremental cache.
3. `services.analysis.shuddho_analysis.pipeline.AnalysisPipeline` performs normalization, rule checks, spell checks, detector hooks, candidate generation, and suggestion management.
4. `services.analysis.shuddho_analysis.ranking.SuggestionRankingPipeline` scores candidates using deterministic signals plus aggregate feedback history.
5. Preference-aware filtering suppresses ignored rule keys, personal-dictionary false positives, and lower-priority suggestions when density is reduced.
6. `services.analysis.shuddho_analysis.ui_enrichment.SuggestionUiEnricher` assigns UX metadata such as short titles, groups, brief Bangla and English explanations, safe-apply hints, and rewrite intent hints.
7. The API returns the enriched response and stores it in a lightweight content-hash cache keyed by text and relevant preference mode.

This keeps the existing correction engine intact while making the output friendlier for inline product UX.

## Feedback and preferences flow

1. Web editor and extension actions call `POST /feedback` for accepts, dismissals, ignore-forever, rewrite feedback, tone feedback, and personal-dictionary events.
2. `services/feedback/shuddho_feedback/store.py` writes feedback and per-user preferences to SQLite.
3. Persisted preferences include:
   - writing goal
   - tone goal
   - suggestion density
   - rewrite enablement
   - tone visibility
   - personal dictionary
   - suppressed rule keys
   - disabled sites
4. Ranking and suppression logic can read aggregate feedback without coupling UI code to persistence details.

The trust model stays explicit: Shuddho never silently rewrites user text, and feedback only influences future ranking and suppression.

## Tone analysis flow

1. Clients call `POST /tone/analyze` with longer text blocks.
2. `services.analysis.shuddho_analysis.tone.ToneAnalyzer` applies heuristic signals first:
   - punctuation intensity
   - abrupt versus soft phrasing
   - honorific and respectful markers
   - conversational markers
   - emphasis and urgency patterns
   - signs of unclear structure
3. The service returns a primary tone, optional secondary tones, confidence, Bangla and English explanations, and short advice strings.
4. If optional model-backed helpers are unavailable, the heuristic layer still responds instead of failing the request.

Tone is informative and non-blocking. It does not gate corrections or rewrites.

## Rewrite flow

1. Clients call `POST /rewrite` with full text or a selected span plus a target intent.
2. `services.analysis.shuddho_analysis.rewrite_service.RewriteService` produces conservative heuristic rewrite options for:
   - clarity
   - formal
   - concise
   - friendly
   - professional
3. Candidate rewrites are validated for spacing, punctuation, named-entity preservation, and meaning drift heuristics before being returned.
4. The service returns one to three options at most, plus warnings whenever confidence is limited.
5. Apply remains a client-side explicit action; the backend never writes user text directly.

Rewrite generation is intentionally separate from baseline correction so high-precision spelling and grammar suggestions remain predictable.

## Chrome extension flow

1. The content script detects supported editable surfaces:
   - `textarea`
   - safe text-like `input`
   - `contenteditable`
2. Unsupported or unsafe surfaces are skipped, including password fields and hidden inputs.
3. Text extraction and visible-range tracking stay local in the page context.
4. Requests are debounced and stale work is ignored to reduce churn while typing.
5. The overlay renders issue underlines for safe surfaces and a compact panel for suggestion details and actions.
6. Actions include:
   - apply suggestion
   - dismiss
   - ignore forever
   - add to dictionary
   - request rewrite by intent
7. Tone summaries appear for longer text when enabled.
8. `background.ts` owns persisted extension settings via `chrome.storage` and site-level enable or disable state.

The extension is the hero product surface, but it avoids risky DOM mutation that could break host editors or native undo behavior.

## Web editor flow

The web editor mirrors the core backend capabilities for testing and demos:

- analyze and local fallback
- preference editing
- tone analysis
- rewrite actions
- suggestion action wiring
- runtime transparency when optional services are unavailable

This keeps backend iteration observable without requiring browser-extension debugging for every change.

## Degraded mode and fallback behavior

Shuddho is designed to remain useful when optional components are unavailable:

- if detector-backed signals are unavailable, rules and spell checks still run
- if rewrite generation is limited, the API returns warnings instead of hard failures
- if tone analysis cannot use richer signals, heuristic tone still responds
- if the backend is unavailable, clients can fall back to lighter local analysis paths where supported

Graceful degradation is visible to the user. The system does not pretend a stronger runtime is active when it is not.

## ML separation

- Runtime analysis remains safe even with no trained detector checkpoint.
- Detector, corrector, ranking experiments, and evaluation live under `ml/`.
- Offline model work can improve recall later, but it does not replace the conservative runtime architecture.
- Any future model-backed rewrite or tone improvements must still pass local validation and confidence thresholds before surfacing to users.
