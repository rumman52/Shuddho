# Deterministic Bangla rules

Shuddho keeps a high-confidence deterministic layer available even when contextual AI, detector, or corrector components are unavailable. Rules must use exact token/phrase boundaries and preserve source offsets so frontend inline suggestions remain safe.

## Exact typo map additions

The curated exact-typo map includes these production-safe corrections:

| Original | Replacement | Type |
| --- | --- | --- |
| `অপরুপ` | `অপরূপ` | spelling |
| `অত্যাধিক` | `অত্যধিক` | spelling |
| `গান গাচ্ছে` | `গান গাইছে` | grammar / lexical phrase |

These rules are intentionally narrow. Do not add broad substring replacements; add only reviewed words or phrases with low false-positive risk.

## Register/style notes

Sadhu forms such as `হইল`, `উড়িতেছে`, and `হইলাম` are not blanket spelling errors. Style suggestions for modern standard Bangla should be contextual and must avoid quoted historical or literary passages.
