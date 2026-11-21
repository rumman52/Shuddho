# Day 2 Isolated Restore Authenticated Readback Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion. Do not mark hosted PASS from source-only receipts.

**Goal:** Close D02.T09's missing authenticated owner-A retrieval and owner-B denial on the *isolated restored* API, without conflating direct database/object hashes with HTTP access checks.

**Source:** `02_Rukh_AI_Private_Staging.docx` Part 02, page 2 "Restore to isolated targets" item 3; page 3 "Download" and "Produce the release bound Day 2 receipt"; page 4 D02.T03/T08/T09/G03/G04. Existing `scripts/staging_backup_restore.py verify` checks source and isolated DB/object inventories and privileged readback, but makes no owner A/B HTTP requests to the isolated API.

**Design:** Introduce a narrow `scripts/staging_restored_api_access.py` read-only API proof reusing Day 2 JWT issuer/audience/expiry and `/me` binding validation, requiring HTTPS source/restored origin separation, a release-identical staging runtime manifest, owner-A `/documents/<id>/content` byte hash match, owner-B content 404 + absent list entry, owner-A cancelled task and owner-B task 404. Return only booleans/digests/size and hashed API origin. Never send credentials in argv or receipts, follow redirects, or call unapproved/non-HTTPS endpoints. Run only *after* full isolated PostgreSQL/object attestation is matched in `staging_backup_restore.verify`. Make the API proof mandatory for issuing `backup_restore: passed`, and require it at the final Day 2 acceptance gate. Use `SHUDDHO_STAGING_ALLOW_RESTORED_API_READBACK=true`, `SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true`, source API origin from `SHUDDHO_STAGING_API_BASE_URL` and separate isolated `SHUDDHO_STAGING_RESTORED_API_BASE_URL`; owner A/B tokens remain environment-only. The operator must independently confirm the restored API is bound to the isolated DB/bucket; URL inequality and HTTP bytes are not cryptographic proof of infrastructure routing.

**Safety:** Source-only tests via `httpx.MockTransport` and synthetic JWT claim fixtures. No mutation of production/staging, account creation, model inference, paid worker, or restore. Still needs Founder+C dated host/cost/restore/rollback approval and independent reviewer D.

## Work

- [ ] RED: add HTTP fixture proving two distinct, API-accepted managed identities, A success byte digest, B denial on content/list/task; reject A wrong bytes, B 200 content, B enumeration leak, B task read, wrong owner ID, source origin reuse, wrong runtime SHA, redirects, missing guards, malformed endpoints.
- [ ] RED: add final Day 2 acceptance rejection of missing/invalid `archive_integrity.restored_api_access` with source/target proof still intact.
- [ ] RED: test `staging_backup_restore.verify` cannot write a PASS without restored API readback, even if four archive paths are provided.
- [ ] GREEN: implement read-only API checker with HTTPS restrictions, no redirects, mockable client and redacted result; wire it into isolated restore verify and CLI, fail closed if absent.
- [ ] GREEN: add `restored_api_access` reconciliation to Day 2 acceptance and runbooks.
- [ ] Run full exact-head CI including no-skips Day 2 contracts and PostgreSQL 18; record failures as blockers, open draft PR and update GitHub #728/Linear MD-6 with precise source vs live distinctions.
