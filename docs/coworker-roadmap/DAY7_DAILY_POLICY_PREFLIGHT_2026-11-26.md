# Prompt 04 / Day 7 — validate daily briefing policy before preparation (26 November 2026)

- Scope: D07.T03, D07.T09, D08.T07; issues #733/#734; [draft PR #951](https://github.com/rumman52/Shuddho/pull/951).
- Base: `43d99fd64467492a7da809cda0ae178191e53981`.
- Tests first `810e363be91a9247ff2a6d295b17521ef042e761`; source `eb2adf4d7b2fd827ca9b98ae1451fd06c5d1e77c`; additional receipt tests `33d7a7f093578824d7abff68991c07bb170ee59d`; source `1f31e150094d43d4ae5e9829183c9753f6d8a807`.
- Root cause: matching preparation/live snapshots were treated as valid without checking the pilot calendar policy; invalid matching values could lead to state creation and two days of unusable observations. Python numeric equality also obscured invalid types in a second receipt.
- Fix: factor existing Day 7 calendar validation into one shared helper used by prepare, matched readback, two-day gate and paused-opportunity calculation; require exact daily fields/empty weekdays, valid IANA zone, strict integer calendar values, valid distinct quiet-hour clocks, skip overlap, exact integer 3600-second catch-up. Validate both receipts. Existing non-pilot runtime schedule flexibility, API/UI semantics, goal scope, version pins, expiry and DST observation checks are unchanged.
- Focused isolated test: `python -m pytest -q test_probe.py`, copied prepare/readback functions and shared calendar validator with synthetic HTTP, environment and writer boundaries, RED 16 failed / 1 passed, GREEN 17 passed / 0 skipped. `python -m py_compile probe.py staging_day7_two_day_gate.py` passed. This is not a full repository checkout or a real Temporal firing. The three additional repository tests for second-receipt numeric type drift are committed but full gate execution remains pending. One existing unapproved-source test fixture now supplies valid explicit weekdays and quiet hours; its original denial assertion is unchanged.
- Exact-head required CI and distinct independent review required. Prior source head CI [45779506777](https://github.com/rumman52/Shuddho/actions/runs/45779506777) pending at readback. Documentation changes require final-head CI.
- No live state preparation, worker start, provider calls, notification sends, schema, hosted data, billing, deployment or activation. A valid preparation does not prove owner approval, natural timer origin, authenticated delivery or release acceptance. No new scheduler. Preserve original rollout gates. Next: full exact checkout and `uv run --locked --extra coworker pytest -q tests/test_staging_pa10_scheduled_profile.py tests/test_staging_day7_two_day_gate.py tests/test_automations.py`; review, protected merge and approved staging procedure.

| Axis | State |
| --- | --- |
| Source | Committed, isolated predicate tests green |
| Repository | Pending exact final-head CI and human review |
| Operated staging | BLOCKED_EXTERNAL |
| Independent acceptance / production / activation | No / No / No |
