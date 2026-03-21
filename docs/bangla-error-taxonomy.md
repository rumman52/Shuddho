# Bangla Error Taxonomy

## High-confidence MVP categories

- spelling
  - unknown word against local lexicon
  - safe exact typo replacement
  - trusted variant mapping
- grammar
  - repeated word
  - narrow pronoun and verb mismatch rules
- punctuation
  - duplicate punctuation
  - whitespace before punctuation
  - missing safe spacing after punctuation
- spacing
  - duplicate whitespace
  - fused spacing around narrow postposition and number-unit patterns

## Detector training labels

The current detector scaffolding uses a narrow label set that stays aligned with conservative runtime behavior:

- `ok`
- `spelling`
- `grammar`
- `punctuation`
- `spacing`

## Future conservative additions

- broader postposition and compound spacing coverage
- more context-aware Bangla agreement detection once annotated data improves
- detector-backed candidate generation for categories already covered by rules or lexicon
- feedback-aware reranking beyond fixed heuristics

## Low-confidence areas intentionally deferred

- full sentence rewrites
- context-heavy verb agreement
- semantic clarity suggestions
- aggressive style normalization

Precision is preferred over recall across all categories.
