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
