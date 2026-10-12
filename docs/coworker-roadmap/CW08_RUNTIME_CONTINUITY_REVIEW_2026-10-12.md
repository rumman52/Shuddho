# CW-08 runtime continuity security — 12 October 2026

Reviewed base: `631b1f1c2b3cd3cca9b38a4d650950dd955e4580`, merged PR #371.

## Findings fixed by this branch

1. **Expiration on worker read:** `ContextService._run_and_sources` formerly considered an uploaded, nondeleted document version active even after expiration. It now marks those versions invalidated. The context producer also rechecks current ownership, document deletion, upload state, SHA-256, size and expiry immediately before and after object-storage retrieval. No model-facing excerpt is emitted after a detected revocation. A database change racing just after the final check remains a theoretical TOCTOU window; require operator review for stronger transactional protection.
2. **Owned workspace inventory:** `GET /api/v1/workspace-manifest` returns owner-scoped document-version and artifact metadata, memory *metadata only* when memory is enabled, and a canonical SHA-256 revision digest. Storage object keys and memory values are never included. Lists are explicitly bounded and report truncation. This digest is a change detector, not a signing key, authorization token, durable version history, or proof of provider-side state.
3. **UI context selection:** The Conversations workspace can select up to five available version-pinned documents. The backend revalidates each selected version independently both when a message is saved and when an Agent run is admitted. No chat message or source selection authorizes email sending, booking, payment or purchase.

## Tests and qualification

The existing heavy coworker CI mandate for `tests.test_conversation_context` now covers worker-time expiry/revocation and manifest identity/revision regression tests. Backend and frontend CI of the exact branch must both pass before merging.

## Remaining CW-01..08 exit conditions

CW-01 safety code and CW-05–07 foundations are on main. CW-02 requires 16 real failure-injection outcomes and independently trusted provider mutation evidence. CW-03 requires a qualified external staging freeze, and CW-04 needs an operated read/draft/goal/reminder/restore/rollback workflow trace. CW-08 still needs durable reviewed memory lifecycle, browser accessibility/reconnect qualification, provider- and process-crash observations, and exact rollout evidence.

Do **not** activate unqualified transaction, automation or external-action providers from this branch. No live credentials, external staging failure injection, deployment or production mutation were performed.
