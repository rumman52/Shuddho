# Day 8 / Prompt 04 — economics snapshot and cost reconciliation (26 November 2026)

- Issues: #734; D08.T06, D08.T08, D08.T10; [draft PR #946](https://github.com/rumman52/Shuddho/pull/946).
- Base: `43d99fd64467492a7da809cda0ae178191e53981`.
- Test-first: `3b8b94d8265ba711049ab65212cef12ace2f53dd`; source: `0281cd8d2eac81e7fe44a84a4fdd01c15950bcb1`.
- Existing compiler parsed four input files, then reopened each pathname for SHA-256. Atomic path substitution could bind unvalidated bytes. Duplicate JSON keys, non-finite values, final symlinks and coercible schema versions could pass. The economics validator also did not reconcile totals, average, p95 and maximum.
- Fix: reuse the existing staging bounded no-follow stable-inode JSON reader (4,000,000-byte cap), parse and hash the same bytes, validate already-loaded provider policy via the same existing plan validator, and reject non-integer schema version. Keep public load helpers compatible. Reconcile aggregate average using integer ceiling division and require a feasible nearest-rank p95/maximum distribution. Category coverage, per-task caps, policy and report shape are unchanged.
- Tests: `python -m pytest tests/test_task_economics_evidence.py -q` in isolated reconstructed Python 3.13.5 source/test sandbox. RED 26 failed / 8 passed; GREEN 34 passed / 0 skips, rerun 34 passed. Git blob checks confirm the full compiler, provider policy source and test blobs match GitHub. The test harness excluded an unrelated incident-restore import and used the exact existing staging-reader/parser excerpt, not a full repository checkout; subsequent attempt to reconstruct the entire dependency failed hash verification and was not used. No claim of integrated or staging results. Downstream scale-review fixture inspected: aggregate category total 4362 / 4, ceiling 1091; p95/max 1400, consistent.
- Exact-head mandatory CI and distinct human review remain necessary. Current source CI run [45778584298](https://github.com/rumman52/Shuddho/actions/runs/45778584298) queued at observation; documentation changes require new head verification.
- Residual: aggregate consistency is not source authenticity; separate operator custody, 80 actual approved first-run receipts, per-run usage/prices/quality and exact release readback remain mandatory. A 4 MB read bound is now applied to these previously unbounded inputs; operators must keep reviewed evidence within it. Existing provider-policy CLI uses its prior separate parsing path outside this slice. No paid run, deployment, migration, production activation, telemetry or hosted write.
- Next: run `uv run --locked --extra coworker pytest -q tests/test_task_economics_evidence.py tests/test_core_agent_observability.py tests/test_cohort_scale_review.py` in a full exact checkout, inspect mandatory CI and obtain independent review. Reconcile shared progress notes before protected merge. Preserve Day 7 natural firings, staging and approval blockers.

| Axis | Status |
|---|---|
| Implementation | Source patch committed, isolated focused tests green |
| Repository verification | Pending exact final-head CI and distinct human review |
| Operated staging / independent acceptance | BLOCKED_EXTERNAL |
| Production qualification / activation | NO / NO |
