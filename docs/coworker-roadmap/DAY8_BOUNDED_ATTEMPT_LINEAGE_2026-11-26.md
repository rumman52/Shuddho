# Day 8 — bounded attempt lineage and canonical evidence identity (2026-11-26)

- Issue #734, D08.T08/D08.T10, [draft PR #957](https://github.com/rumman52/Shuddho/pull/957).
- Base `43d99fd64467492a7da809cda0ae178191e53981`; regression commit `2e2845bcd0c487523264be42f8127a4f941e893b`; implementation `e79b403cab334b3901bd95230ec8181ada769f2e`.
- Reproduction: a single sparse rerun ordinal can be represented in a few dozen JSON bytes but previously caused `list(range(2, max(attempts) + 1))` to allocate in proportion to the *ordinal*, not the observed receipts. An ordinal of 2**100 raises OverflowError before a controlled validation response. JSON floating-point and boolean schema versions compare equal to integer versions; unhashable schema versions raise TypeError. Leading/trailing whitespace in a run ID can evade exact identity de-duplication.
- Fix: exact integer schema version; reject padded first-run/rerun IDs before uniqueness checks; validate contiguous ordinals by max == len + 1, after existing distinct-integer >=2 checks. The equivalence follows because n distinct integers >=2 with maximum n+1 must occupy all n available positions. Legitimate out-of-order receipts remain valid, v1 stays parseable but ineligible, v2 retains all existing acceptance gates. Complexity is linear in observed attempt count, constant extra allocation in the sequence check.
- Local isolated copied-predicate tests: `python -m pytest test_predicates.py -q`: RED **15 failed / 9 passed**, GREEN **24 passed / 0 skips**. `python -m py_compile predicates.py` passed. Exhaustive equivalence check over 255 nonempty distinct subsets of ordinals 2..9 passed. Actual production diff re-read against tested predicates. Full excerpt transfer failed integrity verification and was discarded; these are predicate tests, not a full checkout or full comparator execution. Sixteen added repository regression cases are committed, including a valid out-of-order sequence; full CI pending.
- No production or hosted write, provider calls, evaluation budget, privacy decision, telemetry enablement, database migration or new acceptance credit. No thresholds relaxed.
- Remaining: full exact-head CI and distinct reviewer; live 80 first attempts and authentic receipts still require budget and approved worker; freeze blocked. Run `uv run --locked --extra coworker pytest -q tests/test_core_agent_observability.py` in full checkout, inspect all mandatory CI jobs and merge only via protected rules. Source CI [45785443629](https://github.com/rumman52/Shuddho/actions/runs/45785443629) queued at observation; documentation head requires its own CI.

| Axis | Status |
|---|---|
| Implementation | Source patch committed; isolated predicates tested |
| Repository verification | Pending exact-head CI and distinct review |
| Operated staging/independent acceptance | BLOCKED_EXTERNAL |
| Production/activation | NO / NO |
