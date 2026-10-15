# CW-09 — individual private browser source erasure (15 October 2026)

**Direct integration baseline:** `main` `896b5014bc371f5549fb9daa815338d932506a73`, which includes [PR #406](https://github.com/rumman52/Shuddho/pull/406) retained browser-source Artifact (final PR-head CI #38696966902 and merged-main CI #38699094958 passed all three jobs). **Implementation branch:** `codex/cw09-source-erasure-main-20261015`. Historical [PR #407](https://github.com/rumman52/Shuddho/pull/407) merged only into an older feature branch after #406 had entered `main`; its final-head CI #38697102026 passed but its deletion endpoint was **not** on `main`. This new direct-main implementation ports that tested delta while preserving current `main`. No permission to merge/deploy/activate.

## Reproduced capability gap
The parent source artifact persists the full *bounded rendered visible text* in an owner-bound Artifact and private ObjectStore. Account-level erase exists, but a user cannot revoke **one** source, and a completed Agent `ToolReceipt.summary` retains a reusable untrusted excerpt. Deleting only the object bytes would leave usable content in Agent observations and unrevoked database metadata.

## Bounded integrated behavior
- Add authenticated `DELETE /api/v1/browser-source-artifacts/{artifact_id}`, wired to the existing `RetentionService`, strictly limiting the operation to an owner-owned Artifact with `artifact_class="browser_source"`.
- Require the source to be referenced by **exactly one** owned `browser.read` tool receipt. Lock the associated AgentRun and reject deletion while it is active, because in-flight model work might already hold content. The user must finish/cancel that Agent run before deletion.
- In one PostgreSQL/SQLite transaction, lock and delete Artifact metadata, remove its source URL/digest/byte count/title/excerpt and artifact identifier from the linked ToolReceipt, update it to `observation_scope="source_deleted"` / `source_deleted=true`, and audit the deletion. The existing `verified_observations` boundary is updated to expose the truthful deletion flag, **never** previous source text.
- Then delete the private object through the existing `ObjectStore`. If storage deletion fails, report `metadata_erased=true, object_deleted=false, object_cleanup_pending=true` truthfully. Fresh authenticated downloads remain denied because metadata is gone. The existing aged orphan cleanup can later remove the unreferenced object, but **physical deletion is not claimed until confirmed**.
- The parent implementation already prevents browser-source presigned S3 URLs. Any already-running authenticated content GET might complete before revocation linearizes; the endpoint refuses all **subsequent** lookups. No extra tool grant, mutation registry, schema, S3 bucket, background scheduler, or production feature flag.

## Falsifiable checks
1. Another user deleting the source receives 404; correct owner deleting during an active Agent run receives typed 409 with no data loss; owner deleting after terminal run gets owner-scoped deletion with actual stored bytes absent and linked ToolReceipt redacted.
2. Existing artifact content and metadata GETs return 404 after commit; a future Agent `verified_observations` read reports `source_deleted=true` and no source URL/text/digest/artifact ID; repeat deletion remains denied.
3. Simulated object-store delete outage cannot falsely claim physical erasure. Metadata and receipt revoke, orphan remains eligible for canonical later cleanup.
4. A real PostgreSQL run checks JSON receipt selection, lock/retention transaction and object-store deletion. The full exact-final-head `test-and-build`, zero-skip `coworker` and `ci-merge-gate` must pass. Independent adversarial review and operated staging remain separate.

**Limitations:** Source may already have influenced previously generated final reports/messages; this scope revokes the source artifact and stored tool observation, **not** historical unrelated user-authored outputs or already-running external model inference. The parent capture is bounded visible text, not raw page HTML. No claim of instant deletion if object-store deletion fails, no full CW-09, CW-10/CW-11 or production readiness.

**Keep this direct-main integration pull request draft until matching CI and independent review. Do not auto-merge, deploy or activate.**
