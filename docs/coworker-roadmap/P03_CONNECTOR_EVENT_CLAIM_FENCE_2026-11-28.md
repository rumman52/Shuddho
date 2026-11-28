# Prompt 03 connector event claim fence — 2026-11-28

Scope: PA-06 / Prompt 03 additional connector and action engineering, recovery (D06.T09); source in progress. Base `52a0feb0bb0a674d0c0840a679a3941d78ef6314`.

## Defect and repair

A worker that loses its two-minute event lease can resume after another worker has reclaimed the same row. Previously bind_event_snapshots, finish_event and fail_event locked the row but did not verify which attempt owned it. An old success could mark a new attempt processed; an old failure could remove its lease and mark it retryable; old snapshot evidence could replace the current attempt's evidence. The row already persists a monotonic attempts count. Bind, finish and fail now verify the expected attempt and processing state while holding the existing row lock. A failed evidence bind returns false and stops the superseded execution before consumer admission. No migration, provider grant, external action, feature flag or release-policy change. This fences event persistence; it does not cancel an in-flight provider read or promise exactly-once consumer effects. Existing downstream admission deduplication remains necessary.

## Evidence

- Test-first commit: `2bb60599213c1f8fec2374e764de16f3e07d5cae`.
- Source: `3ee3ff20a603c58c3f23d7913b5b1c818c5a9851`.
- Regressions consolidated in mandatory `tests/test_connector_reads.py` so both explicit connected-read gate and broader coworker suite collect them.
- Local isolated reproduction used copied repository methods, real SQLite/SQLAlchemy transactions, reduced ORM models, synthetic sync/consumer boundaries. Command: `python -m pytest -q --tb=short`. RED: 4 failed, 2 passed. GREEN: 6 passed. `python -m compileall -q probe.py` succeeded. Full checkout blocked by container DNS; this is not full integration or PostgreSQL validation.
- Required remote verification: `uv run --extra coworker pytest tests/test_connector_reads.py tests/test_permission_gateway.py -q -rs`; full exact-head engineering CI and distinct current-head human review remain required. No live provider receipts or acceptance asserted.

## Release boundary

No hosted mutation, spend, deployment or provider event was performed. Recheck existing downstream idempotency separately. Prompt 03 remains unqualified until all ten authentic staging exit criteria and independent review are evidenced.

## Final-attempt recovery follow-up

The eighth claimed attempt could crash and remain processing forever because the claim query excluded all attempts >= 8. The bounded claim scan now terminalizes expired processing rows at the existing retry ceiling as failed, clears their lease and records `connector_event_claim_exhausted`. Unexpired final claims remain active. No ninth attempt and no subscription-sequence advancement. The attempt fence prevents late success from resurrecting the terminal failure.

Test-first: `4de7f769c6dea62db6b978dac1c1c0054ca03658`; source: `0dd8dbd1ea771dab1dec906c487be2a1692cb18e`. Local isolated follow-up RED 1 failed/6 passed, GREEN 7 passed; compileall succeeded. Same synthetic dependencies and full-repo limitations as above. The actual repository fixture test is in the mandatory connected-read suite.
