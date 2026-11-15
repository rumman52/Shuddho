# Plan: make the V-01 ruleset audit failure actionable

Date: 2026-11-16
Base: main at 04788a8f9855bace973fc794917cb625ef9ffbfe

## Goal

Keep the main-branch governance audit fail-closed while reporting the exact reason
when GitHub redacts `bypass_actors` from the read-only Actions token.

## Evidence

The repository has an active main ruleset with one required approval, stale-review
dismissal, last-push approval, thread resolution, strict required checks, and no
bypass actors in the owner-authorized ruleset view. The push-only CI audit uses
the read-only `GITHUB_TOKEN`. GitHub's ruleset API deliberately omits
`bypass_actors` unless the caller has write access to the ruleset.

## Chosen approach

1. Add a regression test proving an active main ruleset with a redacted
   `bypass_actors` field fails with an explicit owner/admin visibility message.
2. Implement that diagnostic without treating a missing field as an empty list.
3. Keep the audit fail-closed; do not grant a privileged token to PR code, weaken
   the bypass check, or alter the live ruleset.
4. Update the staging progress record with the current verified governance and
   infrastructure state.
5. Run exact-head CI and request independent review. Do not merge without the
   required approval and passing merge gate.

## Non-goals

- No changes to GitHub rulesets or branch protection.
- No privileged token creation or secret configuration.
- No Render worker provisioning, billing changes, production deploy, database
  DDL, live backup, external provider calls, or capability activation.

## Acceptance

- The regression test fails before the code change and passes afterward.
- Existing audit tests remain green.
- CI is green on the final PR head.
- An independent maintainer reviews the final head before merge.
