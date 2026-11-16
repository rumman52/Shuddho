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
