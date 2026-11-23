# D02.T09 / D02.G04 — Private object archive evidence intake: inode-bound files

**22 November 2026 (Asia/Dhaka). Source/repository evidence only. Controlled pilot NO-GO.**

## Contract and owner

- **Foundation source:** uploaded Part 01 of 05, p. 1 (one owned English PDF with recovery is the Part 02 handoff), p. 5 (preserve exact RED/GREEN CI and distinguish hosted acceptance); [Day 1 #727](https://github.com/rumman52/Shuddho/issues/727), [Day 2 #728](https://github.com/rumman52/Shuddho/issues/728), parent [#737](https://github.com/rumman52/Shuddho/issues/737).
- **Owners:** A for source tests and implementation; C for operated staged archive/recovery and protected receipt custody; D independent reviewer/evaluator; Founder+C for infrastructure budget, privacy, and pilot release.
- **Base main:** `4eee61c4389b507b95670203618c0ed980d5ccf8`. Branch `fix/day2-private-object-restore-archive-intake-20261122`. [Draft PR #896](https://github.com/rumman52/Shuddho/pull/896).
- **Existing interface:** `scripts/staging_object_backup.py::_manifest(directory)`, `restore_store(...)`, `_read_private_bytes(path,size)`; no public schema, model, object key, signature or storage-provider contract changes.
- **Red evidence:** test-only `0c9d66b048a7535d0dc9801f8a4b5eaed787bdce`, [Actions #45049934543](https://github.com/rumman52/Shuddho/actions/runs/45049934543) mandatory Coworker **9 expected FAILED / 424 PASSED**. Failures isolated to new local adversarial tests, not skipped, import or collection failures.
- **Prior defect:** Manifest `is_symlink/is_file` then `Path.read_bytes` had a time-of-check/time-of-use symlink window and unbounded permissive JSON, accepting duplicate status or SHA fields. Object directory and files were prechecked separately then reopened; bytes could be substituted or changed during read despite later matching a digest.
- **Corrected contract:** Open the archive root, manifest and objects subdirectory using `O_NOFOLLOW` and held directory descriptors. Restrict manifest to 16 MiB including in-flight growth, reject ambiguous duplicate keys and nonfinite numeric tokens. Read each blob using one no-follow descriptor and its manifest byte ceiling; compare pre/post size, nanosecond mtime/ctime, and the count of consumed bytes before trusting its SHA-256. Anchor leaf lookup to the held objects descriptor; do not reopen a prechecked pathname. Preserve empty zero-byte objects (where permitted), source/target fingerprint separation, signed manifest SHA over exact input bytes, total byte cap, ordering, MIME, two-owner isolated API and original-0070 baseline logic.
- **Offline reproduction:** `uv run --locked --extra coworker pytest -q tests/test_staging_object_backup.py tests/test_staging_day2_archive_attestation.py tests/test_staging_preseed_baseline.py tests/test_staging_backup_restore.py`. Then collect final-head `test-and-build`, `coworker`, `browser-qualification`, `Frontend tests and builds`, `PostgreSQL 18 staging compatibility`, ancestry and merge gate jobs. A PR `governance-audit` skip does not prove a main-push governance pass.

## Blocked operational handoff

**C + Founder:** authorize selected Supabase/Render project and workspace, a genuinely isolated PostgreSQL/private-S3 target, protected backup custody, managed owner A/B identities, dedicated worker/Temporal pairing, exact candidate SHA, concurrency/resource budget, retention and privacy before using the guarded backup/restore runbook. Supabase staging currently PG17.11 Alembic `0070` while source head is `0072_merge_0071_heads`; Render staging API still serves old `0e0b662fad0a02817a79a4514abba8f94e0ad022`, autoDeploy off, no persistent worker visible. Once authorized, operate preseed `attest-original` before modification and separately run `prepare` then `verify`, storing immutable raw SQL/object/owner-access receipts privately; sanitized receipt references only in issue/PR. One full owned PDF recovery and denied foreign reads require actual hosted evidence.

**Repository administrator and independent reviewer:** install protected GitHub App client ID/private key in reviewed secret store and reconcile live ruleset `27324410` to one independent approval and strict first-party `test-and-build`, `coworker`, `ci-merge-gate`. Prove unreviewed/failing rejection and independent reviewed acceptance. Do not bypass review.

**Human D and Founder:** establish independently blinded holdout, developer denial, real recovery measurements, and exact release signoff. No user/pilot admission without independent D and Founder+C release GO. PostHog capture and paid model use remain off without privacy/budget approval. The historical v4 18/100 task passes, 5/54 exit passes, 0/10 accepted days remain dated; this source-only PR grants no operated PASS.

## Evidence levels

| Level | Disposition | Needed |
| --- | --- | --- |
| Implemented | Source patch proposed | Exact PR head |
| Repository-verified | Pending full CI and independent review | Required exact-head job results |
| Hosted staging-verified | BLOCKED | Authorized owner A/B+DB+object+Temporal raw receipts |
| Qualified/activated | NO-GO | Governance, blinded D cases, recovery, Founder+C release digest |

No live services, schema, paid inference, PostHog events, D corpus, secrets, user data, provider configuration, production flags or pilot enrollment modified.
