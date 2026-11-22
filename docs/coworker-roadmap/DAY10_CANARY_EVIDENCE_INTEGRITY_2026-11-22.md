# Part 05 / Day 10 — canary expansion evidence integrity (22 November 2026)

**SOURCE-ONLY / NO-GO.** This contract addresses a bounded post-admission canary-input/output vulnerability, not admission or any live expansion. Governing source: Part 05 pp. 5–7, D10.T09/G08, Days 8–10 #734/#735/#736, parent #737, native review #484 and independent D #665.

## Scoped task contract

- **Objective / user-visible behavior:** Use strict, bounded, unambiguous canary stage controls and per-window health data; refuse external symlinked files/directories and oversized records; write a private, immutable first decision, including if the decision would declare eligibility for expansion.
- **Current baseline:** `main e12f9832fb8b495bb30e6a81e125906b53508832` already contains Day 10 source-only PR #887, but that PR was merged with `ci-merge-gate` failed and no independent review.
- **Branch/PR:** `fix/day10-canary-evidence-input-output-integrity-20261122` / [draft PR #891](https://github.com/rumman52/Shuddho/pull/891).
- **Files:** `scripts/cohort_canary_progression.py`, `tests/test_cohort_canary_progression.py`, this contract, one implementation plan, `docs/coworker-roadmap/PROGRESS.md`. No database schema, API, worker or rollout change.
- **Existing interfaces:** `load_plan(Path) -> dict`, `load_history(Path) -> list[dict]`, `evaluate_progression(...)`, `main()`. Preserve canonical thresholds, stage gates, rollback and recovery epoch semantics.
- **Root cause:** The two input readers used unbounded `Path.read_text()` + Python permissive `json.loads()`, accepting duplicate `decision` or threshold fields (a `STOP_ROLLOUT` key can be shadowed by later `CONTINUE_COHORT`), symlinked/oversized file receipts and a symlinked history directory. CLI `--output` used `Path.write_text()` to overwrite previous decisions and produce mode `0644` under `umask 022`.
- **RED verification:** Tests first in `604d92cae8fa37703b4d66c740908cf1c6131366`; [Actions #45034201001](https://github.com/rumman52/Shuddho/actions/runs/45034201001), `test-and-build` Python step: **7 expected failed, 3,647 passed, 107 skipped, 6 warnings**. Failures specifically cover duplicate plan control, duplicate health decision, symlinked receipt, symlinked directory, >4 MB report, first-report mode `0644` not `0600`, and overwritten existing decision. Existing old tests did not assert these properties.
- **GREEN candidate fix:** `b13908fde0e5e9aea8d5d0cee655081701459873`. Reuse the already-tested `scripts.ruke_pilot_eval` strict/bounded input parser, 4 MB cap and exclusive `0600` `immutable_write`. Health history enumeration and member opens use the same opened no-follow directory inode, with `dir_fd`, `O_NOFOLLOW`, `O_NONBLOCK`, `fstat`, 4 MB maximum read and strict duplicate/nonfinite rejection. Reject pre-existing output with a clear nonzero exit.
- **Positive controls:** A canonical plan and three valid synthetic health receipts must still produce the existing eligibility decision; fresh path has mode 0600. All existing canary/recovery tests must remain green.
- **Negative controls:** Duplicate/ambiguous JSON, any linked inputs, size growth/big inputs, and report reuse cannot pass or rewrite old evidence.
- **Verification commands:**

```bash
uv run --locked --extra coworker pytest -q tests/test_cohort_canary_progression.py tests/test_cohort_health_gate.py tests/test_cohort_release_gate.py
uv run --locked --extra coworker python -m scripts.release_contract_check
uv run --locked --extra coworker pytest -q
```

- **Source- and ownership-boundary:** Input is operator-owned synthetic/private receipts; this PR neither authenticates their author nor proves PostgreSQL/Temporal/Storage happened. Preserve existing 5–10 pilot, independent approvals, raw decision, and controlled expansion separate from eligibility.
- **No new budget/egress:** No paid inference, third-party mutation, staging worker, API request, database write, telemetry event, admission, secret or identity read, branch policy edit, native release decision or source contract weakening.
- **Failure handling:** Missing/invalid files fail closed with `CanaryProgressionError` rather than quietly dropping evidence; a collision exits nonzero without replacing original bytes.
- **External dependencies / accountable roles:** Owner C/admin enforces native one-approval plus exact-head checks, negative/positive merge tests and restores staging from an approved compatible backup; human D secures the corpus and operates the 40/80/20 qualification matrix; Founder + Owner C independently authenticate and sign the exact release; approved operator verifies API/worker/schema/43 flags and all admitted members. The assistant has not performed or attested those operations.

## Completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Source code | Patch submitted, pending final-head verification | Draft PR #891, fix SHA above |
| Repository checks | **Pending final-head CI / human review** | [Actions #45034201001](https://github.com/rumman52/Shuddho/actions/runs/45034201001) proves RED on test-only head |
| Staging recovery / live canary | **BLOCKED** | Fresh authenticated release, operated traces, owner permission and budget absent |
| Pilot release-qualified | **NO-GO** | D, Founder/C, 40/80/20 and native governance receipts missing |
| Activated | **NO** | No expansion, allowlist or pilot admission authorized |

Historical v4 ledger (18/100 tasks, 5/54 exits, 0/10 accepted days) remains a dated baseline; source tests do not upgrade it. Validate exact final-head jobs and separate review before merge, then resume at independently operated Day 9/10 gates.
