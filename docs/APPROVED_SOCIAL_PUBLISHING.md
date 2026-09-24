# Approved LinkedIn Social Publishing v1

## Purpose

This Wave D increment lets a signed-in Shuddho user publish one **personal LinkedIn text post** only after reviewing and explicitly approving an immutable consequential-action preview.

Social drafts remain ordinary non-executable coworker output. Draft generation never grants publishing authority.

## Disabled by default

```text
SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false
```

Enabling the flag also requires the existing global actions boundary plus LinkedIn OAuth configuration:

```text
SHUDDHO_ACTIONS_ENABLED=true
SHUDDHO_LINKEDIN_CLIENT_ID=...
SHUDDHO_LINKEDIN_CLIENT_SECRET=...
SHUDDHO_LINKEDIN_REDIRECT_URI=https://<frontend>/oauth/linkedin/callback
SHUDDHO_LINKEDIN_API_VERSION=202609
```

This implementation is **release-qualified for a reviewed controlled cohort**, while remaining disabled by default. Production enablement requires the guarded live LinkedIn evidence, exact runtime activation proof, schema-v14 release-ledger attestation, and schema-v9 scale/recovery consumption described below.

## v1 authority

The registered action is:

```text
social_publish_linkedin
```

It can use only a connected LinkedIn personal member with:

- `r_liteprofile` to bind the app-scoped member identity;
- `w_member_social` to publish on behalf of that member.

The immutable approval scope binds:

- the exact LinkedIn connection;
- the exact authenticated Person URN;
- the exact UTF-8 post text;
- public visibility;
- immediate execution after approval;
- no media;
- no scheduling;
- no social-read authority;
- no Agent authority.

A changed author, text, policy, connection, or expiry invalidates approval.

## Explicitly out of scope

v1 does **not** support:

- organization/company page publishing;
- images, video, documents, carousels, polls, or link-preview configuration;
- private/targeted visibility;
- scheduled publishing;
- reading feeds or posts;
- comments, reactions, likes, reshares, or engagement analytics;
- editing or deleting published posts;
- arbitrary member IDs;
- Agent-selected or Agent-approved publishing;
- background mailbox/social polling;
- silent credential refresh assumptions.

## Credential model

LinkedIn access credentials are encrypted using the existing connector vault. The ordinary Share-on-LinkedIn flow does not assume programmatic refresh-token entitlement. The stored access token carries an expiry and execution fails closed with a reconnect requirement when it is expired or revoked.

Google and Microsoft retain their existing encrypted refresh-token behavior. The credential repository now stores a provider-neutral encrypted credential object so connector-specific secrets do not leak into the action model or APIs.

## Execution and uncertain outcomes

The executor revalidates the connected LinkedIn member immediately before mutation. It submits only the approved personal text post to the versioned LinkedIn Posts API.

A confirmed success requires:

- HTTP 201;
- a valid `x-restli-id` post URN;
- the same approval-bound personal author.

If the response is lost after mutation may have occurred, Shuddho records the action as uncertain and **does not blindly repeat the post**. v1 deliberately does not acquire social-read scope merely to reconcile an uncertain write.

## Draft-to-publish UX

The existing social-writing service remains draft-only. For LinkedIn drafts, the user may choose **Prepare this LinkedIn post for publishing**. That copies the text into the Actions workspace. Nothing is published at that point.

The user must still:

1. connect LinkedIn;
2. review the exact action preview;
3. confirm the personal member, exact text, public visibility and immediate timing;
4. explicitly approve the action.

## Agent boundary

The Agent Runtime receives no LinkedIn publish tool and no connection-discovery or publishing authority. A separate disabled-by-default [inert LinkedIn proposal extension](AGENT_LINKEDIN_PROPOSALS.md) may let the planner suggest exact post text, but the user must still choose the owned LinkedIn connection, promote the exact proposal into this ordinary immutable preview, and approve it separately. That proposal extension is not production-release-qualified by this document and does not widen this action's execution authority.

## Production release qualification

The release chain is now:

1. `scripts/staging_live_social_publishing.py` runs only behind `SHUDDHO_STAGING_ALLOW_LIVE_SOCIAL_PUBLISHING=true` and uses a dedicated staging member plus synthetic text;
2. the live gate proves no auto-publish, wrong-hash denial, immutable member/text/policy binding, one execution audit chain, and a confirmed LinkedIn post receipt;
3. `scripts/action_social_publishing_activation.py` verifies the exact reviewed rollout, deployed source revision, clean operator status, cohort enforcement, LinkedIn provider, runtime manifest and exact feature kill switch;
4. `scripts/cohort_release_ledger.py append-action-social-publishing` records schema-v14 `action_social_publishing_verified` evidence;
5. bounded expansion requires the exact activation SHA and schema-v14 attestation and emits schema-v9 scale evidence while the capability is enabled;
6. post-global-rollback recovery requires a **fresh** activation and schema-v14 event after the rollback-completion event, then emits schema-v9 recovery evidence.

The emergency feature rollback is exactly:

```text
SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false
```

Disabling the feature blocks new social connections/previews/execution through the existing action boundary. It cannot recall a provider request that was already issued.
