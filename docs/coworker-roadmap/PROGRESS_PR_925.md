## 26 November 2026 — Day 8 comparison evidence boundary (#734)

**SOURCE PATCH / NO-GO.** Base `f7138e2025f6f5719aea4f4babfcc3549fae324b`; test-first `d533b853a743eb441c1fd213777b3f527094f0fd`, source `796467d1112dbc7b19a19cf557de2464c0ff1d38`. Day 8 input reopened a checked pathname and accepted exponent-overflow JSON numbers. Reuse the existing bounded no-follow evidence reader and strict parser, preserving the 2 MB acceptance limit. Isolated excerpt pytest RED 3 failed / 4 passed; GREEN 7 passed. Full checkout blocked by DNS; exact-head CI and independent review pending. See [task contract](DAY8_COMPARISON_EVIDENCE_BOUNDARY_2026-11-26.md). No staging, production, flags, telemetry, provider spend or pilot acceptance changes.

