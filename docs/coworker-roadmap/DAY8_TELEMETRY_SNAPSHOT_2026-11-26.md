# Prompt 04 / Day 8 — single-snapshot telemetry privacy boundary (26 November 2026)

- Task: D08.T02–T05; issues #734 / #584; [draft PR #933](https://github.com/rumman52/Shuddho/pull/933).
- Base: `43d99fd64467492a7da809cda0ae178191e53981`; branch `fix/day8-telemetry-snapshot-20261126`.
- Test-first commits: `31f48b04458f6b32cf58614a2f1109199f876b9c`, `c649e6fa9240396b5e20de70d77065034a62ee7d`, `6a6cd0124bc6318ef21777bee8e615f049c17bb9`; source `cd77f5ddcee2d2743d733aec310b9a390c16ab9a`.
- Root cause: allowlisted enum values were read repeatedly from caller-controlled Mapping; a changed value could reach the injected sink without validation. Frozen policy accepted mutable allowlists, spoofable string subclasses, boolean approval retention and overridden permits. Broken mapping access and sink introspection could escape the error-isolation boundary. Denied policy could inspect the sink.
- Changes: single private plain dictionary snapshot; exact plain string keys/metadata; immutable frozenset of exact string tuples; exact EventPolicy type; exact integer approved retention; generic error on snapshot failure; deny before any sink introspection; isolate introspection errors. The canonical event, buckets, nullable counts, provider checks, approved host pairs and sink acknowledgement semantics are unchanged. Read-only Mapping support retained.
- Tests: byte-for-byte local copies of baseline source blob `91631ad08d8302b4d6a761cac19af68f39280fb9`, corrected source blob `3d83f2cab9c50a8ba0785b81cd5881504776b77e`, and final tests blob `c5dd749788e37c9b66f12a28e0c7e56d8e896c41`; verified with git hash-object. `python -m pytest tests/test_day8_telemetry_privacy.py -q`: RED **15 failed / 85 passed**, GREEN **100 passed / 0 failed / 0 skipped**. Python 3.13.5 local standalone module/test pair, not full checkout. All inputs synthetic; sink is in-memory only. Source CI [45776247190](https://github.com/rumman52/Shuddho/actions/runs/45776247190) queued at readback; documentation commit requires its own exact-head CI.
- Boundaries: no SDK, network sender, telemetry enablement, policy storage, live consent change, hosted mutation, provider execution, new authority or deployment. Not evidence of authenticated PostHog delivery. Founder/C approval still required for project, region, retention, consent/opt-out, deletion, actual destination/transport and egress, including service identity. Keep existing release gates.
- Rollback: revert source and tests together; no schema change. Residual: Python objects from trusted server code are not an isolation sandbox; transport and durable consent are still missing and require separately reviewed authorization. 
- Next: exact-head required CI, distinct human review, protected merge only; establish approved staging worker and privacy decision separately.

| Level | Status |
|---|---|
| Source | Locally verified focused module and tests; draft |
| Repository verification | Exact final-head CI and review outstanding |
| Staging / independent acceptance | BLOCKED_EXTERNAL |
| Production / activation | NO / NO |
