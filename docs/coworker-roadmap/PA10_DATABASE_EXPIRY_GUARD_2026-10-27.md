# PA-10 staging database expiry admission guard — 27 October 2026

## Evidence

The connected Render workspace reports `shuddho-staging-db` on the `free` plan, status `available`, with expiry `2026-10-31T17:11:33.79468Z` (23:11:33 Asia/Dhaka on 31 October). A read-only SQL attempt through the Render connector was denied because the database IP allowlist is empty; this is not evidence that the database is empty, and the allowlist was not changed.

## Implementation

`scripts/pa10_database_expiry_gate.py` is a pure, read-only gate for Render metadata. It fails closed if the plan is missing, a free plan has no inspectable expiry, the expiry is malformed or timezone-naive, the database is already expired, or expiry is within seven days. A paid plan without an expiry timestamp passes the lifecycle gate; a present timestamp is still checked. It prints only non-secret lifecycle evidence.

Both `pa10-staging-prerequisite-preflight.yml` and `provision-pa10-staging-worker.yml` call this gate immediately after retrieving Render database metadata and before extracting/using the private connection string. The intent is to stop preflight or paid-worker mutation when the backing database is too close to expiry to safely finish acceptance.

## Limitations and owner action

This gate is **not** a backup or retention operation. It cannot extend the expiry, restore data, prove backup integrity, or choose a paid plan. An authorized owner must inspect the database in the Render dashboard, take and verify a restorable backup, decide whether to retain/upgrade/migrate it, and complete that action before the expiry. The current live `main` remains unprotected and the production API auto-deploys from `main`; do not merge this proposal while the release governance incident is unresolved.

The guard intentionally fails for the currently reported free database until a retention action is complete. It has no network access, uses no secrets, and makes no provider changes.
