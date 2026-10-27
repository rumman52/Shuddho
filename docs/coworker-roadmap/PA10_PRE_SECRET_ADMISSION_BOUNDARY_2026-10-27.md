# PA-10 secret eligibility after source qualification — 27 October 2026

## Confirmed risk
PA-10 `provision-pa10-staging-worker.yml` previously declared Render, database and provider credentials on its `provision` job **before** running the source-qualification step inside that same job. The read-only `pa10-staging-prerequisite-preflight.yml` likewise declared secrets before its own source check. An unqualified workflow run could therefore enter the protected environment and obtain credentials before discovering a failed V-01 source gate.

## Change
Both manually dispatched workflows now use:
1. An initial `source_gate` job with no `environment`, no `secrets.*` references, no Render calls and no provisioning. It checks out the candidate with `persist-credentials: false`, grants the GitHub token only `contents: read` and `actions: read`, and invokes the already-merged `scripts.pa10_source_gate` against the exact dispatch SHA.
2. A separate `preflight` or `provision` job, requiring `needs: source_gate` and `needs.source_gate.result == 'success'` before declaring `environment: pa10-staging` and resolving `PA10_*` secrets. The original repository/ref restriction remains. The provisioning workflow retains `inputs.confirm == 'PROVISION'` on **both** jobs.

The unprivileged guard checks the existing V-01 ruleset configuration candidate, the exact current protected main SHA, and its successful main-push CI job evidence. No provider credentials are sent to the guard job. The implementation does not add any new authority or activate expanded features.

## Evidence and test contract
`tests/test_pa10_secret_boundary.py` enforces the two-job dependency graph, no secret or environment references before admission, reduced token permissions, non-persistent checkout credentials, exact SHA invocation and preserved paid-provision confirmation. The existing source-gate and worker-provisioning tests remain mandatory.

The new tests were authored and read-only static assertions were checked against both committed workflows; full Python repository CI and coworker CI must run on the final PR head. No live secret-bearing workflow was dispatched and no paid service or database was changed.

## Essential limitation
A source-controlled workflow cannot fully defend against an actor permitted to push or merge unreviewed code into `main`: such an actor may edit the workflow or its scripts. This defense is not an alternative to owner-enforced native branch rules, independent approval, required final-head CI, stale approval invalidation, and negative-control merge testing (issue #484). `pa10-staging` environment reviewers, branch restrictions and secret availability must be independently verified by an authorized operator.

## Operational status
- Current baseline at start: `c54e745a25029f61d468a14369747fda502e3e58` (PR #579 merge). Native `main` still reported `protected=false`, rulesets `[]`. The merged-main governance job failed. PR #579 had zero submitted reviews.
- Source-qualification code exists on main; this change solely moves the eligibility barrier **before** environment secret resolution for both PA-10 workflows.
- PA-10 live staging, persistent worker, Temporal/S3/auth tests, database continuity and release freeze remain not qualified; see issue #291.
- Neither staging provisioning nor production activation is authorized by this document.

## Acceptance / rollback
Require full final-head CI, independent review, and an effective native protected-branch policy before merge. Confirm source gate fails in the current unprotected environment and prevents the secret-bearing downstream job from being scheduled. Confirm it may proceed only with a qualified, reviewed protected main revision. Roll back only following security review; do not remove the dependency to make a blocked staging workflow green.
