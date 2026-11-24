# Part 05 / Day 10 — signed release ledger JSONL trust boundary

**23 November 2026 • PR [#901](https://github.com/rumman52/Shuddho/pull/901) • SOURCE-ONLY / pilot NO-GO**

## Objective, evidence and scope

The canonical release ledger is a hash-chained, HMAC-verified sequence used for `stop_rollout`, `hold`, recovery, rollback, stage and provider policy controls. Before this change, `scripts/cohort_release_ledger.read_entries` used unbounded `Path.read_text(...).splitlines()` and permissive `json.loads`. A raw row with an earlier `"event_type":"stop_rollout"` and later `"event_type":"hold"` was interpreted as the original signed hold. The signed canonical dict was unchanged: signature success does **not** authenticate raw ambiguous key material. The reader also followed a final symlink, admitted nonfinite numeric values and propagated filesystem exceptions for nonregular files.

Owner: A (source implementation); independent B code review, C operated infrastructure verification and D custody/holdout qualification remain separate. Base main `e8d3e3c8180eaba2065468bf31f2dba96d682664`. The independent source of truth is Part 05 of the user handoff, especially pp. 1–7 and the final handoff requirement. This PR does not alter release decisions, capabilities, HMAC algorithm, schemas, ledger append signatures or enrollment.

## Existing interfaces, implementation contract

- Only `scripts/cohort_release_ledger.read_entries(path: Path) -> list[dict]` is changed. Reuse `scripts.ruke_pilot_eval.strict_json_loads` and `MAX_BYTES` (4,000,000 bytes), already used by Day 9 release/holdout receipts.
- Open a single final-component no-follow descriptor with `O_NOFOLLOW` and `O_NONBLOCK`; validate `fstat` is regular, before iterating bytes; missing file still returns `[]`. Do not precheck `Path.exists` or follow a linked ledger.
- Read a maximum of `MAX_BYTES + 1` bytes per physical row, reject overlong rows, and enforce a generous **64 MiB total history** cap, including if a regular file grows after `fstat`.
- Reject duplicate keys/nonfinite JSON, invalid UTF-8 and non-object ledger rows. Translate filesystem read failures to `ReleaseLedgerError` with line number where applicable. Keep JSONL row order, first-run history and old HMAC-signed canonical rows compatible. Fail closed if no-follow reads are unavailable.
- No new database/ledger/orchestrator/secret, no spending, no download or external egress. Rollback is to restore reviewed source after preserving the first failing evidence; **never** edit old operator history to make tests pass.

## Actual test-first verification

The production fix was committed *after* the failing tests, not before:

1. Test commit `f9654ef72e317623b6059c17aa28041d11d0c6ef` added six synthetic cases to `tests/test_cohort_release_ledger.py`. The first [GitHub Actions run #45225405097](https://github.com/rumman52/Shuddho/actions/runs/45225405097) observed **4 fail / 3,728 pass**; the oversized case had a malformed escaped-newline fixture and was **not** credited as a valid RED.
2. Test correction `c092becf7a29131ddecd14015eb61afc0aa72adb` repaired the fixture, still before production code. [Test-only Actions #45225809032](https://github.com/rumman52/Shuddho/actions/runs/45225809032) observed **5 fail / 3,727 pass / 107 skip / 6 warnings**, all five expected failures: duplicate signed event, nonfinite sequence, final symlink, oversized valid JSONL row, nonregular path. The missing-ledger compatibility test passed.
3. Production commit `cfbe50b4ce30431e56d2f991d7119404cd72d28c` introduced one bounded descriptor-based reader. The [source-head Actions #45226323848](https://github.com/rumman52/Shuddho/actions/runs/45226323848) `test-and-build` job passed: **3,732 Python passed / 107 skipped / 6 warnings**, plus **551 JavaScript passed**, with no observed Python or build failures. This proves repository source behavior, **not** 20 operated scenarios. Exact final doc-head CI must be separately read back before claiming overall PR checks success.

## Boundaries, residual risks and handoff

This narrow parser fix protects reading **ledger JSONL history**; the independent `load_json_object` reads used when *appending* events and the `file_sha256` reopen/hash path are still separate trust boundaries and deserve a distinct review. `O_NOFOLLOW` protects the final symlink, not every ancestor symlink, hardlink, malicious concurrent file mutation or signed-ledger append races. The 64 MiB cap can intentionally block extremely large existing histories: investigate/retain original history, do not silently truncate. HMAC authentication requires protecting the operator-held key; this PR does not prove authentic C/D platform receipts.

**Blocked qualification:** independent human D has not provided protected 40 distinct first attempts, 80 blind scores, 40/40 security or 20 independently operated PostgreSQL/Temporal/private object-store recovery traces on one frozen release. Exact API/worker/schema/provider identities, all 43 boolean flags including false, live quality, controlled rollback, golden conversation, distinct Founder+C signed decisions and separately authorized 5–10 HTTPS member probes remain unobserved. Historic v4 baseline: 18/100 tasks, 5/54 exits, 0/10 days accepted; source-only PRs do not increment it.

Read-only connection inventory 23 November: Supabase `shuddho-staging` ACTIVE_HEALTHY PG 17.11.0.003, Alembic `0070` (not deployed source schema); Render declined service inventory without user-confirmed workspace; Vercel linked `ali` to unrelated `hero-dev-code`, ProductOS only `Dust2Glow`, PostHog default 675660 no ingested events and no Shuddho identity proven, Linear MD-5 through MD-8 are issue references. Main GitHub ruleset 27324410 allows **zero approving reviews** and has **no required status-check rule**. Admin must enforce native CI/review and demonstrate a blocked negative merge.

**Completion levels**: implemented yes at source fix commit; repository-verified Python/build yes at source head, exact final-head pending; staging-verified **no**; production-qualified **no**; activated **no**. No merge/deployment/migration/telemetry/customer operations performed. Independent review is still required.
