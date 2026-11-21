# Day 1 — Offline native ruleset ownership readback

- **Objective and user-visible behavior:** Never label a captured GitHub main ruleset `configuration_candidate` when the offline snapshot's `source` and `source_type` do not explicitly prove the expected repository-owned existing ruleset. Continue to report `qualified=false` even on a positive readback.
- **Dependency tasks and current evidence:** [10-day Day 1 plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) ¶141–152, [#727](https://github.com/rumman52/Shuddho/issues/727), [#737](https://github.com/rumman52/Shuddho/issues/737); already merged [PR #846](https://github.com/rumman52/Shuddho/pull/846) validates live status-row integrity. The pre-existing administrator `reconcile_main_ruleset.py::_read_unique_existing` validates `source`/`source_type`, but offline diagnostic did not.
- **Exact base:** `main` `b648d1ab2f83ea6b3abd79b660ccf96ce1322b14` (do not interpret as current main after new merges).
- **Work branch and PR:** `fix/day1-offline-ruleset-repository-origin-20261121`; [draft PR #850](https://github.com/rumman52/Shuddho/pull/850).
- **Existing interfaces reused:** `analyze(branch: object, live_ruleset: object, policy: object, *, expected_main_sha: str, expected_ruleset_id: int = RULESET_ID) -> dict`; existing `_object`, `require`, `REPOSITORY`, and native ruleset `source` and `source_type` fields. No schema, endpoint, public signature or CLI change.
- **Exact files modified/added:** `scripts/day1_ruleset_drift.py`, `tests/test_day1_ruleset_drift.py`, this contract, `docs/coworker-roadmap/PROGRESS.md`, `docs/superpowers/plans/2026-11-21-day1-offline-ruleset-origin.md`.
- **Acceptance and assertions:** The explicit `source="rumman52/Shuddho"` and `source_type="Repository"` candidate remains `qualified=false`. Ten negative source/source_type cases (foreign, wrong case, Organization, Enterprise, null, blank and missing) produce `status=blocked_configuration` with drift code `ruleset.repository_origin`. Existing approval, status-source, no-bypass, SHA and native-policy checks unchanged.
- **Reproduction/initial RED:** Test-only SHA `28d8fe4783f854bc722e1554f33c37a082a3ff6e`; [Actions #44889771927](https://github.com/rumman52/Shuddho/actions/runs/44889771927) `test-and-build` **10 expected FAILED, 3,080 PASSED, 105 SKIPPED, 6 WARNINGS**; ten targeted assertions observed `configuration_candidate` instead of `blocked_configuration`. This RED run intentionally fails and is not release evidence.
- **Minimum fix commit:** `f2c10625d688054b4e35271bfb66657125b01bc1`; append one repository-origin check to `analyze`; the rest of the script is untouched.
- **Tests and required CI:** `uv run --locked --extra coworker pytest -q tests/test_day1_ruleset_drift.py tests/test_main_protection_audit.py tests/test_reconcile_main_ruleset.py`; exact PR HEAD `test-and-build`, `coworker`, frontend, browser, PostgreSQL 18 compatibility, ancestry and `ci-merge-gate`. `governance-audit` is normally SKIPPED on PRs: do not call that SUCCESS. Inspect actual logs, never infer from branch head or RED run.
- **Secrets/owner/grant/approval/egress:** The offline script reads local JSON only; it does not authenticate a GitHub administrator. Secrets `V01_RULESET_APP_CLIENT_ID`, `V01_RULESET_APP_PRIVATE_KEY` and live ruleset mutation require separately authorized Owner C/repository administrator. Do not place values in GitHub/Linear.
- **Budget, timeouts, cancellation, revocation:** No new external request, provider call, paid resource, queue, or user grant. Existing CLI bounds and fail-closed JSON parsing unchanged.
- **Default-off gate and rollback:** This is a read-only audit behavior; no capability activation. Code revert only through a reviewed PR; no native ruleset or deployment change performed.
- **External prerequisites:** Genuine native denied/unreviewed and allowed/reviewed merge controls on rule `27324410`; protected App installation permissions; real staging backup + isolated restore and API/worker/schema identity; independent D custodian for 40 private holdout cases; separately signed Founder+C exact-release GO decision.
- **Out of scope:** Read/change protected GitHub App secrets or native rule, Supabase migration `0070` → checked-in head `0072_merge_0071_heads`, Render paid worker/Temporal/S3 provision, PostHog ingestion, Vercel deployment, unrelated ProductOS workspace, private holdout access and pilot admission.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Source correction committed | [PR #850](https://github.com/rumman52/Shuddho/pull/850), commit `f2c10625d688054b4e35271bfb66657125b01bc1` |
| Repository-verified | **Exact-final-head CI pending** | [PR #850 Checks](https://github.com/rumman52/Shuddho/pull/850/checks) |
| Staging-verified | **Not attempted; BLOCKED_EXTERNAL** | No current exact-release recovery or runtime receipt |
| Production-qualified | **NO-GO** | Real merge control + custody + staging and approvals absent |
| Activated | **NO** | No live configurations changed |

- **RED pass/fail/skip:** 3,080 pass / 10 expected fail / 105 skip / 6 warning.
- **GREEN:** Must be read from GitHub Actions final head; absence of a result is not a pass.
- **Review:** Distinct independent human review required; self-review does not qualify.
- **Residual risk:** A repository-owned ruleset readback remains a candidate only; no offline JSON fingerprint establishes authoritative operation or GitHub merge enforcement.
- **Next exact action:** Inspect final-head CI; arrange distinct human reviewer; Owner C validates actual protected App with real denied/permitted merge evidence and staging restore before any Day 1 acceptance.
