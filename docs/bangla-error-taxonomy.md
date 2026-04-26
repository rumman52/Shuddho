# Bangla Error Taxonomy

This taxonomy is the conservative source of truth for Shuddho's normal `/analyze` pipeline.

Pipeline order:

`normalizer -> rules -> spell -> detector -> corrector -> candidate generator -> ranking -> validation -> UI enrichment`

Rules for this taxonomy:

- Every visible `/analyze` suggestion must be exact-span, anchored, and explainable.
- `rewrite_only` items are not shown by normal `/analyze`.
- `register` and `clarity` suggestions are never auto-applied in normal analysis.
- Detector and corrector outputs only survive when they can be projected to safe inline spans.

## Categories

### `spelling`

| subtype_id | examples | safe_auto_apply | min_confidence | modes |
| --- | --- | --- | --- | --- |
| `spelling_error` | `বংলা -> বাংলা`, `ব্যকরণ -> ব্যাকরণ`, `অবশই -> অবশ্যই` | yes | 0.94 | standard, strict, formal |
| `orthography_variant` | `নিয়ে -> নিয়ে`, `হয় -> হয়` | no | 0.95 standard, 0.84 strict/formal | strict, formal |

### `grammar`

| subtype_id | examples | safe_auto_apply | min_confidence | modes |
| --- | --- | --- | --- | --- |
| `first_person_verb_mismatch` | `আমি ভাত খায় -> আমি ভাত খাই`, `আমি কাজ করে -> আমি কাজ করি` | yes | 0.88 | standard, strict, formal |
| `casual_pronoun_verb_mismatch` | `তুমি এখন যান -> তুমি এখন যাও`, `তুমি এটা করেন -> তুমি এটা করো` | yes | 0.88 | standard, strict, formal |
| `honorific_pronoun_verb_mismatch` | `আপনি কাজটা করো -> আপনি কাজটা করুন`, `তিনি স্কুলে যায় -> তিনি স্কুলে যান` | yes | 0.88 | standard, strict, formal |
| `third_person_verb_mismatch` | `সে স্কুলে যাই -> সে স্কুলে যায়`, `সে ভাত খাই -> সে ভাত খায়` | yes | 0.88 | standard, strict, formal |
| `repeated_word` | `আমি আমি -> আমি`, `বাংলা বাংলা -> বাংলা` | yes | 0.88 | standard, strict, formal |
| `duplicate_negation` | `না না -> না` when clearly accidental | yes | 0.88 | standard, strict, formal |
| `safe_exact_correction` | exact multi-token deterministic fixes such as `যদি ও -> যদিও` | yes | 0.9 | standard, strict, formal |

### `punctuation`

| subtype_id | examples | safe_auto_apply | min_confidence | modes |
| --- | --- | --- | --- | --- |
| `duplicate_punctuation` | `!! -> !`, `।। -> ।` | yes | 0.88 | standard, strict, formal |
| `bangla_full_stop` | `আমি বাংলা লিখি. -> আমি বাংলা লিখি।` | yes | 0.88 | standard, strict, formal |

### `spacing`

| subtype_id | examples | safe_auto_apply | min_confidence | modes |
| --- | --- | --- | --- | --- |
| `extra_whitespace` | `আমি  বাংলা -> আমি বাংলা` | yes | 0.9 | standard, strict, formal |
| `space_before_punctuation` | `লিখি  । -> লিখি।` | yes | 0.9 | standard, strict, formal |
| `space_after_punctuation` | `লিখি।সে -> লিখি। সে` | yes | 0.9 | standard, strict, formal |
| `number_unit_spacing` | `১০কেজি -> ১০ কেজি` | yes | 0.9 | standard, strict, formal |
| `fused_postposition` | `আমারসাথে -> আমার সাথে`, `স্কুলথেকে -> স্কুল থেকে`, `কাজেরজন্য -> কাজের জন্য` | yes | 0.9 | standard, strict, formal |

### `register`

| subtype_id | examples | safe_auto_apply | min_confidence | modes |
| --- | --- | --- | --- | --- |
| `formal_lexical_replacement` | `প্লিজ -> অনুগ্রহ করে`, `ওকে -> ঠিক আছে` | no | 0.82 | formal |
| `formal_pronoun_replacement` | `তুমি রিপোর্ট পাঠাও -> আপনি রিপোর্ট পাঠান` when the sentence is clearly formal and not quoted dialogue | no | 0.82 | formal |

### `clarity`

| subtype_id | examples | safe_auto_apply | min_confidence | modes |
| --- | --- | --- | --- | --- |
| `repeated_coordinator` | `এবং এবং -> এবং` | no | 0.9 | standard, strict, formal |
| `repeated_filler` | `মানে মানে -> মানে`, `আসলে আসলে -> আসলে` | no | 0.9 | standard, strict, formal |
| `code_mixed_latin` | `today -> আজ`, `tomorrow -> আগামীকাল` for the exact safe map only | no | 0.84 | strict, formal |

### `rewrite_only`

| subtype_id | examples | safe_auto_apply | min_confidence | modes |
| --- | --- | --- | --- | --- |
| `long_sentence_punctuation_hint` | very long Bengali sentence without separators | no | n/a | rewrite only |
| `connector_overload_hint` | too many connectors with no clean inline edit | no | n/a | rewrite only |
| `filler_overuse_hint` | repeated filler patterns that need a broader rewrite | no | n/a | rewrite only |

## Validation Rules

Any candidate is rejected when:

- `replacement_options` is empty
- replacement equals the original span text
- `original_text` does not exactly match the span
- explanation is generic
- `source_trace` is missing
- a model or hybrid suggestion lacks an exact anchor
- the replacement changes meaning too much
- Latin output appears outside the `code_mixed_latin` subtype
- confidence is below the minimum threshold
- a generic lexicon guess lacks a strong margin

## UI Expectations

- `spelling`, `grammar`, and `punctuation` show in correctness-oriented review queues.
- `spacing` shows as exact cleanup, not as vague style guidance.
- `register` and `clarity` always explain why they are suggestions and are never auto-applied.
- `rewrite_only` stays out of `/analyze` and belongs to a dedicated rewrite workflow.
