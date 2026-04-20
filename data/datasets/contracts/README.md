# Dataset Contracts

Each dataset split should be line-delimited JSON with explicit fields.

Core record shapes:
- detector example: `input_text`, `issues`
- corrector example: `source_text`, `target_text`
- evaluation example: `text`, `expected_subtypes`

Issue fields:
- `label`: current coarse detector-compatible label
- `subtype`: concrete mutation name used by runtime and tests
- `fine_label`: expanded taxonomy target for later detector upgrades
- `expected_text`: what the clean text should contain
- `observed_text`: what the noisy source contains
- `is_variant_only`: marks orthography variants that are acceptable in some modes

See `dataset.schema.json` for the baseline contract.
