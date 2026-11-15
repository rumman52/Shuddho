# Plan: make the V-01 ruleset audit accurate for read-only tokens

Date: 2026-11-16
Base: main at 04788a8f9855bace973fc794917cb625ef9ffbfe

## Goal

Keep the V-01 source/configuration preflight useful without claiming that a
read-only Actions token verified ruleset bypass actors that GitHub redacts.

## Evidence

The repository has an active main ruleset with one required approval, stale-review
dismissal, last-push approval, thread resolution, strict required checks, and no
bypass actors in the owner-authorized ruleset view. The push-only CI audit uses
the read-only `GITHUB_TOKEN`. GitHub's ruleset API omits `bypass_actors`
unless the caller has write access to the ruleset.

## Chosen approach

1. Add regression tests for both visible-empty and redacted `bypass_actors`.
2. Report a redacted field as `bypass_actors_visibility=redacted`; never infer
   that it is an empty list.
3. Continue to reject explicit bypass actors, missing branch protection, and
   missing/invalid review or status-check rules.
4. Keep the audit result at `qualified=false` and require owner-admin
   verification plus native negative/positive merge-control tests.
5. Keep source admission separate from live staging qualification. The manual
   provisioning workflow still requires exact-head CI, the explicit
   `PROVISION` input, and protected staging-environment approval.
6. Do not grant privileged credentials to PR code, alter the live ruleset, or
   weaken Day 2 release evidence requirements.

## Non-goals

- No changes to GitHub rulesets or branch protection.
- No privileged token creation or secret configuration.
- No Render worker provisioning, billing changes, production deploy, database
  DDL, live backup, external provider calls, or capability activation.

## Acceptance

- Redacted bypass actors are visible as an explicit unverified status.
- Explicitly configured bypass actors still fail the audit.
- Existing audit tests remain green.
- CI is green on the final PR head.
- An independent maintainer reviews the final head before merge.
