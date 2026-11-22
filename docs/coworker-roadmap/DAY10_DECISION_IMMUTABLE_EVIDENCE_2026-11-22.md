# Day 10 — immutable evidence digests and first release decision (22 November 2026)

**State: SOURCE-ONLY implementation; controlled pilot NO-GO.** Scoped to Part 05 D10.T04/D10.T10 (parent #737, Day 10 #736), and follows merged Day 9 evidence integrity PR #876. This work is not a human/custodian receipt, operated staging rollback, approval, or admission.

## Task contract

- **Objective:** Each SHA-256 reported by the Day 10 release-decision CLI must identify the exact input bytes that produced its decision; an existing decision artifact must never be overwritten by a rerun.
- **Dependencies/current evidence:** Part 05 release/handoff contract, `scripts/day10_release_decision.py` and `scripts/ruke_pilot_eval.py`; Day 9 PR #876 already merged as main `92cdc1a4952239a4a676b754ebc3d1ca044c9cbd`. Governance #484 and independent D custody #665 still block qualification.
- **Base:** `main` `92cdc1a4952239a4a676b754ebc3d1ca044c9cbd`.
- **Branch/PR:** `fix/day10-decision-evidence-immutable-digests-20261122`, [#881](https://github.com/rumman52/Shuddho/pull/881).
- **Existing interface reused:** Day 9 `_read_json_and_sha256` (descriptor-based bounded, non-symlink reader) and `immutable_write` (exclusive create, private 0600 mode). No new ledger/schema.
- **Files:** `scripts/day10_release_decision.py`, `tests/test_day10_release_decision.py`, this contract and `PROGRESS.md`.
- **Interface:** Adds `read_json_with_sha(path: Path | None) -> tuple[dict | None, str | None]`; retains `read_json` and `sha256` read helpers for compatibility. Neither receipt alters the canonical cohort gate.
- **Acceptance:** (1) swapped pathname hash cannot change the digest of already parsed rollout; (2) first-run report hash matches original parsed first-run JSON, not a later pathname read; (3) existing `--output` is not replaced, returns nonzero; (4) new report is mode 0600 and requires a fresh path for every rerun.
- **Reproduction:** Four synthetic tests committed first at `7b7d1337b2e9ceb16e017b1179be124dcd40c33a`. The original implementation read and hashed two inputs from separate opens and wrote output with `Path.write_text`. Test-only workflow was superseded by the follow-up production commit; **do not claim an observed RED result from cancelled CI**.
- **Expected failure:** invalid/linked/oversized evidence stays rejected; collision on output returns explicit `decision_artifact_write_failed:FileExistsError` without writing a false success report. Error output has `pilot_activated=false`.
- **Test commands:**

```bash
uv run --locked --extra coworker pytest -q tests/test_day10_release_decision.py tests/test_ruke_pilot_eval.py tests/test_cohort_release_gate.py tests/test_staging_release_freeze.py
uv run --locked --extra coworker python -m scripts.ruke_pilot_eval preflight
uv run --locked --extra coworker python -m scripts.release_contract_check
```

- **Secrets/authority/egress:** Only synthetic test data in repo; real Founder/Owner C, D and production readbacks remain independently held. No provider calls, migrations, egress, PostHog capture, Send, purchase or schema migration.
- **Budgets/retries/cancellation:** Existing `MAX_BYTES` bound and read-only decision, no paid dispatch. Repeat evaluation must use a new report path and preserve lineage.
- **Default-off/rollback:** All existing 43 capabilities and cohort admission stay unchanged; revert this code patch separately only through reviewed source release, preserving original decision files.
- **External prerequisites:** Independent D custody and 40 first attempts with 80 blind reviews, all-security-true, 20 authenticated operated recovery receipts; exact API/worker/SQL/model+43-flag readbacks and live quality gates; native required checks and independent review; separate Founder and C approval and a distinct cohort authorization.
- **Out of scope:** Authenticating operator-created JSON as a real platform event, deploying staging, changing account allowlist, weakening quality threshold or marking a Day 10 exit PASS.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Patch committed; independent review pending | PR #881, see exact current PR head |
| Repository-verified | **UNVERIFIED** until exact-head CI jobs finish successfully | Review GitHub Actions on final PR head |
| Staging-verified | BLOCKED | No frozen paired API/worker/schema/Temporal restore readback |
| Production-qualified | BLOCKED | Human-held Day 9 and decision/approval evidence absent |
| Activated | **NO** | No admission or rollback mutation |

- **Historical completion denominators:** The 21 November source handoff reported 18/100 implementation task PASS, 5/54 exits, 0/10 accepted days. A single merged source fix and this draft do not update those counts without applicable verified row-level receipts.
- **Residual risks:** A digest proves the bytes supplied, not independent D custody, review authenticity, operator intent, or source-system execution. The JSON returned on stdout is not a persisted private decision file. The repo's native `ci-merge-gate`/review enforcement must be proved by repository administration rather than inferred from a CI workflow.
- **Next action:** Inspect PR #881 exact head, required CI and independent review. A human-authorized D/C operator then runs Day 9 first-run and 20 distinct recovery scenarios on one frozen staging release, checks authenticated readbacks, and runs the canonical Day 10 decision with a new unused output path; Founder/Owner C independently authorize any subsequent pilot action.
