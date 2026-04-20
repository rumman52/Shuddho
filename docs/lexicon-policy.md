# Lexicon Policy

Shuddho treats the lexicon as a governed local asset, not a raw dump of every imported token.

Runtime layers:
- `core_formal_words`: trusted, active, common canonical forms that the spell engine accepts directly
- `accepted_variants`: trusted, active surface forms that normalize into a canonical form and can safely power correction maps
- `named_entities`: explicit named-entity sources that are safe to keep in runtime when provenance supports them
- `colloquial_or_dialect_review`: trusted but non-common rows kept out of runtime until reviewed
- `reject_list`: inactive or untrusted rows excluded from runtime
- `user_dictionary`: per-user words merged at request time, never silently folded into the shared base lexicon

Runtime inclusion rules:
- include only trusted and active rows
- include canonical rows in runtime only when they are marked common or come from an explicit named-entity source
- include normalized surface variants when they map to a canonical form
- keep trusted but non-common canonical rows in review output, not in the live runtime artifact
- never load `words_clean.csv` directly in production runtime when a built artifact is available

Governance rules:
- provenance must be recorded in `data/imports/lexicon/provenance.json`
- runtime artifacts are built with `python scripts/build_runtime_lexicon.py`
- review and reject outputs are part of the build so policy decisions stay inspectable
- lexicon changes that widen runtime acceptance should be explained in policy or provenance updates
