# Superpowers TDD execution plan — Day 10 operator receipt signing boundary

## Outcome
Make `scripts/cohort_release_ledger.load_json_object(Path, label)` reject ambiguous/symlinked/oversized/nonfinite JSON **before** a valid HMAC-signed event can be appended. Do not change the actual HMAC chain, stored schema, signer key, replay order or independent human pilot gates. Use base main `a3e8dba039436e2553d10f2147f886cdf1877815` and draft PR #908.

## Units and verification
1. **Reproduce failure first** in `tests/test_cohort_release_ledger.py`. Reuse `artifacts` and `append` for a real deterministic signed event: shadowed `STOP_ROLLOUT` before `ELIGIBLE_FOR_EXPANSION`, symlink rollout, oversized plan, nonfinite cap, directory status, and valid signed-hold compatibility. Commit only tests and inspect failing GitHub Actions Python test log.
2. **Smallest production correction** in `scripts/cohort_release_ledger.py`. Reuse the existing bounded, final-no-follow, strict JSON `read_json` instead of permissive `json.loads(Path.read_text)` and translate errors to `ReleaseLedgerError`. Do not modify `append_event`, `verify_entries`, schema versions or provider actions.
3. **Verify RED/GREEN**. Required default Python tests + strict Coworker test gate, frontend, browser, PostgreSQL compatibility and controlled release-contract checks; verify exact commit SHA and job results. Distinguish source suite green from authentic staging or protected independent D scoring.
4. **Checkpoint** in `docs/coworker-roadmap/DAY10_LEDGER_OPERATOR_RECEIPT_TRUST_BOUNDARY_2026-11-24.md` and `PROGRESS.md`; document residual `load_json_object` vs `file_sha256` separate-read race and concurrent ledger append limitations. Link PR #908 to tracker #736 and branch governance #484.
5. **Human operators**. Keep unresolved custody (40 case/80 blind/20 operated), frozen 43 flags, distinct Founder+C release signoffs and independently authorized 5–10 HTTPS admission as blockers. GitHub administrator must enforce native required review and required checks. Do not merge unreviewed or deploy any environment.

## Observed at implementation
Test-only commit `8dfdf9aaab3a35d14e41430e172c522e506d340e`; [RED CI #45246504107](https://github.com/rumman52/Shuddho/actions/runs/45246504107): 4 expected failures, 3,783 passes, 109 skips, 6 warnings. Source correction commit `ace514e03d114b6f91040904c879e2cb3e804d75`. Reviewer must check actual final-head CI before crediting repository verification. All external release statuses remain NO-GO.
