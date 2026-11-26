# Day 10 — complete-cohort access verification (19 November 2026)

**Status: SOURCE-ONLY / NO-GO. This is not release qualification or an admission.**
Issue: [#736](https://github.com/rumman52/Shuddho/issues/736). Independent
holdout custody: [#665](https://github.com/rumman52/Shuddho/issues/665).

## Verified read-only baseline

At source review-base commit `cebe322d88d2120e6c78c6755b70445eedf8c39f`,
Supabase staging's connected Alembic ledger was `0070` with **0 Auth users,
0 Coworker accounts, and 0 AgentRuns**. The source migration head is newer
(`0072_merge_0071_heads`); no staging migration was applied. The Render
workspace lists the historical Shuddho staging API and production API but
**no Shuddho persistent worker**. The historical staging deployment's build
is not a matching source/worker release. The connected Vercel inventory did
not return a matching Shuddho project. These are observations, not operated
Day 9/10 receipts.

An earlier reviewed head `79329732285a9a188ee495e66d326cd05382fb62`
had five passed CI test jobs but failed the governance audit and merge gate.
**Do not transfer that verdict to this PR head or to a frozen release.**
No independently reviewed D corpus, first-run 40-case scores, twenty C-operated
Postgres/Temporal/object-storage scenarios, planner/curated-quality live gates,
rollback/restore, cancel-in-flight, paused schedule, two-way owner isolation,
multi-turn golden, or Founder/platform-owner approvals were authenticated.
The production execution ledger at this checkpoint remained **17/100 tasks,
5/54 exit checks, 0/10 accepted days**; Day 9 and Day 10 remain open.
No pilot was admitted.

## Gap closed by this source PR

The existing `scripts/staging_cohort_admission.py` checks **one invited**
staging identity and **one denied** identity. This is a useful preflight,
not evidence that *every* member of a 5–10-user pilot can access their account.
The new `scripts/pilot_admission_verify.py` is a separate **post-admission
observation** tool, not an allowlist writer or user provisioner.

It fails closed unless all of these are true:

1. The actual canonical rollout manifest passes `validate_rollout` and
   declares a maximum of **5–10** users.
2. The unmodified Day 10 decision receipt is bound to the **exact byte hash**
   of that rollout and the exact source revision, has canonical
   `GO_CONTROLLED_COHORT`, decision `READY_FOR_OWNER_CONTROLLED_PILOT`,
   no blockers and no claimed activation by the decision CLI.
3. An independently owner-controlled, private (0600), non-symlink JSON file
   supplies **5–10 distinct signed member credentials**; they map to
   **exactly** the configured backend cohort accounts (no extras and no
   duplicate subjects); enforcement is enabled and the configured maximum
   exactly matches the release manifest.
4. The admitted HTTPS API's authenticated `/api/v1/runtime-manifest` identifies
   the exact candidate source revision, reviewed environment, complete **43**
   boolean capability flags, action providers and enforced pilot cohort size.
   The independent operator must also verify the deployed image/build digest;
   the HTTP runtime manifest alone does not attest a build digest.
5. Every member's actual HTTPS `/api/v1/me` response is **200** **and**
   its JSON `account_id` exactly matches the signed-token identity that was
   prevalidated against the complete backend allowlist. A shared-cache,
   cross-owner, malformed, or identity-free HTTP 200 is **not** admission
   evidence and aborts before later probes. A fresh nonmember response is
   **403** with `cohort_not_enabled`. No account ID or bearer token is logged
   or written into the output receipt.
6. The nonmember account was not provisioned either **before or after**
   the probes, checked through the existing database access boundary.
7. A uniquely named output receipt is created exclusively and is never
   overwritten. No bearer token, subject, account ID or response body is
   printed or persisted.

An attempted or failed check **must not** be interpreted as admission,
pilot health, or the independent human verification required for GO.

## Exact order for authorized human operators

**Before doing any of the following**, the original Day 9/10 requirements
must be satisfied independently and their real evidence bound to one
release ID / exact API+worker Git SHA / rollout manifest SHA-256.

- Owner C provisions only an approved staging worker/Temporal/storage and
  performs backed-up schema alignment; independently observes API + worker
  source and image digests, live schema, 43 capability flags and model/provider.
- Independent D controls an external fresh 40-task holdout, proves developer
  negative-read and D positive-read, obtains D1/D2 blinded reviews, and
  preserves the first-run outputs/results unchanged. Run
  `scripts.ruke_pilot_eval evaluate` only after authentic receipts exist,
  requiring >=36/40, >=9/10 in each of four cells, and 40/40 security checks.
- C operates all 20 native recovery boundaries and records the actual
  observations. A/B/C/D independently operate rollback/restore, in-flight
  cancellation, paused scheduling, owner isolation both ways and multi-turn
  deliverable; D runs the live planner and quality gates.
- Execute `scripts/cohort_release_gate.py` and
  `scripts/day10_release_decision.py` on **actual independently reviewed**
  receipts. A successful unit test, test fixture or handwritten JSON is
  not an operated receipt.
- The **Founder** and **platform owner C** must authenticate *distinct*
  approvals for the exact manifest digest and pilot size via approved
  out-of-band channels. The CLI reads a decision JSON but **cannot**
  authenticate the approvers. Only the authorized human operator can admit
  five to ten allowlisted users; this PR never modifies the allowlist.
- **Only after the manual authorized admission**, observe all permitted
  member accounts and fresh nonmember denial with the command below.

Store the user tokens in a file **outside the checkout and CI artifacts**,
e.g. `/secure/operator/pilot-members.json`, containing a JSON array of the
five-to-ten bearer token strings, permissions `0600`. Do not include the
real credentials in a shell command, repository, ticket or PR. Provide the
backend operator's own `SHUDDHO_COWORKER_DATABASE_URL`, authentication settings and
`SHUDDHO_COWORKER_COHORT_*` settings via approved protected environment,
along with these **protected environment secrets**:

- `SHUDDHO_PILOT_API_BASE_URL`: verified HTTPS endpoint for the
  **admitted exact pilot deployment**; do not substitute an older API.
- `SHUDDHO_PILOT_NONMEMBER_TOKEN`: freshly issued, signed credential for
  a nonmember whose account is not provisioned.

After external authorization, run (placeholders below are paths, never fake
values to feed the gate):

```bash
uv run --extra coworker python -m scripts.pilot_admission_verify \
  --rollout /secure/operator/rollout-frozen.json \
  --decision /secure/operator/day10-decision.json \
  --source-revision "$VERIFIED_EXACT_RELEASE_SHA" \
  --member-tokens-file /secure/operator/pilot-members.json \
  --output /secure/operator/pilot-access-first-observation.json
```

Exit 0 means the **submitted release prerequisite, authenticated API manifest
and access probes** passed
mechanically; it **does not** mean this CLI admitted users, confirmed real
human approval, verified an image digest from a live runtime, or authorized
expansion. Exit 1 means no pass; preserve any earlier receipt. A failed first attempt also writes a minimal, anonymous failure receipt with
only the exception **type** (no exception text or token data). A subsequent
probe must use a **different output filename**. The operator must archive
HTTPS and DB observations separately with bounded, privacy-approved
retention, not the tokens themselves.

After an actual admitted pilot and sufficient observation, use
`scripts/cohort_health_gate.py`, `scripts/cohort_canary_progression.py`,
`scripts/cohort_scale_review.py` and the documented canary thresholds
against observed provider usage, failures, queue age, latency, cost, quality,
security and expansion-window telemetry. **No canary expansion now.**

## Source verification

```bash
uv run --extra coworker pytest -q tests/test_pilot_admission_verify.py \
    tests/test_staging_cohort_admission.py \
    tests/test_day10_release_decision.py
uv run --extra coworker python -m scripts.pilot_admission_verify --help
```

These tests are explicitly mandatory with **zero skips** in the existing Coworker CI job; a JUnit receipt is retained for each exact PR head. These tests are synthetic **source-level** checks only. They do not create
pilot users, operate fault scenarios, call a model or close any day. A fresh
exact-PR-head CI and independent review are still required; this document
must not be cited as a live acceptance result.


## 26 November 2026 — exact canonical-only capability follow-up

The pilot verifier requires the authenticated runtime-v2 API to report the separate `canonical_only_capabilities` object with exactly `{"suggestion_model_relevance": false}`. The existing 43 authority flags and one derived UI indicator are unchanged. A missing, enabled, unknown, or non-boolean setting blocks credit. The API exposes the actual configured boolean; this is readback only, not activation. Old receipts lacking the new required evidence remain archival.
