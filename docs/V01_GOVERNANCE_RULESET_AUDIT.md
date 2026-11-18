# V-01 ruleset inspection credential (staging prerequisite)

## Why the native ruleset can exist while CI fails

GitHub deliberately **redacts `bypass_actors`** from the GET
`/repos/{owner}/{repo}/rulesets/{id}` response unless the caller has
**write access to that ruleset**. A standard `GITHUB_TOKEN` with
`contents: read` can see the required checks and approvals while still
being unable to verify that bypass actors are absent. The source audit
must **fail closed** in that case; never interpret a missing
`bypass_actors` field as an empty list.

Official documentation: https://docs.github.com/en/rest/repos/rules#get-a-repository-ruleset

## Operator-controlled credential prerequisite

1. Install the dedicated GitHub App and configure the two GitHub Actions
   environments using the [infrastructure runbook](../infra/README.md#authorize-the-github-ruleset-audit).
2. The main-push audit mints a short-lived installation token restricted to
   Shuddho. The audit uses it to read the protected branch and ruleset details.
3. PA-10 `source_gate` uses `github.token` to check exact-head CI. A separate
   live ruleset audit in `v01-governance` must pass before the workflow enters
   `pa10-staging`. After staging approval, the workflow repeats the audit
   before accessing the database or invoking Render and other providers.
4. Verify the audit result on the exact protected `main` SHA, then
   verify `test-and-build`, `coworker`, `governance-audit` and
   `ci-merge-gate` conclusions are successful on that same run.
   Staging source validation must reject pending/old/failed runs.
5. Independently verify the effective native protection with a harmless
   **negative-control PR** (pending/red checks and no independent
   approval cannot merge) and a **positive-control PR** (current-head
   checks and independent approval permit merge). Record evidence in
   issue #484. No CI result or audit can replace this operator test.

## Staging work remains separately gated

An active native ruleset is **not** a license to provision paid worker
compute, recreate an old database, expose private keys, or turn on high
authority features. The PA-10 workflow additionally requires the
operator's explicit `PROVISION` dispatch, valid scoped staging
credentials, successful live database migration check, and an
approved spending boundary.

If an audit fails with "redacted bypass_actors", correct the GitHub
credential's **ruleset inspection access**. Do not change the code to
assume an empty bypass list, add an undocumented bypass actor, or remove
a required check just to obtain a green pipeline.


## Day 1: reproducible, non-mutating ruleset drift evidence

The offline tool \`scripts/day1_ruleset_drift.py\` reports which specific
configuration requirements are missing from ruleset 27324410. It reads
previously captured GitHub JSON snapshots; it never contacts GitHub, creates
an App token, modifies a ruleset, approves a review, or exercises a merge.

From an administrator-approved session, capture fresh API readbacks into a
private directory (do not commit the files or print credentials):

\`\`\`bash
umask 077
gh api repos/rumman52/Shuddho/branches/main > /secure/day1/main-branch.json
gh api repos/rumman52/Shuddho/rulesets/27324410 > /secure/day1/main-ruleset.json
uv run --extra coworker python -m scripts.day1_ruleset_drift \
  --branch-json /secure/day1/main-branch.json \
  --ruleset-json /secure/day1/main-ruleset.json \
  --expected-main-sha "<exact-current-40-character-main-commit>" \
  --output /secure/day1/ruleset-drift.json
\`\`\`

The tool exits **1** for configuration drift, **2** for untrusted/malformed
input, and **0** only for a configuration *candidate*. Even a zero exit
prints \`qualified=false\`: administrator-authenticated effective-rule
inspection, protected GitHub App audit credentials, exact-head CI,
independent review, and native denied/permitted merge-control exercises are
still required. This is a diagnostic complement to
\`main_protection_audit.py\`, not an alternate release gate.

The compared policy is always loaded from the checked-in
\`infra/github/main-ruleset.json\` by default; weakening that policy causes
the diagnostic to reject the input. Inputs are bounded and output is
created once with private permissions. Never commit the captured
administrator readbacks or evidence files.
