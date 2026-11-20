# Day 6 Native Byte Identity and Restart Reconciliation (Part 03)

**Scope:** Read-only Days 3–6 staging acceptance verifier only. Uploaded `03_Rukh_AI_Product_Workflows.docx`, pp. 8–10, especially D06.T05/T06/T08/T09, D06.G04 and the original-byte/recovery authentication contract. GitHub #732, Linear MD-7. **Do not use synthetic test fixtures as hosted acceptance.**

## Intent

Previous `check_day6` accepted `owner_a_hash_verified=true` with only an unverified declared native file SHA/byte count, even if the manifest, private object store and authenticated owner download differed. It also accepted a restarted run with only matching run IDs and asserted zero *additional* effects, without checking recovered native artifact IDs, byte identity or exactly-once run-scoped effects.

This change requires **internally consistent operator readback receipts** for both flows. It is not a download implementation, platform authentication, or deployment. Independent reviewer must still directly open/download the original bytes, compute SHA-256 locally, verify private storage metadata and compare platform event histories.

## TDD plan

- [x] First commit only synthetic adversarial tests: `c69ef6b142e9eb4d6fae9c61f32bb0bbbe2c624e`. The new fixture has per-file manifest/store/download SHA-256 and lengths, explicit 200 owner A retrieval, private storage ref and independent receipt refs; reconnect has before/after artifact snapshots, timestamps, and run-scoped admission/outbox counts.
- [x] Verify genuine **RED**. GitHub Actions [#44790471658](https://github.com/rumman52/Shuddho/actions/runs/44790471658) `Run Python tests`: **45 expected `DID NOT RAISE` failures** in the new test parametrizations, **2,858 passed**, **103 skipped**, **6 warnings**; original 40-case registry and unrelated suite unaffected.
- [x] Implement minimal **GREEN** `check_day6`: compare declared native/manifest/private-store/download SHA-256; require object/store/download byte sizes identical and nonzero; require A's 200 readback and distinct private storage object refs/manifest/storage evidence. Record the final artifact set for each run; verify post-recovery snapshot exactly matches the restarted run's expected artifact IDs and SHA-256; pre-snapshot may be empty or a preserved subset. Prove before/after timing and one run-scoped AgentRun plus one outbox effect on both sides.
- [ ] Verify the final **exact HEAD** on the repository's Python/Days 3–6 contract, frontend/browser, PostgreSQL and extended Coworker CI.
- [ ] Complete independent code review plus governance and exact-head merge-gate approval. If the repository account auto-merges while governance or Coworker is missing, record that as a shortcoming, never as acceptance.

## Interfaces

**Input:** Existing Day 6 receipt plus `cases[].native_files[]` fields:
`manifest_sha256`, `object_store_sha256`, `owner_download_sha256`, `object_store_byte_size`, `owner_download_byte_size`, `owner_a_http_status`, `storage_object_ref`, `manifest_receipt_ref`, `object_store_receipt_ref`.

`reconnect` fields: `artifacts_before`, `artifacts_after` (lists of `{artifact_id,sha256}`); `before_snapshot_at`, `after_snapshot_at`, `before_snapshot_receipt_ref`, `after_snapshot_receipt_ref`; `run_agent_effects_before/after`, `run_outbox_effects_before/after` (each exactly 1).

**Output:** Existing `check_day6(release, receipt, frozen)->verified_at`, raising `Days36EvidenceError` on mismatches, and still producing **`evidence_internally_consistent_not_live_attested`**, never a certified hosted pass.

## Key negative proofs

- Manifest mismatched private store or download SHA while `owner_a_hash_verified=true`: fail.
- Missing storage, owner-download or manifest digest/receipt; zero or mismatched lengths; owner A denied; reused storage object across four language/workflow cases: fail.
- Recovery returns duplicate/foreign/missing artifact, changed SHA, or silently drops a pre-restart artifact: fail. Empty before is supported if none yet published.
- 0/2 run-scoped agent/outbox effects or missing/misordered snapshot timestamps/receipts: fail.

## Explicit exclusion / operator handoff

The schema still relies on operator-provided statements and external `evidence_ref` values. It **does not fetch object bytes**, calculate hashes independently, prove the browser executed, or authenticate Render/Temporal/Supabase/provider logs. No owner credentials, paid model calls, migrations, new services or emails are created. MD-6 Day 2 backup/isolated restore/managed owners/schema/worker/browser and MD-7 same-release independent reviewer/quality/human checks remain open. Connected staging Supabase currently reports 0 public tables and migrations; Vercel connection has no Shuddho project; Render workspace requires explicit selection.

The Part 03 Day 6 40-case first-output preservation and remediation, email send audit, fact checking, Bangla glyph checks, DOCX/PDF content quality and full 4-cell hosted workflow remain separate acceptance requirements.
