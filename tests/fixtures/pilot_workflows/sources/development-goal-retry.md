# A-02 / P-01 — bounded goal-run admission replay (24 October 2026)

## Baseline and scope
- Source baseline: `main` after merged PR #558, SHA `d1621e5e320bce44ce4e5f5c3c773df39412fdc1`. Concurrent Agent-form correction PR #559 is a separate review branch and is not duplicated.
- Change limited to the personal-goal **Run bounded work now** UI admission path (`GoalWorkspace.tsx`), focused React tests and standard web test registration.
- No change to server-side idempotency, goal revisions, budgets, Temporal orchestration, approvals, flags, provider actions, live deployment or schema.

## Root cause and impact
The existing `GoalWorkspace.runNow` passed `crypto.randomUUID()` directly to `client.runGoal` **on every attempt**. If a goal run committed to the durable API but the response was lost, the user's same-action retry received a fresh key and could admit an unintended *second* bounded Agent run, consuming budget and potentially running twice. This breaks the expected A-02 duplicate-effect prevention and P-01 admission identity invariants at the UI boundary.

## Implemented behavior
1. Bind the request identity to the selected goal ID, expected goal revision and output language. Keep the same key while the accepted outcome is unknown.
2. Use a fresh key if the user selects a different goal/revision/language; the server remains the ultimate authority and rejects stale versions.
3. Clear the successful request identity **as soon as** `runGoal` confirms admission, *before* fetching the refreshed goal; a refresh error must not make the next deliberate click replay the already admitted run.
4. Use a synchronous `runInFlight` ref guard along with the existing busy/UI guard; this prevents reentrant handlers before the React state commit, while allowing a genuine retry after failure.
5. Preserve the intentional distinction between “recover the previous uncertain request” and “start another explicitly requested bounded run.”

## Test and evidence contract
- `apps/web-editor/src/coworker/goalRunIdentity.test.tsx` covers four cases: two intentional confirmed starts; lost response accepted once then same-key retry; selection of a different goal after unknown response; accepted run followed by goal-refresh error and fresh next click.
- Tests and runner registration committed before implementation: `8d19c491c2ea697797fca9ed805513c6c78c06c7`, `422a8be8a27a1136eb60eca44978358d9bd0dc03`, `6526f242f55177d76ae7d8e3093d2eebbdeb1d80`. Source fix: `0130fff4a3bff1398d82486c33da947900ce8590`.
- No executed **RED** claim is made from commit ordering. Require exact-head `npm run test --workspace @shuddho/web-editor`, `npm run build --workspace @shuddho/web-editor`, `test-and-build`, `coworker`, `ci-merge-gate` and independent human approval. A PR code test is not operated live duplicate-effect evidence.

## Release boundary
Implemented on a separate review branch; repository CI pending; staging and real network-loss recovery unverified; production qualification not established; activation not requested. V-01 native policy remains unconfirmed: unprotected merge capability does not authorize bypassing final-head review/check requirements. No provider sends, purchases, billing, privileged config or production flag changes.
