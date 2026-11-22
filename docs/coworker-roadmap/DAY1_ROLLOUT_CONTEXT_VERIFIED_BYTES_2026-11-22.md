# Part 01 — staging release context is bound to verified rollout bytes

**22 November 2026 (Asia/Dhaka) · SOURCE_ONLY / controlled pilot NO-GO.** Scoped Day 1 release-identity source guard for **D01.T05 / D01.G03**. These acceptance rows remain **ACTIVE / not PASS** because the operator's deployed service revisions, isolated restore, capacity and private receipts are not present.

## Evidence-backed task contract

| Field | Record |
| --- | --- |
| Parent and authority | [#737](https://github.com/rumman52/Shuddho/issues/737), [#727](https://github.com/rumman52/Shuddho/issues/727), attached Rukh AI Foundation Part 01 pp. 2–5 |
| Owner, prior → new state | C (runtime/release identity), **ACTIVE → ACTIVE**; source guard added, hosted qualification missing |
| Reviewed source base | `main=b5b7805c37a1a9c2bb3d319bafcec85df8f77e99` |
| PR | [draft #884](https://github.com/rumman52/Shuddho/pull/884), `fix/day1-rollout-evidence-one-read-20261122` |
| Reproduction commit | `8c062a373d515bea1b3e2b05aaf44b4bcfbe1357` |
| Evidence class | GitHub Actions test-only RED, then exact-head CI when available; NOT operated staging, native-review evidence, signed Founder approval or independent custody |
| Interfaces | `scripts/staging_release_evidence.py::release_context`, `tests/test_staging_release_evidence.py`; no database, app schema, API or rollout activation changes |

### Reproduced failure and root cause

`release_context` parsed `rollout_path.read_text` and then independently computed `sha256_file(rollout_path)` by reopening the path. An intervening local rewrite bound the first release ID to the second version's hash. Python's permissive JSON parser also accepted duplicate keys, `NaN` and overflowing `1e999` values, while symlink and oversized manifests lacked fail-closed limits.

**RED:** [CI #45019552298](https://github.com/rumman52/Shuddho/actions/runs/45019552298), exact test-only SHA `8c062a373d515bea1b3e2b05aaf44b4bcfbe1357`: **7 expected failures, 3,612 other Python passed, 105 skipped, 6 warnings**. One case asserted the mismatched digest, and six previously accepted invalid input scenarios reported `DID NOT RAISE StagingReleaseEvidenceError`. This is test evidence of a source defect, not a proven production attack.

### Smallest correction and mandatory checks

- Read one `O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK` file descriptor with `fstat` regular-inode check and **1 MiB maximum** (read ceiling + 1 catches post-`fstat` growth). No second pathname read for digest.
- Parse and hash precisely that byte sequence, reject duplicate keys at any depth and non-finite JSON values, maintain the exact release ID, deployed full SHA, and prepared/verified context behavior. Retain `sha256_file` for callers that explicitly need only a file digest.
- This does not authenticate the human who supplied a manifest or verify an immutable server-side release. A new, independently captured and approved hosted readback is still required.

Relevant commands after checkout (with locked coworker dependencies):

```bash
uv run --locked --extra coworker pytest -q tests/test_staging_release_evidence.py tests/test_staging_backup_restore.py
uv run --locked --extra coworker pytest -q tests/test_day1_ruleset_drift.py tests/test_day1_staging_migration_drift.py
```

The full GitHub Actions test-and-build, coworker, browser, frontend, PostgreSQL 18, ancestry and merge-gate jobs must be read from the *final* corrected PR head. No local full-suite result is claimed. A PR-only governance-audit skip is not proof that the main-push audit passes.

### Explicit blockers and operator resume

**C / administrator:** effective native ruleset `27324410` still requires zero reviews and no CI checks. Configure protected repository-scoped GitHub App client ID/private key in approved environments and reconcile only after reviewed fingerprints. Prove independently denied unreviewed/failing and accepted reviewed passing revisions. No admin mutation was authorized here.

**C / Founder:** Supabase `shuddho-staging` PostgreSQL 17.11.0.003 is at Alembic `0070`, behind checked-in `0072_merge_0071_heads`; Render `shuddho-api-staging` has auto-deploy off and a historical November 14 release, with no confirmed persistent worker. Approve and identify actual staging project, budget, capacity, identity, private storage and isolated database backup/restore destination before running a real probe. Required HTTPS API + PostgreSQL/Temporal/private object and two-owner negative reads remain unproven.

**Human D:** outside-repository access-controlled holdout and denial of developer access must be independently demonstrated; 40 developer-readable candidates are not a blinded corpus ([#665](https://github.com/rumman52/Shuddho/issues/665)). **Founder and C:** exact signed release-digest GO/NO-GO and controlled pilot admission require their own decisions. PostHog private telemetry consent and Vercel project binding not established.

**Resume:** C independently captures and privately stores the approved rollout manifest and deployed API/worker source revision, runs the read-only source `release_context` from exact release code, compares the digest against the signed candidate and performs the isolated archive+restore and two synthetic-owner access proof under the existing staging runbook. Record sanitized receipt IDs and source SHAs; do not promote D01.T05/G03 to PASS without those operated outcomes.

No secrets, migrations, paid resources, external sends, production or pilot flags, telemetry activation, or replacement holdout data were changed. The historical v4 denominator remains 100 tasks / 54 exits; no task PASS was credited from this patch.
