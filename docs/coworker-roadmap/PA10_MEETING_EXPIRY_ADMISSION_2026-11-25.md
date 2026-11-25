# PA-10 meeting expiry admission contract

- Objective: a delayed scan or concrete meeting occurrence cannot admit a new run after owner-approved automation expiry.
- Base: `67d187f972c8069e4369ebc9fdb28dae55c40e3f`.
- Branch: `fix/pa10-meeting-admission-clock-20261125`.
- Existing interfaces: `AutomationRepository.accept_meeting_scan` and `accept_meeting_occurrence`.
- Test-first: `0be3def01dcaaa15281f057036806a8a183d74b2`, parameterized existing calendar fixture preserves successful path and adds delayed expiry denial, including direct entry and zero runs/notices.
- Root cause: historical scan/admission argument is not a reliable current authorization clock. Compare expiry against the later of the supplied time and fresh UTC time in each admission path.
- No schema, connector scope, tool grants, approval boundary, notification transport, or Temporal identity changes.
- Focused command: `uv run --extra coworker pytest tests/test_connector_reads.py -k meeting_coworker -q -rs`.
- Local isolated predicate check reproduced both original errors and checked corrected conditions. Full integrated test was not run locally (GitHub clone DNS blocked).
- Rollback: revert code and test together; no database migration.
- Residual: broader historical-clock/catch-up behavior and revocation races require separate review; this slice only corrects expiry admission.
- External: persistent staging worker, credentials, approved budgets, frozen release, actual provider and Temporal evidence.

| Level | Status |
| --- | --- |
| Implemented | Proposed, source commit 58ebcbdbdb55db492af53582a3544871b46a2fd9 |
| Repository verified | Pending exact-head CI and independent review |
| Staging verified | No |
| Production qualified | No |
| Activated | No |

No synthetic evidence promoted to staging qualification.
