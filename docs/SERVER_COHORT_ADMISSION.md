# Server-Enforced Coworker Cohort Admission

The first controlled production cohort must be enforced by the backend, not only by frontend visibility or an operator-maintained user list.

## Configuration

The backend supports:

```bash
SHUDDHO_COWORKER_COHORT_ENFORCED=true
SHUDDHO_COWORKER_COHORT_ACCOUNT_IDS=<comma-separated 64-char Coworker account IDs>
SHUDDHO_COWORKER_COHORT_MAX_USERS=25
```

When enforcement is enabled:

- the allowlist must not be empty;
- every account ID must be a lowercase 64-character SHA-256 identifier produced by Shuddho's managed-identity account mapping;
- configured members must not exceed the maximum;
- a non-member receives HTTP 403 with `cohort_not_enabled`;
- the admission check happens before `ensure_account`, so a fresh denied identity does not get a Coworker account/workspace created.

The frontend flag is not a security boundary.

## Building the approved cohort

Before switching enforcement on, use authenticated staging/production enrollment tooling to collect the Coworker account IDs for explicitly approved users.

Do not place raw access tokens, email addresses, OAuth secrets or user documents in the environment variable. The allowlist contains only opaque Coworker account IDs.

## Live admission exercise

Use:
- one invited staging identity whose account ID is in the allowlist;
- one **fresh** staging identity whose account ID is not in the allowlist and has never provisioned a Coworker workspace.

Set:

```bash
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com
SHUDDHO_STAGING_TOKEN_A=<invited staging token>
SHUDDHO_STAGING_TOKEN_DENIED=<fresh non-member staging token>
```

Run:

```bash
uv run --extra coworker python scripts/staging_cohort_admission.py \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.cohort.json
```

A pass requires:

- cohort enforcement is enabled;
- invited account is in the configured allowlist;
- denied account is not in the allowlist;
- configured allowlist size is within the backend maximum;
- denied account does not exist in the Coworker account table before the API call;
- invited `GET /api/v1/me` returns 200;
- denied `GET /api/v1/me` returns 403 `cohort_not_enabled`;
- denied account still does not exist in the Coworker account table after the request.

Only then is `cohort_admission` staging evidence promoted to `passed`.

## Rollback

To stop all new Coworker access, use the global kill switch:

```bash
SHUDDHO_COWORKER_ENABLED=false
```

To remove one cohort member without globally disabling Coworker, remove that account ID from `SHUDDHO_COWORKER_COHORT_ACCOUNT_IDS` and redeploy current API instances.

Removing an account from the cohort blocks future API access; it does not erase the account's existing data. Use the retention/erasure operation separately when deletion is intended.
