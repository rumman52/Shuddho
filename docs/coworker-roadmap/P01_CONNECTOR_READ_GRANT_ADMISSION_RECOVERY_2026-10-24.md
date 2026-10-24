# P-01 / C-01 — connected read-grant admission recovery

- **Objective and behavior:** make optional Agent connected context grants safe to retry after an API admission response is lost; prevent a failed initial sync from hiding a successfully created, revocable read grant. A manual Sync must never mint another grant.
- **Base branch/SHA:** `main` at `c3472f76ca2725fd8928abd59cdce57dc524422e` (merged PR #560); later base updates must be rechecked.
- **Work branch/PR:** `fix/p01-connected-grant-admission-recovery-20261024`, draft PR #561.
- **Dependency evidence:** existing owned connector read-grant endpoints accept `Idempotency-Key` and a payload containing absolute `expires_at`. The Agent UI already has grant listing, a separate initial sync operation, a manual Sync button, and revocation. Reuse these existing contracts; create no new server ledger or permission type.
- **Original concrete defect:** `authorizeRead()` in `AgentWorkspace.tsx` computed a new UUID and expiry on each click. When POST admission succeeded but its response was lost, the retry used a different key/expiry and could create a second grant. When POST returned a grant but initial sync failed, the UI displayed no grant and offered only a new authorization, even though the existing grant was active.
- **Touched files:** `apps/web-editor/src/coworker/AgentWorkspace.tsx`, `apps/web-editor/src/coworker/connectorGrantAdmission.test.tsx`, `apps/web-editor/test/run-tests.mjs`, this contract, and `PROGRESS.md`.
- **Interface/schema:** client and backend endpoints unchanged. Local in-memory pending-admission map keyed by connection ID stores **both** UUID request key and fixed absolute expiry. Confirmed grant admission clears only that connection's pending record. No local key persistence across unmounts/browser reloads is claimed.
- **New regressions:**
  1. Accepted POST with lost reply; retry on same connection uses unchanged idempotency key **and expiry** and recovers one grant; sync called once.
  2. POST confirmed then initial sync fails; previously accepted grant is visible/selected, and manual Sync succeeds without another POST.
  3. Two Allow clicks in one React tick do not issue two concurrent admissions, even when POST is pending.
  4. Pending uncertain grant for connection A is retained across granting connection B, and later A recovery does not share B's identity.
- **Test-first:** tests committed at `f58c078b52da5d6ea4ae0df4a4fd59de6e6f0ae6`; registered at `4b49bbd6055ec10c4335a703f910f793c10d9182`; fix at `29fc7ff96b715fb05d6582fd807f90e39c78a8c2`. A test-only CI run was cancelled before web tests completed by subsequent branch updates; do not claim an observed red test run.
- **Expected failure outcomes:** ambiguous POST response leaves pending identity for retry; definitive backend `idempotency_conflict` surfaces without silently rekeying. A confirmed POST with failed sync surfaces a sync error while preserving grant for manual retry. A changed/other connection has distinct pending identity. The server remains ultimate authority for revoked, expired and disallowed grants.
- **Tests/CI:** repository `npm run test --workspace @shuddho/web-editor` and `npm run build --workspace @shuddho/web-editor`; mandatory GitHub `test-and-build`, `coworker`, `ci-merge-gate` on **final PR head** plus independent submitted reviewer decision.
- **Trust and authorization:** backend-issued grant remains revocable. No new provider credentials, browser direct access, model-assigned permissions, or automatic external actions. A read grant is not blanket consent for external-action execution. Keep existing owner, capability, purpose and expiration checks.
- **Budget/timeout/cancellation/revocation:** existing connector sync limits and client timeout are unchanged; do not auto-retry uncertain POST with a new key. Manual sync remains explicit. The UI's synchronous admission fence prevents same-tick duplicates. Revocation enforcement remains backend-owned.
- **Default-off/rollback:** no feature flags changed. The fix only affects Agent UI when connected read sources are enabled and present. Roll back by reverting this PR; no data migrations.
- **External prerequisites:** selected-provider and controlled PostgreSQL/Temporal/S3 staging, independent provider mutation observation, UI reload/crash recovery and security review remain separate work (issue #291). No production or paid provisioning authorized.
- **Out of scope:** persistent browser-safe replay journal (potential privacy/security concerns), server/Idempotency-Key contract changes, automatic sync retries, background permissions, provider subscription lifecycle changes, V-01 administrator-applied protection.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Source fix on draft branch | `29fc7ff96b715fb05d6582fd807f90e39c78a8c2` and scoped tests; CI on final commit must still be checked |
| Repository-verified | Pending | Exact-head CI and mandatory coworker suite, independent review |
| Staging-verified | Not established | Real provider/DB/worker recovery and revocation |
| Production-qualified | No | V-01/V-02/V-03/V-04 remain open |
| Activated | No | No flag or deployment changes |

- **Residual risks:** in-memory identity is lost if the tab unmounts before confirmed POST; a server-side grant list can recover known grants on reload, but cannot equate an unknown lost reply with a new grant. The test fixture models backend idempotency but does not itself prove provider/DB behavior.
- **Next action:** confirm all four UI regressions and mandatory exact-head CI; obtain independent review before merge. Apply and negative-test native main ruleset under issue #484 separately.
