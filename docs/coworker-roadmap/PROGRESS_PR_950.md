## 26 November 2026 — Prompt 03 selected-memory persistence fence

**SOURCE PATCH / NOT RELEASE-QUALIFIED.** Base `43d99fd64467492a7da809cda0ae178191e53981`; test-first `4ddd9b916adcfa5d200d361b50a747c465716789`, source `e3496fe15d6c83be114d843d68d878c61eea9c22`, additional deletion regression `04622491071e81a44c976a63ed9d17c173762a9c`. Lock selected owner/workspace fact rows in stable ID order and refresh ORM state before validation; validate expiry after locks. Isolated copied-function SQLite/dialect probe RED 2 failed/1 passed, GREEN 3 passed; PostgreSQL and full CI pending. [Contract](P03_MEMORY_PIN_COMMIT_FENCE_2026-11-26.md). No staging acceptance or deployment, provider, flags or data changes.


**Extension:** Child draft/export checkpoint and artifact publication revalidate selected memory in their persistence transactions; model reservation and phase entry also checked. Account reference/mutation lock ordering aligned. Test commits `31664a1288e716e2086b1c77dbf4b79032b6e0dd`, `404cf67a90e25b17170f9ec65531cd2fdc32fcca`; source `72feee2a78a89b925341a1e0eaf744a0a75101ec`. Isolated child persistence probe RED 6 failed/1 passed, GREEN 7 passed; full CI and actual PostgreSQL/hosted evidence pending. [PR #950](https://github.com/rumman52/Shuddho/pull/950).

**Accepted proposal deletion:** nullable FK links now detached atomically before owner-scoped fact deletion; accepted-history replay never recreates or rebinds deleted facts. Tests `82e5910c16906393abda845b928b73cca5e23225`, source `eb1f8656015946cfdacb5d6c32dd182ad156a6c4`. Isolated FK-enabled SQLite RED 2 failed/1 passed, GREEN 3 passed. Exact repository regression and CI pending. No migration or change to historical proposal retention.

Reconcile this PR-specific record with the canonical [PROGRESS.md](PROGRESS.md) during reviewed merge. Shared history remains unchanged on this branch.
