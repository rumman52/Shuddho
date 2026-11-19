# Prompt 3 / Days 3–6 — release-bound hosted evidence verification

**Date:** 2026-11-19 (Asia/Dhaka). **Status: source-only verification tool, staging NO-GO.**

This plan is an executable follow-up to [PR #787](https://github.com/rumman52/Shuddho/pull/787), [PR #793](https://github.com/rumman52/Shuddho/pull/793), and the [November 19 continuation ledger](../../coworker-roadmap/PROMPT3_DAYS3_6_CONTINUATION_2026-11-19.md). It does **not** close any of the hosted Days 3–6 rows.

## Implementation

`scripts/staging_days3_6_acceptance.py` reconciles six separately captured operator inputs: `--freeze`, `--day3`, `--day4`, `--day5`, `--day6`, and `--review`. It refuses any row that lacks a **matching full 40-character Git SHA, frozen manifest hash, exact staging API/worker deployment IDs, database revision, provider/model, two distinct synthetic owners**, real hosted-operation references, complete post-action counts, and an independent review reference. Rows from a different release cannot be combined.

It requires:

- **Day 3:** source-selected English and Bangla answers with model request IDs, verified citations, foreign-owner denials and a separate provider request revoked *during* inference, with no stale visible delta, no stale persistence and zero AgentRuns/outbox before and after.
- **Day 4:** Bangla re-edited/reapproved digest, edit→approval→Start order, one added run/one outbox effect, exact retry, and 409 on concurrent Start/edit with no new effects.
- **Day 5:** three distinct model-backed runs sharing source/prompt/model/budget (no memory, exact fact v1, corrected fact v2); a materially different observed fact, unselected-memory exclusion, five forbidden-pin denials, and historical v1 replay without a new effect.
- **Day 6:** both workflows in both languages; owner A opens and hashes native DOCX and PDF files, owner B is denied each, three confirmed citations per research case, 40 independently recorded development invocations (10 per workflow/language; at least 9/10 quality score 7/8 per cell); one same-run restart/reconnect with zero new effects; unsent email draft and **independent external provider-side** 0→0 send audit.
- **D verification:** non-operator reviewer, platform readbacks and verified timestamp after all four days. This is a *consistency check on supplied receipts*, not proof of the reviewer's identity or real platform access.

The machine verdict is intentionally `evidence_internally_consistent_not_live_attested`, **never PASS/GO**. A manually synthesized JSON file can satisfy a JSON contract; only actual independent, authenticated API/Render/Temporal/Supabase/S3/provider readbacks and source code comparison can substantiate the claims.

## Operator invocation (only after the separately authorized staging release)

All input files must be separately verified, redacted and stored in a private local directory. **Do not commit private evidence, cookies, bearer tokens, model prompts, owner content, SMTP metadata or secrets.** The tool accepts only small on-disk files (2 MiB maximum each), rejects symlinks and overwrites, and uses private atomic output creation.

```bash
export SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true
export SHUDDHO_STAGING_ALLOW_DAYS36_VERIFICATION=true
uv run python -m scripts.staging_days3_6_acceptance \
  --freeze /secure/receipt/freeze.json \
  --day3 /secure/receipt/day3.json \
  --day4 /secure/receipt/day4.json \
  --day5 /secure/receipt/day5.json \
  --day6 /secure/receipt/day6.json \
  --review /secure/receipt/independent-review.json \
  --expected-revision YOUR_FROZEN_40_CHARACTER_LOWERCASE_GIT_SHA \
  --output /secure/receipt/days3-6-consistency.json
```

A reproducible **source-only** test suite is mandatory in GitHub Actions:

```bash
uv run pytest -q -rs tests/test_staging_days3_6_acceptance.py
```

Its positive fixture consists of wholly synthetic timestamps, fake deployment identities and fake receipt references. It proves only that the verifier checks expected fields; it does **not** increase the number of real staging cases.

## Independently measured staging baseline (NOT operation evidence)

On 2026-11-18, Render service `srv-dav98otg1s2s73cod4gg` still deployed commit `0e0b662fad0a02817a79a4514abba8f94e0ad022` (November 14), auto-deploy disabled. The staging Supabase project `bsmbvjenpvcyfjzwtuax` reported migration `0070`, no users, AgentRuns, artifacts, worker instances or storage objects. The connected Vercel scope reported only project `ali`, and no authenticated Shuddho browser acceptance. The latest CI for PR #793 failed a Day 6 test due to a `TaskBrief` variable shadowing the saved report; subsequent `main` source contains the renamed `reviewed_brief` and PR #794's Coworker CI succeeded, but neither demonstrates a live deployment or satisfies the separate governance gate.

## Non-negotiable release blockers and next steps

1. The authorized release owner must approve the **exact costs and duration** of provider/worker resources, resolve the Day 2 #728 prerequisite, reconcile migration and staging runtime flags, and freeze the **same API + worker + schema + provider/model SHA**. Do not treat this plan or the user's general completion request as an open-ended purchase authorization.
2. The authorized operator uses two real *synthetic* accounts to perform and record live requests, time-bounded revocation, concurrent Start/edit, memory corrections/denials, all 40 development cases, worker reconnect and private downloads, plus separately verified *external provider* zero sends.
3. An independent reviewer verifies sources, actual file bytes, source/manifest hashes, owner-B denial, provider IDs and release ownership against the live systems, then issues a separate signature/receipt.
4. Run the consistency validator, preserve the redacted checks and **independently** close each individual row only after demonstrated results. Any code, schema, model, source or worker-deploy change reopens affected rows.

**No deployment, paid worker, Supabase migration or outgoing send is performed by this PR.** The default remains NO-GO.
