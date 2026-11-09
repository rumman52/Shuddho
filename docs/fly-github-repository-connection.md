# Fly GitHub repository connection

## Scope

This integration connects a GitHub App to a Fly project and provides bounded, read-only repository browsing. Selected files are copied into owner-private Rukh Files snapshots and attached to an Agent task as immutable source context.

This phase does **not** clone a repository, write branches, create commits or pull requests, execute repository code, or run multi-language tests. The GitHub App must remain read-only until the later patch-approval and isolated-execution phase is implemented and reviewed.

## GitHub App registration

Create a GitHub App and configure:

- **Setup URL:** `https://YOUR-FRONTEND-DOMAIN/fly`
- **User authorization callback URL:** the exact same clean HTTPS `/fly` URL, with no query string.
- **Repository permissions:** Metadata — Read-only; Contents — Read-only.
- **User authorization:** enable expiring user access tokens. Fly requests the `offline_access` scope and uses PKCE S256.
- **Webhook:** not required for this read-only connection phase.

Do not grant Contents write, Pull requests write, Actions write, Administration, or other write permissions for this phase.

## Backend configuration

Set these values in protected runtime secrets:

```dotenv
SHUDDHO_FLY_GITHUB_ENABLED=true
SHUDDHO_GITHUB_APP_ID=...
SHUDDHO_GITHUB_APP_SLUG=...
SHUDDHO_GITHUB_APP_CLIENT_ID=...
SHUDDHO_GITHUB_APP_CLIENT_SECRET=...
SHUDDHO_GITHUB_APP_REDIRECT_URI=https://YOUR-FRONTEND-DOMAIN/fly
SHUDDHO_GITHUB_API_VERSION=2026-03-10
SHUDDHO_GITHUB_TIMEOUT_SECONDS=15
SHUDDHO_GITHUB_MAX_FILE_BYTES=262144
SHUDDHO_GITHUB_MAX_TREE_FILES=500
SHUDDHO_CONNECTOR_ENCRYPTION_KEY=...
```

Keep the existing connector encryption key stable. Do not rotate it without first using the repository's credential re-encryption procedure. Never put GitHub credentials in frontend environment variables, source control, chat messages, or browser storage.

Apply database migration `0066` before enabling the feature. The feature flag defaults to false and startup validation fails closed if the required settings are missing or invalid.

## Authorization sequence

1. Fly creates a one-use, owner/project-scoped OAuth state and PKCE verifier.
2. The user authorizes the GitHub App through GitHub's user authorization flow.
3. The backend exchanges the code and temporarily encrypts the expiring user/refresh token bundle.
4. The user installs or selects an installation through the App setup URL.
5. The backend treats `installation_id` as untrusted input and verifies it against the exact authenticated GitHub user's `GET /user/installations` response and configured App ID.
6. The backend lists repositories through `GET /user/installations/{installation_id}/repositories` using the user's token.
7. Fly binds one repository to one owner-scoped project.
8. Repository tree and file reads use the user's token, preserving the intersection of user access and App permissions.

Access and refresh tokens are encrypted with TokenVault and never returned to the browser. Access-token refresh is serialized under the installation row lock; rotated tokens replace the prior encrypted bundle. Rukh supports one GitHub user authorization per Rukh account. Revoking that authorization calls GitHub's `DELETE /applications/{client_id}/grant` endpoint with Basic authentication. This revokes the user's GitHub App authorization, including its expiring access/refresh token grants, then clears every local installation token and deactivates all project bindings for that GitHub user. If GitHub cannot confirm revocation, local deletion is rolled back so the user can retry. The GitHub App may remain installed in GitHub settings; uninstalling the App is a separate GitHub-side action. Account erasure revokes each distinct GitHub user authorization once before deleting local account records; if provider revocation cannot be confirmed, the database erasure transaction aborts and the encrypted token remains available for a retry.

## Repository context limits

- Tree response: at most 500 source files.
- Individual file: at most 256 KiB.
- Fly import: at most 8 selected files per action and 12 local workspace files total.
- UTF-8 text only; binary and NUL-containing files are rejected.
- Paths are relative POSIX paths; traversal and backslashes are rejected.
- Environment/credential files, private keys, generated directories, dependency trees and build output are excluded.
- Each file response includes repository, branch, commit SHA, upstream Git blob SHA and content SHA-256. Fly verifies byte length and SHA-256 before import.
- Before an Agent task is dispatched, imported repository files are stored as owner-private Rukh Files snapshots and their exact version IDs are attached to the conversation message.

## Qualification still required

The following remain outside this connection PR:

- Multi-file model-generated patch proposals and schema validation.
- Immutable exact-diff review hashes and approval/rejection.
- Write-scoped user token minting, branch creation, commit and pull-request creation after explicit approval.
- Rebase/conflict detection and stale-base rejection.
- Isolated repository execution for supported runtimes, with network egress denied by default.
- Test logs, repair proposals, execution cleanup and crash recovery.
- Live GitHub App staging credentials and an independent reviewer.

Do not describe repository-level coding as complete until those controls and the relevant live qualification evidence exist.
