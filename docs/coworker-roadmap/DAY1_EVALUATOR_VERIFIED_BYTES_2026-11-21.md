# Day 1 D — exact-byte provenance of the offline bilingual evaluator

**Disposition:** SOURCE_ONLY / controlled pilot NO-GO. This bounded patch preserves the offline evaluator; it is not a human quality run and cannot establish independently controlled D holdout custody.

## Task contract

- **Objective:** Ensure the text, scenario JSONL and calibration reference outputs scored by `scripts/pilot_workflow_eval.py` are exactly the file bytes whose declared SHA-256 digest passed validation. Block directly symlinked and oversized inputs before evaluation without consuming unbounded content.
- **Source basis:** User's five-numbered-part Rukh AI execution prompt, particularly Part 01 Day 1 D source freeze/independent custodian and Part 03 Day 6 source/artefact integrity; [primary ten-day Day 1 plan ¶141–152](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit), [CTO board #737](https://github.com/rumman52/Shuddho/issues/737), [Day 1 #727](https://github.com/rumman52/Shuddho/issues/727), [independent D custody blocker #665](https://github.com/rumman52/Shuddho/issues/665), existing [evaluation contract](DAY1_EVALUATION_2026-11-10.md), [roadmap SPEC](SPEC.md).
- **Dependency:** Initial Day 1 80 repository-grounded scenarios, frozen reviewed manifest digest, 40 development/40 candidate holdout, previous `quality_qualified=false` and `HeldoutAccessBlocked` semantics. Earlier Day 6 native export rejections already fixed on main: do not duplicate. Earlier [PR #863](https://github.com/rumman52/Shuddho/pull/863) patched the separate GitHub governance reader and merged.
- **Base SHA:** `57b0cbce15eaf5517cc6e78fff399d93faee87ad`; branch `fix/day1-evaluator-verified-bytes-20261121`, [draft PR #870](https://github.com/rumman52/Shuddho/pull/870).
- **Existing interface:** `load_suite(root:Path=FIXTURE_ROOT)->dict`, `sha256_file(path:Path)->str`, `read_outputs(path:Path)->list[dict]`, `main(argv=None)->int`. Keep all public signatures, scoring rubrics, split defaults, case matrix and source classification unchanged.
- **Implementation:** `scripts/pilot_workflow_eval.py` private file reader uses `O_NOFOLLOW` plus regular file `fstat`, and bounded `os.read`; the private `_verified` returns the *actual verified bytes*, never a path for re-open. Parse source UTF-8, cases, reference outputs, frozen suite and heldout metadata from the same byte buffers whose digest is compared. `tests/test_pilot_workflow_eval.py` adds the three regressions.
- **Pre-fix reproduction:** Existing `_verified` hashed path via `sha256_file` then returned Path; `load_suite` later called `path.read_text` and `read_outputs(path)`, and the standalone `read_outputs` followed an input symlink. Deterministically monkeypatched second-read text was incorporated under the original declared checksum. This is a source integrity bug, not a completed customer incident.
- **RED exact SHA:** `b93587ed3f987356e5285c1cfc1be5f505764647`; [Actions #44921905522](https://github.com/rumman52/Shuddho/actions/runs/44921905522) `test-and-build` **3 expected failed / 3,494 passed / 105 skipped / 6 warnings**. Root causes explicitly: hashed source text mismatch, extra unreviewed case row field incorporated, and direct symlink never rejected. The earlier test-only attempt `fbeaf1f9c074617bafa968f38e7746636bad4f63` was CANCELLED by the later test-only CI run, not a separate RED.
- **GREEN patch:** commit `3bfc83d98364080024c6eedf6db9327e986c30ff` unifies all file input reads with a bounded no-follow descriptor and uses the attested bytes. Preserve normal fixture provenance against historical Git revision independently of this offline check.
- **Tests:** Preferred real-checkout focused `uv run --locked --extra coworker pytest -q tests/test_pilot_workflow_eval.py`, then [PR exact-head CI](https://github.com/rumman52/Shuddho/pull/870/checks) Python source and added output contract, frontend, browser, PostgreSQL 18, Coworker, ancestry; governance skipped on PR never counts as native rule verification. Do not claim local focused command if unavailable.
- **Security/custody:** Source path symlink last-component and over-size boundary only. The parent directory is not independently protected; mutable checkouts remain unsuitable for D holdout. No outside credentials, heldout inputs/answers, private customer bytes, provider calls or network access. Human D alone may authorize independent heldout custody following actual access denial/positive proof.
- **Budgets and rollback:** Bound each file to 2 MB + 1 read sentinel. Model calls 0; spend 0; no new run/prompt/OS execution or outbound network. Freeze corpus manifest/40×2 cell schema. Rollback code via reviewed Git PR only, not by relabeling corrupted inputs. Existing default `--split holdout` remains blocked.
- **Host and staged state read-only 21 Nov 2026:** Supabase staging ACTIVE_HEALTHY PG17.11 and actual `shuddho_coworker.cw_alembic_version=0070`; repo migration head `0072_merge_0071_heads`. Render connected workspace `Rumman`, no owner-approved service target; Vercel `shuddho` project search empty; ProductOS only unrelated Dust2Glow; PostHog user event/recording privacy approval unproven. No live data/worker/deploy/ruleset/secret/write change.

## Evidence and final review

| Gate | State | Evidence |
| --- | --- | --- |
| Reproduction on original reader | **RED reproduced** | [Actions #44921905522](https://github.com/rumman52/Shuddho/actions/runs/44921905522): 3 failed / 3,494 passed / 105 skipped / 6 warnings |
| Source patch committed | **Implemented** | `3bfc83d98364080024c6eedf6db9327e986c30ff`; PR #870 |
| Exact final PR head | **GREEN pending readback** | [PR #870 checks](https://github.com/rumman52/Shuddho/pull/870/checks) |
| Independent submitted human review | **BLOCKED_EXTERNAL** | GitHub review identity and current-head approval |
| Staging operated and restored | **BLOCKED_EXTERNAL** | Founder+C approved DB/objects backup, isolated destinations, paired API/worker/Temporal on exact rollout, paid resource/retention choice |
| Native GitHub governance | **BLOCKED_EXTERNAL** | Administrator-owned App secrets and ruleset `27324410` genuine denied/unreviewed and permitted/reviewed merge cases |
| Independent D blind holdout | **BLOCKED_EXTERNAL** | Developer-negative and custodian-positive access to separate replaced 40-case corpus, 20 operated recovery cases |
| Pilot decision | **NO-GO** | Independent Founder + Owner C exact-release approvals and eligibility |

The recorded v4 baseline was 18/100 task PASS, 5/54 exit PASS, 0/10 accepted days, dated 19 November; it is historical. Source-only patch and merged PR counts cannot automatically increase those credited totals. Reconcile every row and its exact receipt before publishing an updated percentage.

**Next action:** A independent engineer reviews and verifies exact-head #870; C/admin stages authentic main governance and native merge tests; Founder+C approve isolated backup/restore and controlled resource/provider budget; human D replaces exposed candidates, proves external custody and operates qualified evaluation. Keep draft/unmerged until independent review and release prerequisites.
