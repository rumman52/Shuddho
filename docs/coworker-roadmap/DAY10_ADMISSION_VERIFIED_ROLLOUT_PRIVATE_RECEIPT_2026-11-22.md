# Day 10 — exact rollout bytes and private first-run admission receipts (22 November 2026)

**SOURCE-ONLY / controlled pilot NO-GO.** Part 05 Day 10 `D10.T09` / `D10.G08` acceptance boundary; parent #737, daily #736, independent D #665 and native governance #484. This task is not authorization to admit or verify any real pilot members.

## Scoped task contract

- **Objective and behavior:** A post-admission check must bind its approved rollout digest to the same bytes that were parsed to validate the cohort, and must create the first operator receipt privately at mode `0600` even under the normal `umask 022`. Reruns must use a new path, never clobber an old success/failure.
- **Dependency/source truth:** Part 05 (post-admission verification and immutable handoff); existing canonical Day 10 `scripts/day10_release_decision.read_json_with_sha`, Day 9 `scripts.ruke_pilot_eval.immutable_write`, and `tests/test_pilot_admission_verify.py`. The existing CI Coworker job runs the admission module under `--extra coworker` with `scripts.mandatory_test_gate` to reject skips.
- **Base main:** `b5b7805c37a1a9c2bb3d319bafcec85df8f77e99`.
- **Branch/PR:** `fix/day10-admission-verified-rollout-private-receipt-20261122` / [draft #887](https://github.com/rumman52/Shuddho/pull/887).
- **Existing interfaces:** `require_release_decision(rollout_path, decision_path, revision) -> (rollout, digest)`; `immutable_report(path, result) -> None`. Both signatures remain unchanged.
- **Exact files:** `scripts/pilot_admission_verify.py`, `tests/test_pilot_admission_verify.py`, this task contract, scoped implementation plan and `docs/coworker-roadmap/PROGRESS.md`.
- **Minimal fix:** consume `read_json_with_sha(rollout_path)` once instead of `read_json` followed by a second `file_sha256` open. Reuse `immutable_write(path, result)` instead of default-mode `path.open("x")`, preserving `PilotVerificationFailure` on pre-existing outputs.
- **Reproduction (actual RED):** committed two regression tests first at `2444c60f8c9c61d672115700b85271b1b0345896`. [GitHub Actions #45019756125](https://github.com/rumman52/Shuddho/actions/runs/45019756125) ran the mandatory Day 10 source module: **2 failed, 385 passed**. The rollout substitution test failed because the separate hash saw a different file; the POSIX mode test observed `0644` instead of `0600`. Neither failure was a missing dependency.
- **Production correction:** `375d9525a861a8c497a8f95fe8636a47913ad090`, reusing reviewed descriptor and private-exclusive writer, no new ledgers.
- **Expected post-fix behavior:** If the path changes after the frozen parsed bytes are read, the returned digest remains the digest of that parsed object. New receipts always mode `0600`, exclusive create with fsync; old receipts remain unmodified; failure replies preserve existing no-secret error behavior.
- **Tests and commands:**

```bash
uv run --locked --extra coworker pytest -q tests/test_pilot_admission_verify.py tests/test_day10_release_decision.py tests/test_cohort_release_gate.py tests/test_staging_release_freeze.py
uv run --locked --extra coworker python -m scripts.release_contract_check
```

- **Secrets, owner grants and egress:** Only synthetic identifiers and tokens in tests. The real `--member-tokens-file` and nonmember token remain owner-private; the code does not expose them to the JSON receipt, GitHub or telemetry. No external HTTP requests in these new tests.
- **Budget/timeouts/cancellation:** Existing 20-second HTTPS request timeout and 5–10-member validation are unchanged. No inference or paid providers. No new retry or control plane.
- **Default-off/rollback:** Capability flags and cohort allowlist unaffected. Source-only revert is a reviewed code change, never a downgrade of independently held first-run evidence.
- **External prerequisites:** Owner C/admin main protection plus final-head checks and independent reviewer; authentic exact-revision API/worker/schema+43 flags, staging restore and canonical quality evidence; human D's 40 protected first attempts, 80 blind scores and 20 operated recovery traces; separate Founder and Owner C same-release approval; separate owner-controlled admission action and all-member HTTPS/nonmember verification. None is established by this PR.
- **Out of scope:** An actual pilot/production rollout, authenticated signoffs, provisioning, SQL migration, staged member traffic, financial/external mutations, PostHog event capture, Render/Vercel/Private-object changes.

## Completion evidence

| Level | State | Required evidence |
| --- | --- | --- |
| Source implemented | Patch submitted for independent review | PR #887 current source SHA |
| Repository-verified | **Pending final-head CI and review** | Coworker zero-skip Day 10 gate, relevant Python tests, release contract, required status gates |
| Staging-verified | **BLOCKED** | Exact approved/operated staging source, worker, SQL and rollback identities |
| Production-qualified | **BLOCKED** | Independent D/C, Founder/Owner C authentic receipts |
| Activated | **NO** | Separate authorized 5–10 cohort admission and observed HTTPS tests |

- **Human review:** No independent approval inferred from an automatically merged PR or passing source tests.
- **Historical denominators:** The v4 baseline of 18/100 task PASS, 5/54 exits, 0/10 accepted days remains *historical*, not advanced by this source correction.
- **Risks:** Hashing the consumed bytes is internal consistency only. It cannot authenticate a live external platform, validate a signed human decision, or prove owner isolation; operators must compare independent source-system traces and permissions.
- **Next exact action:** Inspect [PR #887](https://github.com/rumman52/Shuddho/pull/887) final SHA, final-head required jobs and separate reviewer. After admin guardrails, the authorized D/C operator resumes Day 9 custody and 20 operated scenarios and runs the Day 10 admission gate only after canonical GO and separate authorization.
