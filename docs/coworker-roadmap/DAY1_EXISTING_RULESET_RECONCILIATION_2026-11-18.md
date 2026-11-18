# Day 1 — Safe reconciliation of the existing GitHub main ruleset

**Status:** Source-only operator candidate. This document is not an authorization to mutate repository settings, approve a pull request, or release the pilot.

## Verified discrepancy (18 November 2026)

The live repository-owned ruleset \`27324410\` targets default branch \`main\`, is active, and has no bypass actors, but does **not** require an independent approving review or the checked-in first-party CI statuses. The committed \`infra/github/main-ruleset.json\` requires one approving review, stale-review dismissal, last-push approval, resolved review threads, and strict \`test-and-build\`, \`coworker\`, and \`ci-merge-gate\` checks pinned to GitHub Actions app 15368.

The existing \`scripts/apply_main_ruleset.py\` correctly **refuses to create a second ruleset** when a protected or ambiguous main branch already exists. Do not relax that creation operator. For the one already-existing rule, a separate, explicit repair path is now available.

## Safe procedure for a separately authorized repository administrator

1. Verify the required GitHub App audit identity is configured in the protected \`v01-governance\` and \`pa10-staging\` environments. Use a repository-scoped credential with Administration write permission for the operator's readback and PUT request. Do **not** commit, paste, log or pass a token as a command-line argument.
2. With the approved administrative identity, inspect the repository's Settings → Rules and confirm the current policy ID, source, active scope, bypass list, existing review constraints, and all required checks. Preserve any stronger or inherited rule.
3. Obtain the current full \`main\` SHA and **first run dry-run only**:

   \`\`\`bash
   python -m scripts.reconcile_main_ruleset \
     --repository rumman52/Shuddho \
     --expected-main-sha <40-character-observed-main-sha>
   \`\`\`

   The result reports \`status=dry_run\`, \`would_create=false\`, exact ruleset ID, \`observed_sha256\`, and planned first-party checks. It does not make a PUT request. If configuration is ambiguous, an extra or stronger review rule exists, the ruleset differs, or bypass details are redacted, the command fails without writing.

4. Have a **different administrator/reviewer** inspect the dry-run and approve that precise proposed policy change. Only then, with the same source SHA and exact observed fingerprint (do not re-use stale evidence), run:

   \`\`\`bash
   python -m scripts.reconcile_main_ruleset \
     --repository rumman52/Shuddho \
     --expected-main-sha <40-character-observed-main-sha> \
     --expected-current-ruleset-sha256 <64-character-dry-run-fingerprint> \
     --confirm-repository rumman52/Shuddho \
     --confirm-ruleset-id 27324410 \
     --apply
   \`\`\`

5. The tool re-reads the main SHA and every active main-targeting ruleset before the one \`PUT /repos/rumman52/Shuddho/rulesets/27324410\`. It never issues a ruleset POST, DELETE or duplicate PUT. After a response, it re-reads the effective ruleset, pins its original ID, confirms active protection with the existing V-01 audit, and still reports \`qualified=false\`. If the response is lost, readback is attempted before any result; **never rerun the PUT blindly**.
6. Run one negative-control PR that remains unmergeable when checks are pending/failed, reviewer approval is absent or stale, or a review thread is unresolved. Run one independently reviewed positive-control PR with current-head successful checks. Record exact rule ID, main SHA, check IDs, reviewer identities and outcomes in issue #727 without secrets.

## Guarantees and limitations

- The command refuses non-\`rumman52/Shuddho\` repositories, unexpected source/scope, redacted or nonempty bypass lists, duplicate/unknown rules, stricter-than-target approvals, extra status checks, and other settings it cannot safely preserve.
- An exact source SHA and fingerprint prevent most stale configuration updates; like other REST read-then-write operations, they cannot guarantee perfect atomicity against a separate concurrent administrator. The final readback and independent merge controls remain mandatory.
- A clean configuration readback is **not** proof of effective native enforcement. \`qualified=false\` and \`merge_enforcement_verified=false\` remain hardcoded.
- This does not configure GitHub App credentials, grant billing authorization, perform staging restores, deploy Render or Vercel, or establish independent holdout custody.
- Official GitHub REST update contract: https://docs.github.com/en/rest/repos/rules#update-a-repository-ruleset

**Related:** \`docs/coworker-roadmap/V01_SAFE_RULESET_APPLY_OPERATOR_2026-10-25.md\`, \`docs/V01_GOVERNANCE_RULESET_AUDIT.md\`, issues #727 / #291 / #665.
