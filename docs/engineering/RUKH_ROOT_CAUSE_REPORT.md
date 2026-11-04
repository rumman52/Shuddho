# Rukh AI root-cause report — Coworker quality gate

## Symptom
Main CI run #41768410772 failed `tests/test_coworker_quality_eval.py::test_curated_multilingual_quality_fixture_passes` with `pass_rate=0.8333` instead of the required 1.0. The same gate failed in the heavy Coworker job.

## Confirmed causes
1. `scripts/coworker_quality_eval.py::strings` only traversed strings, dictionaries and lists. Numeric JSON leaves were discarded. The spreadsheet fixture's numeric values 120 and 80 were therefore incorrectly counted as missing required facts even though they were present in typed numeric cells.
2. The image-prompt fixture required the literal phrase `no text or logos`, while its reference draft said `No text, logos or visible branding.`. The fixture contradicted its own exact required-term contract.

## Test-first evidence
A regression test changes the spreadsheet's 120/80 cells to integral floats, expects the required facts to pass, then changes 120.0 to 121.0 and expects 120 to be missing. It also asserts booleans are not serialized as numeric facts.
- RED: PR run #41780272070 failed the new regression at required-fact preservation, alongside the existing 0.8333 aggregate failure.
- Fix: numeric leaves are now included using stable numeric text; booleans and non-finite floats are excluded. The image fixture now contains `No text or logos`; its required-term list is unchanged.
- GREEN evidence at the latest checkpoint: exact-head test-and-build reports 1,743 passed, 73 skipped, 6 warnings. Heavy Coworker CI was still in progress.

## Guardrails preserved
The 1.0 pass-rate and required-fact-recall thresholds were not changed. No task schema, provider contract, feature flag, secret, database, deployment or production setting was changed.
