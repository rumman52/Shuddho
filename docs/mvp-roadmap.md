# MVP Roadmap

## Shipped in this v1 pass

- Extension-first product direction with the Chrome MV3 extension as the primary user surface
- Conservative Bangla analysis pipeline preserved across normalization, rules, spell checks, detector hooks, candidate generation, ranking, and suggestion management
- Shared Python and TypeScript contracts for:
  - enriched suggestions
  - user preferences
  - rewrite requests and responses
  - tone analysis
  - extended feedback actions
- New backend endpoints:
  - `POST /rewrite`
  - `POST /tone/analyze`
  - `GET /preferences/{user_id}`
  - `POST /preferences/{user_id}`
- SQLite-backed persistence for per-user preferences, personal dictionary entries, and ignored rule keys
- Feedback-aware ranking and preference-aware suggestion suppression
- Lightweight incremental caching for repeated analyze, tone, and rewrite requests
- Extension settings and richer suggestion actions:
  - apply
  - dismiss
  - ignore forever
  - add to dictionary
  - rewrite by intent
- Tone guidance and non-blocking rewrite support
- Web editor parity for testing, demos, and backend debugging
- Regression coverage for schemas, preferences, analyze compatibility, tone, and rewrite flows

## Product principles for this phase

1. Trust first. Do not silently apply changes or overclaim confidence.
2. Bangla-first behavior. Handle orthography, spacing, named entities, and mixed Bangla plus English text conservatively.
3. Extension-first polish. Real inline interaction matters more than decorative UI.
4. Shared contracts. Backend, extension, and web editor should stay in sync.
5. Graceful degradation. The product should remain useful when optional runtime components are unavailable.

## Immediate next milestones

1. Improve safe inline rendering for more complex `contenteditable` editors without risky DOM mutation.
2. Broaden rewrite quality validation with more Bangla-specific fixtures and named-entity regression tests.
3. Expand tone heuristics and advice coverage for more workplace, academic, and conversational writing patterns.
4. Add richer extension-side unit coverage for overlay state, stale-request handling, and suggestion action wiring.
5. Improve feedback similarity matching so repeated false positives down-rank more precisely across near-duplicate cases.
6. Build lightweight evaluation dashboards for acceptance rate, suppression rate, and rewrite usefulness.

## Explicitly deferred beyond this v1

- billing
- team administration
- plagiarism and citations
- mobile or desktop apps
- cloud infrastructure work
- Word or Docs plugins beyond the browser extension
- replacing the layered pipeline with a monolithic generative system
- automatic application of user-visible edits
