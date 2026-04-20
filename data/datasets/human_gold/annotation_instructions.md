# Annotation Instructions

Annotate each record as line-delimited JSON.

Required fields:
- `input_text`
- `target_text`
- `issues`

Issue guidance:
- keep `label` detector-compatible for now: `spelling`, `grammar`, `punctuation`, or `spacing`
- use `fine_label` for the more specific error taxonomy
- mark `is_variant_only=true` when the difference is an accepted orthography variant rather than a clear error
- use `expected_text` and `observed_text` when they help explain insertions, deletions, or zero-length spans

Review rules:
- do not mark dialect or colloquial forms as errors unless project policy says so
- if the fix is stylistic rather than mandatory, say so in notes or use `is_variant_only`
- if a missing word has no concrete span in source text, use `start == end` at the insertion point
- keep records small and local; do not rewrite whole paragraphs when a span-level fix is enough
