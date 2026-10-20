# V-01 native GitHub protection — read-only administrator diagnostic

Date: 2026-10-21 (Asia/Dhaka). Tracker: [#484](https://github.com/rumman52/Shuddho/issues/484).

## Motivation and observed blocker

The merged [PR #524](https://github.com/rumman52/Shuddho/pull/524) did **not** meet pre-merge approval/CI qualification: its exact-head [workflow #39490662180](https://github.com/rumman52/Shuddho/actions/runs/39490662180) completed with `test-and-build` successful, `coworker` cancelled, and `ci-merge-gate` failed. GitHub's submitted reviews list was empty when inspected. The app integration receives HTTP **403** reading `GET /repos/rumman52/Shuddho/branches/main/protection`; its `GET /repos/rumman52/Shuddho/rulesets` returned `[]`. Neither response establishes effective policy or actor bypass rights. This is a **native GitHub enforcement blocker**, not a Python review-gate bug.

## Deliverable

`scripts/v01_native_protection_audit.py` is a zero-write diagnostic with 11 regression tests in `tests/test_v01_native_protection_audit.py`. It reads saved administrator JSON or makes administrator-authorized GET requests. It checks that a single explicit native branch-protection / active ruleset candidate has:

- Required full exact-head check names: `test-and-build`, `coworker`, `ci-merge-gate`, with strict policies.
- At least one approval, stale approval dismissal, last-push approval, and resolved review threads.
- Admin/approval bypass not configured; force pushes/deletion not enabled.
- If relying on a ruleset: active branch target explicitly includes `refs/heads/main`, no exemptions/bypass actors, and non-fast-forward and deletion restrictions.

This script deliberately **does not** infer settings from workflow YAML, mix partial unrelated rules into a fictional compliant policy, or mark V-01 qualified.

## Run in a trusted administrator terminal

Option A: read-only live evidence. Use a token with permission to **read** repository administration metadata. Never put it in command output or issue comments:

```sh
export GITHUB_TOKEN=...   # load securely; do not paste secrets into reports
python -m scripts.v01_native_protection_audit --live-repository rumman52/Shuddho
```

Option B: save independent JSON snapshots with `gh api` and review them before sharing. If native rulesets are present, collect full details for each applicable ruleset:

```sh
gh api repos/rumman52/Shuddho/branches/main/protection > /tmp/shuddho-main-protection.json
gh api 'repos/rumman52/Shuddho/rulesets?includes_parents=true' > /tmp/shuddho-rulesets.json
gh api repos/rumman52/Shuddho/rulesets/ID > /tmp/shuddho-ruleset-ID.json
python -m scripts.v01_native_protection_audit \
  --branch-protection-json /tmp/shuddho-main-protection.json \
  --rulesets-json /tmp/shuddho-rulesets.json \
  --ruleset-detail-json /tmp/shuddho-ruleset-ID.json
```

If a REST endpoint returns 403, **do not invent its JSON**; use an admin-authorized account to inspect the settings in GitHub. Wildcard or inherited rulesets need separate effective-rules verification: a conservative `blocked` result is not proof that GitHub lacks protection.

## Safety semantics / acceptance

- `blocked`: exit **2** (no complete readable qualifying candidate, or missing required fields).
- `configuration_candidate`: exit **3**, **not zero**. Means the supplied *settings* are consistent with one conservative configuration; `enforcement_verified` is **always false**.
- No code path from this tool can return a successful release gate (exit 0). It cannot change rules, merge PRs, promote deployments, or enable transactions.
- Independently collect effective actor bypass rights, rule IDs, and demonstrate with safe test PRs that **unreviewed**, **pending/red CI**, and **stale-head approval** PRs **cannot merge**; demonstrate green current-head independently reviewed positive control. The human administrator must attest this evidence before V-01 acceptance.
- Keep [#484](https://github.com/rumman52/Shuddho/issues/484) open and treat staging [#291](https://github.com/rumman52/Shuddho/issues/291) as a separate deployment qualification blocker.

## Local test evidence

A deliberately permissive implementation returned 9 failures and 1 passing check on the initial 10-test file; restoring the real implementation produced 10 passes. An additional negative-control CLI test verifies that even a compliant-looking fixture exits 3, not 0; final local result **11 passed** under Python 3.13 and `py_compile` succeeded. These are **local unit tests**, not final-head GitHub Actions or administrator enforcement evidence.

Draft PR must remain unmerged without a complete current-head CI, an independent human review, and verified native rules.
