# Owned Action Recipient Directory

This Wave D increment adds a bounded, user-owned recipient shortcut directory for approved email and calendar actions.

## Safety boundary

A saved recipient is **not** a new consequential action and is never executable authority.

- Users explicitly create each name/email pair in Shuddho.
- Shuddho requests no Google Contacts, Microsoft Contacts, mailbox-read, directory-read, or people-search permission.
- The Agent runtime, planner, memory and action-proposal paths cannot read, resolve or select saved recipients.
- There is no fuzzy name matching and no server-side conversion from model text to a destination.
- Selecting an entry in the UI copies its exact validated email address into the normal action form.
- The existing action payload validation, immutable preview, approval-scope hash and provider execution contract remain unchanged.
- Updating or deleting a saved recipient cannot mutate an already prepared action because the prepared preview stores the exact email string.

This is intentionally different from provider contact import or organization-directory search, both of which require a separate permission/privacy design.

## Data model and limits

Migration `0014` adds `cw_action_recipients`.

Each row is owner-scoped and contains only an opaque UUID, display name, validated bare email address, normalized name/email uniqueness keys, and timestamps. The default limit is 100 recipients per account and `SHUDDHO_ACTION_RECIPIENTS_MAX` is capped at 500.

Names are Unicode NFKC-normalized, whitespace-collapsed and capped at 80 characters. Email validation reuses the existing action-address validator. Mutations serialize on the account row, preventing concurrent limit/uniqueness races in PostgreSQL. Audit records contain only the recipient resource ID and operation name; they do not duplicate the name or email.

## API and UI

Authenticated owner-scoped routes:

- `GET /api/v1/action-recipients`
- `POST /api/v1/action-recipients`
- `PUT /api/v1/action-recipients/{id}`
- `DELETE /api/v1/action-recipients/{id}`

Create/update require `SHUDDHO_ACTION_RECIPIENTS_ENABLED=true`. Listing and deletion remain available after rollback so stored personal data is not stranded behind a feature flag.

The action workspace can add a saved address to email **To** or calendar **Guests**. The exact address is visibly present before preview creation and again in the approval preview.

## Privacy and lifecycle

Account erasure deletes recipient rows before deleting the account. Recipient data is never sent to a model or to an external provider merely because it is saved; a provider sees an address only when the user places it into an explicitly approved email/event action.

## Rollout

Keep these settings at their defaults until migration `0014`, authenticated CRUD, owner isolation, erasure, and UI smoke tests pass in staging:

```text
SHUDDHO_ACTION_RECIPIENTS_ENABLED=false
SHUDDHO_ACTION_RECIPIENTS_MAX=100
```

This increment does not widen the consequential-action registry and does not add provider OAuth scopes. The existing controlled `actions` rollout remains the outer execution gate.


## Production qualification and attestation

Implementation alone is not permission to enable this feature. Production activation follows the same fail-closed evidence chain used by other consequential-action capabilities, while retaining the recipient directory's narrower non-executable authority boundary.

1. Run `scripts/staging_live_action_recipients.py` with two dedicated staging identities and `SHUDDHO_STAGING_ALLOW_LIVE_ACTION_RECIPIENTS=true`. The probe creates a synthetic recipient for account A, verifies exact round-trip values, proves account B cannot read/update/delete it, updates it, deletes it, and verifies cleanup for both accounts.
2. Review a production rollout manifest declaring `action_recipients=true` and the exact rollback switch `SHUDDHO_ACTION_RECIPIENTS_ENABLED=false`.
3. Deploy migration 0014 and the reviewed revision with the recipient flag enabled only for the controlled cohort.
4. Run `scripts/action_recipients_activation.py`. It binds the exact staging evidence, reviewed rollout, deployment record, source revision, fresh operator health, runtime manifest, capability flags and cohort ceiling into one activation artifact.
5. Append that artifact to the HMAC-protected release ledger as schema-v11 `action_recipients_verified`.
6. Bounded cohort expansion and post-rollback recovery must reference that exact ledger-attested activation. Recipient-enabled scale/recovery evidence uses schema v6.

Older attachment/reminder/proposal activation validators normalize `action_recipients=false` when reviewing pre-recipient rollout manifests. This prevents the new runtime-manifest key from breaking prior feature attestations while still requiring an exact value whenever a rollout explicitly enables recipients.

### Operator commands

Controlled staging:

```bash
SHUDDHO_STAGING_ALLOW_LIVE_ACTION_RECIPIENTS=true \
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com \
SHUDDHO_STAGING_TOKEN_A=<short-lived-account-a-token> \
SHUDDHO_STAGING_TOKEN_B=<short-lived-account-b-token> \
uv run --extra coworker python scripts/staging_live_action_recipients.py \
  --base-evidence staging-evidence.json \
  --output staging-evidence-with-recipients.json
```

Production activation:

```bash
SHUDDHO_PRODUCTION_VERIFICATION_TOKEN=<short-lived-cohort-token> \
uv run --extra coworker python scripts/action_recipients_activation.py \
  --staging-evidence staging-evidence-with-recipients.json \
  --rollout docs/cohort-rollout.production.json \
  --deployment-change action-recipients-deployment.json \
  --operator-status operator-status.json \
  --api-base-url https://api.example.com \
  --output action-recipients-activation.json
```

Ledger attestation:

```bash
uv run --extra coworker python scripts/cohort_release_ledger.py append-action-recipients \
  --ledger release-ledger.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference <oncall-or-change-actor> \
  --change-reference <approved-change-reference> \
  --current-stage <current-cohort-stage> \
  --staging-evidence staging-evidence-with-recipients.json \
  --rollout docs/cohort-rollout.production.json \
  --deployment-change action-recipients-deployment.json \
  --operator-status operator-status.json \
  --action-recipients-activation action-recipients-activation.json
```

The staging script never writes access tokens into evidence. Use dedicated non-customer staging identities and synthetic `example.test` addresses only.
