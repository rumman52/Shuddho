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

This implementation is **not production-release-qualified yet**. The flag must remain outside reviewed production cohorts until a dedicated live LinkedIn staging/activation/release-ledger gate is implemented.

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

The Agent Runtime receives no LinkedIn publish tool, no connection discovery authority, and no proposal-promotion support for this action. A future Agent expansion would require a separate architecture and safety review.

## Next release task

Before production cohort enablement, add independent **LinkedIn social publishing release qualification**:

1. guarded live staging post against a dedicated test member;
2. wrong-hash approval denial and no-auto-publish proof;
3. deployed runtime-manifest verification;
4. exact kill switch `SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false`;
5. tamper-evident release-ledger attestation;
6. scale and post-rollback recovery consumption of that exact attestation.
