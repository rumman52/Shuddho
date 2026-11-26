# Day 8: private dispatch and worker observability

## Scope and semantics

- Existing cohort health collector reads the existing task, agent outbox, durable worker claim and worker instance ledgers. No new table, scheduler, provider call or telemetry destination.
- Dispatch statistics cover outbox-backed admissions of configured cohort owners whose creation time lies in the closed observation interval `[cutoff, now]`. Inline child work is excluded. Use only the earliest recorded claim of the matching resource type on the configured queue. Retries do not inflate the sample denominator. Admissions with no such claim or an invalid first-claim clock remain in explicit separate counters; admissions = samples + unobserved + invalid_clock. Percentiles are nearest-rank, in integer milliseconds, and null if there are no valid samples.
- Worker inventory is queue-wide, not a cohort-owner attribution. Active rows use the existing starting/running/draining states and 15-second worker heartbeat TTL. Fresh running rows have a valid heartbeat no older than that TTL; stale includes all active states; invalid chronology includes a future heartbeat or a heartbeat before start. Starting/draining are overlapping state counts. Oldest valid heartbeat age is rounded down to whole seconds and null if absent.
- These are durable dispatch lag and inventory measurements, not Temporal workflow execution lag, polling evidence, external notification delivery, or production SLO proof. Do not use them to authorize release. No STOP thresholds changed.
- Existing OpenMetrics export adds fixed metric families `shuddho_coworker_cohort_{task,agent}_dispatch_*` and `shuddho_coworker_queue_worker_*`; no identifiers or metric labels. Legacy snapshots lacking measurements render NaN, not zero, including missing provider-capacity lease fields. No external exporter or public endpoint is enabled.
- The collector adds three scoped SQL queries; validate EXPLAIN on a disposable migrated PostgreSQL database using representative data before deciding whether indexing is needed. No production DDL or speculative index.

## Implementation and verification checkpoint

- Base: `43d99fd64467492a7da809cda0ae178191e53981`.
- Regression-first: `48913f940f54a31fa9ce7e6ae10adad030940eb4`.
- Source and collector integration: `783ed1aca9a9ac563f4a7fa3745c4b43704980bf`.
- Local: four new SQLite tests failed before implementation (missing collector); two export regressions failed against the copied original renderer. All six passed after implementation using the new collector and copied renderer with a limited schema fixture matching the required model columns. This is not full repository integration, migration validation, or PostgreSQL evidence.
- Exact-head required CI and distinct independent review pending. Production activation, PostHog registration and live measurements remain unauthorized/unverified. Day 8 release acceptance stays blocked.
