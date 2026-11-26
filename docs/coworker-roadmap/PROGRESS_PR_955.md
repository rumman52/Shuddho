## 26 November 2026 — Prompt 01 / strict release-evidence Unicode and publication parity

**SOURCE_IN_PROGRESS / staging NO-GO.** Base `43d99fd64467492a7da809cda0ae178191e53981`; tests-first `627703002ac9e90542f3593d45ebcc7ce3c37230`; source `ae050e8427d01fabde100bc7f65d341366bbf9f5`; mandatory CI wiring `be6a0c30a122d6c9eb8cec274fa96dd498032172`. Reject escaped lone surrogates and refuse private evidence that its own strict reader cannot decode before publication. Hash-verified complete modules: RED 12 failed/1 passed; GREEN 13 passed, combined existing/new 28 passed; py_compile and both mandatory JUnit module checks passed, zero skips. Valid Bangla/supplementary Unicode and existing byte format preserved. [Task contract](DAY2_STRICT_EVIDENCE_UNICODE_2026-11-26.md). Full exact-head CI, independent review and hosted receipts outstanding; no hosted operation, production activation or billing.

---

Reconcile this PR-specific record with the canonical [PROGRESS.md](PROGRESS.md) during reviewed merge. Shared history remains unchanged on this branch.
