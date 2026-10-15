# CW-09 — persisted owned browser-source artifact (15 October 2026)

**Base:** `main` `599002b8e80089ac658548fdd6ed9e3dafc5ec22` (PR #405 merged). **Branch:** `codex/cw09-owned-browser-source-artifact-20261015`. **Outcome:** an authorized Runtime v3 `browser.read` that captured nonblank rendered text yields a retrievable, owner-bound source artifact, not only a transient 1,200-byte excerpt. This builds upon PR #404's truthful bounded page digest and PR #405's terminal expiry guard. Default-off Agent browser remains default-off.

## Observed gap
Current `read_agent_capture` opens at most 8,192 bytes of untrusted worker-observed visible text, but final receipt settlement scrubs the sealed body. Only a short excerpt remains in `ToolReceipt`; Shuddho cannot inspect the complete captured bounded text after finalization. Existing `Artifact`, `ObjectStore`, `RetentionService` and owner-checked artifact download already provide a suitable durable store. A new source schema or duplicate file authority is unnecessary for this increment.

## Committed design
- Derive the artifact ID, private object key, code-owned filename and safe `text/plain; charset=utf-8` media type exclusively from UUID owner+browser command ID. No model-nominated object key.
- In the trusted Agent runtime, after the owner/expiry-verified capture getter, write the **exact bounded captured text** to the existing private object store, read it back, verify equality, and fail closed if storage is disconnected or corrupt. Do not persist blanks as successful content.
- In the final existing `AgentRepository.finish_invocation` transaction, revalidate current authorization and live browser session, exact command owner/identity/lease result, hash and size, submitted source bytes, URL, truncation, excerpt and untrusted trust label. Insert one `Artifact(artifact_class="browser_source")` and the `ToolReceipt` atomically; the existing helper scrubs transient sealed text on the same commit. Retried duplicate settlement cannot create a second artifact ID. Never add a separate approval or activation ledger.
- The ToolReceipt exposes an `artifact_id` and SHA bound to the browser command; a user can fetch its bytes via the **existing owner-authenticated artifact content/download route**, not a new unauthenticated endpoint. For `browser_source`, the download endpoint explicitly returns the authenticated content path and never a transferable presigned object-store URL, including on S3; ordinary export URL behavior stays unchanged. Do not include private content in the general task artifact list, Temporal history, or normal audit logs.
- `RetentionService.referenced_object_keys` already includes every `Artifact.object_key`; account erasure deletes owned artifact rows and the underlying blobs. If the private blob write succeeds and the Agent transaction later rolls back (cancellation/expiry), the object remains unreferenced; the existing aged `cleanup_orphans` reconciler must delete it. It must not be misreported as a verified artifact.
- This is a **captured visible-text snapshot** only. Its SHA-256 is of the bounded UTF-8 captured source, **not** upstream full HTML bytes, raw HTTP response, or unbounded text. Version identity is the immutable command ID, not a fabricated HTTP ETag. Per-source delete/revocation (distinct from account erase), cross-project grant checks, operated object-store outage, real browser/SSRF and prompt-injection qualification remain incomplete acceptance items.

## Falsifiable checks
1. An owner-run, claimed, successful Agent browser command with text creates exactly one owner-scoped `Artifact` row with the same SHA and byte count as verified command provenance, and the bytes round-trip from private store; command ciphertext is scrubbed on settlement.
2. Another owner cannot read the artifact. Metadata-only and whitespace-only pages do not mint artifacts or fabricate content. Untrusted page text never authorizes a tool.
3. Storage failure raises a typed error and commits no Agent receipt or Artifact; retry against the *same* immutable completed command can succeed after storage recovery. Forged summary/hash is rejected and cannot poison legitimate receipt.
4. Real PostgreSQL and local private ObjectStore tests execute, plus full final SHA required `test-and-build`, no-skip `coworker` and `ci-merge-gate`; collect independent review and staged S3/egress evidence separately.
5. No migration, frontend activation, external effect or API permission expansion.

## Gate
Review PR and exact-head CI. **Do not merge, deploy or activate automatically.** The broader CW-09/CW-10/CW-11 and architecture/core acceptance inventory remain incomplete until their own evidence is collected.
