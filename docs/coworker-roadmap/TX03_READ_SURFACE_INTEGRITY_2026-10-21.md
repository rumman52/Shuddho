# TX-03 — fail-closed transaction terms read surfaces (21 October 2026)

## Scope and root cause

At base `c1329e001ddff3a47783d858d9d304bf238498bc`, `_require_current_fresh_terms()` authenticates the persisted terms snapshot before approval binding, but `TransactionRepository.latest_terms()` and `review_surface()` exposed the saved terms without that verification. A corrupted price, terms payload or provider quote ID could therefore be shown as a legitimate human-review snapshot, even though a later approval would reject it.

## Patch

- Use the already-shipped `verify_stored_terms_snapshot_integrity()` function before projecting stored terms through both owner-scoped read APIs.
- Preserve not-found, missing-terms, owner-scope, quote-expiration and external-action execution behavior.
- Parametrized database-tampering regressions cover `terms`, `price`, and `provider_quote_id`, checking both read surfaces for deterministic `transaction_terms_integrity_failed` (409).
- The hash is an integrity consistency check against the persisted snapshot; it is not a separately keyed signature or proof against an actor who can rewrite both payload and digest.

## Qualification gates

- [x] Source fix and three parameterized regressions prepared.
- [ ] Exact-head CI and focused DB tests must pass on this PR commit.
- [ ] Independent current-head reviewer approval must be recorded.
- [ ] Enforceable native `main` protection must be verified under V-01 #484.
- [ ] Real provider execution/staging still blocked by separate qualification gates.

No deployment, provider operation, staging activation, migration or production readiness is claimed. Keep this PR in draft until all required evidence is available.
