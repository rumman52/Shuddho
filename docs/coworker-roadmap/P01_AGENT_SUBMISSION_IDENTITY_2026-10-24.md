# P-01 / C-01 — Agent creation request identity (24 October 2026)

## Baseline and source of truth
- Base: `main` `a14dee4870af05954936b88882e40f6db2374aab` (PR #557 merged).
- Separate in-flight PR #558 is **not** part of this patch.
- Scope: UI-created bounded Agent runs in `apps/web-editor/src/coworker/AgentWorkspace.tsx`. Server-owned admission, run identity, authorization and all ExternalAction enforcement remain unchanged.

## Concrete defect
`submit()` retains `submission.current` after `createAgentRun` succeeds. A later explicit click with an *identical* goal, source set and output language reuses the successful request idempotency key, so the API replays the previous Agent run instead of creating a new one. Reusing the same key is **correct only while the initial response is uncertain**, not after the UI has confirmed admission.

## Bounded behavior change
- On a successful `createAgentRun` response, clear the cached submission key for a new explicit user operation.
- On transport error or lost response, retain the exact key so retry recovers the committed run.
- On changed payload, regenerate the key; never reuse a request key with different contents.
- Reject synthetic/reentrant submit events while the form is busy, disabled or lacks a valid goal, before mutating any request identity.
- Do not autosubmit work, alter a feature flag or the runtime's idempotency guarantees.

## Regression test contract
New React test-renderer suite `apps/web-editor/src/coworker/agentSubmissionIdentity.test.tsx` is explicitly collected by `apps/web-editor/test/run-tests.mjs`. It verifies:
1. Repeating an accepted goal uses a fresh key and creates a distinct run.
2. A simulated lost response following a persisted admission is recovered by the same key/run, then a new explicit start uses a new key/run.
3. Editing an uncertain payload generates a distinct key, preventing the prior binding from silently becoming a new one.

Test module was committed **before** implementation: `00f6f3b9a78fe2f32f20685105e695ab9405aea2`; runner entry was committed before implementation: `a453a92c3b3f5226d3a72292ab3bf2a9629c96bf`. Source correction: `9f8aead25a17322db30360bf2ad255580d5e5530`. This is test-first commit ordering; **observed failing-first execution is not claimed**.

## Qualification and release boundary
Required verification is the web test runner and production TypeScript/Vite build on the exact PR head, followed by full mandatory `test-and-build`, `coworker`, `ci-merge-gate` and independent human review before a protected merge. Record exact run identities and failed/skipped coverage. Unit UI tests use synthetic API records and do not substitute for real browser navigation, multi-user staging or provider receipt evidence.

Implementation: narrow UI correction on review branch. Repository CI: pending. Staging: not verified. Production qualification: not established. Activation: none. All 17 A/C/P/V acceptance criteria retain their independent evidence gates, and V-01 native protection is not configured in the connected read-only view.
