# Bangla NLP in Shuddho

Shuddho treats the Python Bangla pipeline as the linguistic source of truth. The TypeScript API gateway orchestrates requests, adapts legacy `/analyze` results into canonical `CheckResponse`, and falls back only to conservative Bangla-safe deterministic rules when Python is unavailable.

## Pipeline

1. NFC-preserving normalization.
2. Bangla sentence and token handling in the Python analysis stack.
3. Rule engine, spell engine, ranking, deduplication, tone, and rewrite services.
4. TypeScript span adaptation from Python code point offsets to browser UTF-16 offsets.
5. Grapheme snapping to avoid splitting Bangla vowel signs, virama/hasanta, nukta, and conjunct clusters.

Fallback rules are intentionally small: repeated spaces, duplicate words, spacing around `।`, and low-confidence missing sentence punctuation. English demo rules are not in the Bangla product path.
