# Day 1 D — reject ambiguous holdout checksum records (22 Nov 2026)

**Disposition: SOURCE_ONLY / controlled pilot NO-GO.** One bounded source integrity correction. This is not independent holdout custody, real model scoring, staging acceptance, or an authorization to release.

## Contract and source

- Parent [#737](https://github.com/rumman52/Shuddho/issues/737), Day 1 [#727](https://github.com/rumman52/Shuddho/issues/727), D custody blocker [#665](https://github.com/rumman52/Shuddho/issues/665), repository `AGENTS.md`, `docs/coworker-roadmap/SPEC.md` and the Part 01 Foundation prompt.
- **Pinned source:** `main=4b055bcaab83151cca1478ab52ee121f5b2f74f7`; exact TDD-only revision `41ea1b143521a7bf346e6df5e814a91b67e35533`; [draft PR #873](https://github.com/rumman52/Shuddho/pull/873).
- **Actual defect:** `load_suite()` compared only `.decode('utf-8').split()[0]` against the frozen holdout manifest's SHA-256. The checksum companion could name the wrong file, omit the filename, append a second checksum or extra fields, yet be accepted. A zero-byte checksum raised `IndexError` instead of the existing controlled `ValueError`.
- **RED evidence:** [GitHub Actions #44938484991](https://github.com/rumman52/Shuddho/actions/runs/44938484991), test-only revision `41ea1b143521a7bf346e6df5e814a91b67e35533`; `test-and-build` Python step **5 failed / 3,541 passed / 105 skipped / 6 warnings**. The empty case yielded `IndexError`; four other syntactically malformed checksum records incorrectly passed. All five regressions are in `tests/test_pilot_workflow_eval.py`.
- **Correction:** read the already-bounded non-symlink checksum file once and compare its complete UTF-8 bytes as text with the exact canonical `<pinned sha256>  holdout_integrity.json\n` record. This rejects empty, extra tokens, second lines and filename substitution. The frozen manifest bytes/digest, corpus, case counts, source snapshots, D access isolation flag and user-facing APIs do not change.
- **Expected GREEN:** Five new negative cases plus frozen-corpus validation, development 40/40 calibration and the mandatory final-head CI. Final-head CI remains **unverified until observed**. CI validation does not prove real D custody.

## Release and operator boundary

- Staging `shuddho-staging` was read-only observed at PostgreSQL 17.11 with Alembic `0070`, behind source `0072_merge_0071_heads`; no migration or restore performed.
- Render service inventory: API staging at deployment source `0e0b662fad0a02817a79a4514abba8f94e0ad022` (14 Nov), auto-deploy off. No dedicated persistent coworker worker discovered in the connected workspace; no paid worker provisioned.
- Vercel connected Git-project inventory has no Shuddho-linked project. ProductOS active project is unrelated, untouched. No PostHog events, flags or privacy authorization are inferred from connector availability.
- **BLOCKED D01.T03 / D01.G01:** C and repository admin must provision repository-scoped protected GitHub App identity, record exact-head governance pass; command `uv run --locked --extra coworker python scripts/reconcile_main_ruleset.py --repository rumman52/Shuddho --expected-main-sha "$(git rev-parse origin/main)"` is dry-run verification, not authority to apply policy.
- **BLOCKED D01.T04 / D01.G02:** Authorized admin and independent reviewer must reconcile native ruleset `27324410` and prove rejected unreviewed/failing PR plus accepted independently reviewed passing PR.
- **BLOCKED D01.T05–T07 / D01.G03:** C+Founder must confirm staging workspace/host, approve resource/billing/data handling and carry out isolated DB+storage backup/restore, owner A/B read/denial, source/schema pairing and real API-worker execution. No service update authorized.
- **BLOCKED D01.T09 / D01.G04:** Human D must replace developer-readable candidate cases, freeze independent custody with developer-denial and custodian-positive access evidence. No same-repository fixture establishes blind holdout.
- **BLOCKED D01.T10 / D01.G05:** Founder+C must approve bounded provider, rate, cost, concurrency, retention and rollback; distinct written Founder+Owner C exact-release pilot decision remains absent.
- No numeric Day 1 ledger promotion: v4 `18/100` task and `5/54` exit PASS counts are dated observations, not recalculated from today's evidence.

## Reproduce and resume

```bash
git fetch origin
uv run --locked --extra coworker pytest -q tests/test_pilot_workflow_eval.py
uv run --locked --extra coworker python -m scripts.pilot_workflow_eval --validate-only
uv run --locked --extra coworker python -m scripts.pilot_workflow_eval --calibrate
```

No local clone/test execution is claimed from this tool session (the sandbox has no GitHub DNS). GitHub Actions provides the recorded RED and, after this change is submitted, the new exact-head candidate check. Keep PR draft until final CI and independent review; never auto-merge.
