## 26 November 2026 — Prompt 03 connected-read cursor generation fence

**Source patch; not release-qualified.** Base `43d99fd64467492a7da809cda0ae178191e53981`; test-first `e0f56797fb74b56763ee955b6825173377f6149a`, source/call-site `cff51dc6f037c52f7435c35767d887af3c8e7afe`. Reject stale full-read results crossing cursor reset and invalid-cursor recovery after a newer sync advanced the state. Existing lock and grant checks retained. Isolated copied-method SQLAlchemy SQLite RED 2 failed/1 passed; GREEN 3 passed. Full repository CI, PostgreSQL and operated-provider qualification pending. [Contract](P03_CONNECTOR_CURSOR_GENERATION_2026-11-26.md). No external effects, deployment or authority changes.

Reconcile this PR-specific record with the canonical [PROGRESS.md](PROGRESS.md) during reviewed merge. Shared history remains unchanged on this branch.
