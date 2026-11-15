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

For the protected **main-push audit job** only:

1. Create a dedicated, short-lived GitHub App installation credential
   or fine-grained token restricted to the **Shuddho repository**, with
   effective **ruleset write** access needed to reveal `bypass_actors`.
   Prefer short-lived installation credentials over broadly privileged
   personal tokens.
2. Store it in GitHub Actions secrets as
   `V01_GOVERNANCE_RULESET_TOKEN`. Do **not** put tokens in repository
   files, PR comments, logs, issue bodies, browser code or model prompts.
3. The `governance-audit` job runs **only on a push to main**, uses
   this optional credential for GET inspection, and falls back to the
   restricted `github.token` if it is absent. The fallback remains
   **fail-closed** if GitHub redacts bypass actors. No rule is weakened.

The PA-10 `source_gate` runs **before protected-environment approval**.
Its first job MUST use only `github.token` and **MUST NOT read any
`secrets.*`**. The current staging source gate separately requires a
fully inspectable main ruleset; with a redacted default token it stays
**BLOCKED** until a separately reviewed design can establish exact-head
governance trust **without crossing this pre-secret boundary**. A
working main audit is necessary but not sufficient to provision a
worker. Never inject privileged tokens into `source_gate`.
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
