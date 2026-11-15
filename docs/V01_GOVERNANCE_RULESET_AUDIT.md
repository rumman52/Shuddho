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

For the two gated, trusted entry points only:

1. Create a dedicated, short-lived GitHub App installation credential
   or fine-grained token restricted to the **Shuddho repository**. It
   must have the effective **ruleset write** access needed to reveal
   `bypass_actors`; the staging source gate additionally reads GitHub
   Actions workflow runs and jobs, requiring **Actions: read**.
   Prefer a short-lived, repository-scoped GitHub App installation
   credential over a broadly privileged long-lived personal token.
2. Store it in GitHub Actions secrets as
   `V01_GOVERNANCE_RULESET_TOKEN`. Do **not** put tokens in repository
   files, PR comments, deployment logs, issue bodies, the browser, or
   model prompts. Do not grant access to unrelated repositories.
3. The `governance-audit` job runs **only on a push to main**.
   The PA-10 `source_gate` runs only on manually confirmed
   `workflow_dispatch` from `main`. Both use the optional secret
   only for HTTPS GET inspection. Missing secrets fall back to the
   standard token and **remain blocked** when bypass actors are
   redacted; no branch-protection requirement is relaxed.
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
