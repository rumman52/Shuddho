# V-01 — Safe native main-ruleset operator (25 October 2026)

## Objective

Provide a reproducible, fail-closed local operator command for applying the already-reviewed `infra/github/main-ruleset.json` without pretending that source-level CI checks enforce GitHub's merge button.

The connected GitHub integration used for this task has read-only ruleset inspection and no ruleset-write action. No branch protection, ruleset, secret, deployment, or production setting was changed by this implementation.

## Evidence and root cause

- PR #561 merged as `38aac357f99ca90dedc2db43271bd1bf5fb69ae1`.
- Its exact-head `test-and-build` and `coworker` jobs succeeded, but `ci-merge-gate` failed at **Require independent current-head review**. The review API returned no submitted review.
- The PR still merged. This demonstrates the distinction between a failing workflow check and an enforced required check: native GitHub branch rules/rulesets must make `ci-merge-gate`, `test-and-build`, and `coworker` required.
- The connected integration cannot write repository rulesets. An authorized owner/admin must execute the operator below with an appropriately scoped token.

## Behavior

`scripts/apply_main_ruleset.py`:

- Is **dry-run by default**; it does not mutate repository settings unless `--apply` is supplied.
- Supports only `rumman52/Shuddho` and requires an exact `--confirm-repository` match for an apply.
- Uses the existing policy template; validates required checks, first-party GitHub Actions check source, independent review/stale approval settings, main targeting, and an empty bypass list.
- Refuses to create or replace rulesets when existing or ambiguous protection may target main, when legacy protection is already reported, or when current state cannot be verified.
- Rejects HTTP redirects for credential-bearing API calls.
- After creation, re-lists active rulesets, checks the unique ruleset targeting main, reads back the exact detail, and checks the branch's protection state.
- Does not automatically update, delete, roll back, or retry a potentially successful creation. If read-back fails after creation, it reports the ruleset ID and tells the operator to inspect before retrying.
- Always reports `merge_enforcement_verified: false` and `qualified: false`. Configuration read-back is not a negative-control test.

## Use by an authorized repository administrator

Use a secure local environment or secret manager to provide `GITHUB_TOKEN`; do not paste a token into source, a PR comment, or this document. The token must be able to read the effective branch/ruleset state and create repository rulesets (fine-grained PAT: appropriate repository Administration write permission).

First inspect without mutation:

```bash
python -m scripts.apply_main_ruleset --repository rumman52/Shuddho
```

Review the JSON plan and the current Settings → Rules/Branches state. Do not proceed if the script reports an existing or ambiguous policy; manually reconcile it while preserving any stricter rules.

Only after explicit owner/admin authorization, apply:

```bash
python -m scripts.apply_main_ruleset \
  --repository rumman52/Shuddho \
  --apply \
  --confirm-repository rumman52/Shuddho
```

The `GITHUB_TOKEN` must be supplied to the process through the authorized local environment. Do not run this command in PR-controlled CI or expose an administrator credential to untrusted code.

## Required proof after apply

1. Record ruleset ID, observation time, main SHA, actor identity/permissions and exact required check names.
2. Re-inspect effective repository and organization rulesets; confirm no ordinary bypass actor and preserve stricter inherited policy.
3. On a harmless test PR, demonstrate that pending checks, a failed check, missing independent approval, stale approval after a head change, and unresolved review threads each prevent merge.
4. Demonstrate that a fully current, reviewed, green test PR is eligible to merge; this does not require actually merging it.
5. Capture the observed rule ID, final-head check run IDs, review IDs, and negative/positive-control evidence without secrets.

If the admin token cannot read `bypass_actors`, the script must fail closed. Do not treat a green read-only audit or a ruleset JSON file as proof that merge is blocked.

## Status boundary

- **Operator implementation:** draft PR #562; tests and exact-head CI must be completed and independently reviewed.
- **Native ruleset applied:** not established.
- **Negative/positive merge-control proof:** not established.
- **V-01 release governance:** remains open until owner/admin action and evidence are recorded.
