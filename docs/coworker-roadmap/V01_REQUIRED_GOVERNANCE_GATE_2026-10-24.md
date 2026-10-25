# V-01: required governance result and operator handoff

## Task contract

- Objective: a successful `ci-merge-gate` on a main push must not hide a failed,
  cancelled, skipped or missing `governance-audit` result.
- Base: `ddb58a308b9cd28de791c911bc1338f12d7bed5c`.
- Branch: `fix/v01-required-governance-gate-20261024`.
- Evidence of the defect: main CI [39954055394](https://github.com/rumman52/Shuddho/actions/runs/39954055394)
  passed `test-and-build`, `coworker` and `ci-merge-gate`, while its governance
  audit failed because main protection was not confirmed.
- Root cause: the aggregate job depended on only the two code jobs and never
  consumed the audit result.
- Interfaces: existing workflow jobs, existing configuration auditors and
  existing independent-current-head review step. No new permissions or secrets.
- Change: add the governance dependency; require success on push; allow the
  intentional audit skip on PR/review events; reject unknown events and
  unexpected audit failures. Keep `always()` so a failed dependency produces
  a failed gate rather than a skipped gate.
- Compatibility: PR code jobs and independent approval remain required.
  The governance audit remains push-only and read-only.
- New configuration: `infra/github/main-ruleset.json` is an unapplied desired
  policy, not evidence of actual GitHub settings.
- Out of scope: modifying native rules, staging, production activation,
  transaction authority, runtime features or approval bypasses.

## Verification

Test-first execution of `tests/test_main_protection_audit.py` reported 15 failures
and 38 passes before implementation. The failures included the absent dependency,
false-positive shell exits for bad governance results, unsupported event handling,
and missing operator policy file. The tests run the actual workflow shell for
success, failure, cancellation, skipped and missing-result cases.

After the fix, the focused governance/review/redirect suite reported **149 passed,
zero skipped**. The policy template is consumed by both existing configuration
auditors; neither treats it as live enforcement evidence. Full-suite and exact-head
remote evidence are recorded in the PR and PROGRESS.md; do not infer them here.

## Apply native policy only through the authorized administrator

The payload requires PRs, one independent approval, stale-review dismissal,
last-push approval, resolved threads, up-to-date branches, the three existing
checks pinned to GitHub Actions App 15368, no bypass actors, no force pushes and
no branch deletion. It deliberately does not add a new required check name.

Before applying, inspect existing repository/organization policies and preserve
any stricter rule. Confirm that a qualified independent reviewer is available.
Use an authenticated administrator session whose scope is authorized for this
repository. Never store a token in this file or expose it to PR code.

Read current policy with the connected GitHub tools or authenticated `gh`:

```bash
gh api repos/rumman52/Shuddho/branches/main
gh api --paginate 'repos/rumman52/Shuddho/rulesets?includes_parents=true&per_page=100'
gh api repos/rumman52/Shuddho/rules/branches/main
```

If no applicable rule exists and the exact change is authorized, an administrator
can create it from the reviewed file:

```bash
gh api --method POST repos/rumman52/Shuddho/rulesets \
  --input infra/github/main-ruleset.json
```

Do not repeatedly POST on retry: retain the returned ruleset ID, re-fetch it,
compare current state, and review an update if needed. Do not replace existing
stronger rules wholesale. Record the returned ID and observation time, not a
made-up success receipt. This command was **not executed** by this change.

Re-fetch the policy using the authorized administrator identity, run the existing
native-policy diagnostic with securely supplied credentials, and perform the
following controls on a harmless test PR, without bypass:

1. Pending required jobs prevent merge.
2. A failed required job prevents merge.
3. Passing tests without independent approval prevent merge.
4. A new head invalidates stale approval and requires fresh checks/review.
5. Unresolved review threads prevent merge.
6. A reviewed, current, fully passing head is eligible to merge.

Keep source SHA, rule ID, actor permission evidence, check run IDs, review IDs,
timestamps and observed eligibility. A positive eligibility check need not merge
the test PR. Do not deliberately force-push/delete main as a negative control.

## Visibility limitation that must remain explicit

GitHub only returns `bypass_actors` in ruleset detail to callers with write access
to the ruleset. The CI read-only token may therefore be unable to prove bypass
absence even after an administrator configures the policy. The existing audit
correctly remains failed when evidence is unavailable. This patch propagates that
failure; it does not solve privileged evidence collection. Any future trusted
collector must bind evidence to repository, policy identity and observation time,
and must not execute PR-controlled source with an administrator credential.

Sources:
- [GitHub ruleset API and permission/visibility contract](https://docs.github.com/en/rest/repos/rules)
- [GitHub Actions dependency and always() semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)

## Status boundary

Implemented on the review branch; native policy unapplied; independent human
approval pending. V-01 remains open until actual policy and controls are verified.
The broader 17 A/C/P/V requirements, staging and production remain unqualified.


## Current status — 25 October 2026 (Asia/Dhaka)

This section supersedes the earlier draft-PR status above.

- PR #562 is merged into main at da7b7b66903be1ff5d29ec474fe8af2511d83701. The operator and reviewed policy template are already present; do not repeat their implementation.
- The latest observed main run is [CI #40169838677](https://github.com/rumman52/Shuddho/actions/runs/40169838677): test-and-build passed, governance-audit failed with “main branch protection is not confirmed”, and coworker was still running at last observation.
- Direct read-only GitHub API inspection returned protected=false, required-check enforcement off, and no applicable repository/parent rulesets. Native enforcement therefore remains unverified and the governance audit correctly fails closed.
- The connected GitHub integration has no ruleset-write action. An authorized owner/admin must run the existing operator from a secure local environment, inspect its dry-run output, apply only after policy review, and then prove negative/positive merge controls. Do not place an admin token in PR-controlled CI or chat.
- The production Render API previously reported commit-triggered auto-deploy while this revision's governance gate failed. That service setting is outside this operator and must be separately changed and verified by an authorized owner.
- The separate staging blocker remains tracked in [issue #291](https://github.com/rumman52/Shuddho/issues/291). This issue cannot be closed by source-level operator implementation.

Current V-01 state: **operator implemented; native policy not applied; negative/positive controls not run; release governance remains open**.
