## 26 November 2026 — Prompt 05 downstream pilot authorization recheck

**SOURCE_IN_PROGRESS / NO-GO.** Extend #940. Tests `176d366775dc3accd79c6cd97671c8c584e09e98`; shared validator `aeb917434cad1d1f3e93cf36a71c2b752e69c8f1`; consumer `0f09ddf60d8a6f2cc68474ec3118708e4a30a5a2`. Old READY receipt without current exact scope, spend and expiry previously passed post-admission verification. Isolated RED 10 failed/3 passed, GREEN 13 passed; integration guards for expiry before token read and during probe committed. Prior head test-and-build 3945 passed/109 skipped and 551 passed separate suite does not qualify new head. No independent approval or activation. [Contract](P05_PILOT_APPROVAL_TERMS_2026-11-26.md).

## 26 November 2026 — Prompt 05 independent pilot approval terms

**SOURCE_IN_PROGRESS / controlled pilot NO-GO.** Base `43d99fd64467492a7da809cda0ae178191e53981`; tests-first `40eac91b34e5f30e452005b6323967550f9de2d1`; source `e40eb4aaa5dc482224df1f9a7fe1c08962083757`. Both claimed signoffs and their summary now require identical exact rollout-scope digest, integer nonnegative USD-micro-unit spend cap and future expiry. Synthetic isolated receipt guard RED 12 failed/3 passed, GREEN 15 passed; full checkout blocked by DNS, repository CI and independent human review outstanding. [Task contract](P05_PILOT_APPROVAL_TERMS_2026-11-26.md) and updated Day 10 runbook. Prior records missing terms are nonqualifying; no signatures, approved spend, operational evidence or activation manufactured.

Reconcile this PR-specific record with the canonical [PROGRESS.md](PROGRESS.md) during reviewed merge. Shared history remains unchanged on this branch.
