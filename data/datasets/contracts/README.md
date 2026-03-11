# Dataset Contracts

Each dataset split should be line-delimited JSON with explicit fields.

Core record shapes:
- detector example: `input_text`, `token_labels`
- corrector example: `source_text`, `target_text`
- evaluation example: `text`, `expected_subtypes`

See `dataset.schema.json` for the baseline contract.

