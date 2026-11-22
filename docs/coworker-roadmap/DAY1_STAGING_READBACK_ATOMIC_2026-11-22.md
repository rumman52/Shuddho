# Day 1 C — stage migration readback consumes one bounded regular inode

**22 November 2026 (Asia/Dhaka) · SOURCE_ONLY / controlled pilot NO-GO.** This source-only correction supports the Part 01 Foundation evidence integrity obligations for **D01.T06** and **D01.G03**. It does not fulfill C's real private-schema inventory, independently authenticated SQL, isolated restore or run acceptance.

## Task and decision contract

| Field | Record |
| --- | --- |
| Parent issue and canonical prompt | [#737](https://github.com/rumman52/Shuddho/issues/737), [Day 1 #727](https://github.com/rumman52/Shuddho/issues/727), attached Part 01 Foundation pp. 2–5 |
| Owner and state | C / platform-security; prior **ACTIVE** → **ACTIVE** (source evidence reader improved; operated gate remains incomplete) |
| Source base | `main=92cdc1a4952239a4a676b754ebc3d1ca044c9cbd` |
| Isolated branch and PR | `fix/day1-staging-readback-atomic-bounds-20261122`; [draft PR #882](https://github.com/rumman52/Shuddho/pull/882) |
| Exact test-only revision | `551325923d3e173f1fde85fb16c4dd9909e4dd40` |
| Evidence class | Repository CI regression + code review; **not** hosted operation, human/administrator approval, backup or recovery |
| Source interfaces | `scripts/day1_staging_migration_drift.py::read_readback`, `tests/test_day1_staging_migration_drift.py`; no API/schema change |

### Root cause and reproduced RED

The previous reader checked a pathname using `lstat()`, `resolve()` and `stat().st_size`, then reopened it through `Path.read_text()`. A symlink introduced between checks and the read can substitute a different evidence file, while a growing same-inode file can exceed the prechecked 32 KiB bound without detection. This is a *potential local readback-substitution vulnerability*, not an observed staging compromise.

Two new deterministic adversarial tests reproduced the defective behavior at test-only revision `551325923d3e173f1fde85fb16c4dd9909e4dd40`: [GitHub Actions #45014367909](https://github.com/rumman52/Shuddho/actions/runs/45014367909) `test-and-build` Python **2 expected FAILED, 3,574 PASSED, 105 SKIPPED, 6 WARNINGS**. Both failed with `DID NOT RAISE MigrationDriftError`, not import/collection errors.

### Minimal fix and required recheck

The corrected reader still rejects paths resolved inside the repository and missing `O_NOFOLLOW` support. It opens once with `O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK`, verifies that same descriptor with `fstat`, caps `os.read` to 32,769 bytes, and parses the exact consumed bytes. The same `MigrationDriftError` path handles OS failures, invalid/duplicate/nonfinite JSON and invalid UTF-8. This preserves the existing outer `assess` report identity and its `staging_qualified=false` / `migration_authorized=false` invariants.

Focus and mandatory checks after the implementation:

```bash
uv run --locked --extra coworker pytest -q tests/test_day1_staging_migration_drift.py
uv run --locked --extra coworker pytest -q tests/test_day1_ruleset_drift.py tests/test_day1_staging_migration_drift.py tests/test_staging_backup_restore.py
```

GitHub Actions must finish on the exact corrected PR head; a green source suite does not count as independent authorization or operated restore. No local checkout execution is claimed here. The original RED logs remain linked.

### Operator and release blockers

- **C / Founder**: authorize actual staging workspace, isolated DB + storage restore destination, custody, retention, bounded spend, and two synthetic owner read/denial probes. Read-only Supabase `shuddho-staging` PG17.11 reports Alembic **0070**, while source head is `0072_merge_0071_heads`. Do not migrate without authenticated backup/rehearsal, runtime pairing and explicit owner decision.
- **C / Render owner**: actual staging API is inventoried; no persistent `shuddho-worker-staging` appears in the connected workspace, API latest deploy is historical, auto-deploy disabled. No worker creation or paid provisioning authorized.
- **C / repository administrator + independent reviewer**: effective native ruleset 27324410 still mandates **zero** approvals and **no required status checks**; configured App token/secret and separate denied/permitted merge controls remain absent.
- **Human D**: independent externally held 40-case holdout and true developer-negative / custodian-positive access proof remain missing ([#665](https://github.com/rumman52/Shuddho/issues/665)).
- **Founder and Owner C**: independent exact-release GO/NO-GO and privacy/model/budget approvals have not been supplied. No actual provider, production, PostHog telemetry, external send or allowlist action was performed.

**Resume action:** C captures a new non-secret authenticated SQL revision receipt outside the repository, runs `uv run --locked --extra coworker python -m scripts.day1_staging_migration_drift --readback /path/to/private/staging-readback.json --project-ref bsmbvjenpvcyfjzwtuax --source-revision "$(git rev-parse HEAD)"` on the corresponding checked-out SHA; authorizes an isolated restore only after the owner approvals and existing recovery runbook. The result must be recorded with private receipt custody and exact runtime identity. The source code patch alone does not advance D01.T06 or D01.G03 to PASS.
