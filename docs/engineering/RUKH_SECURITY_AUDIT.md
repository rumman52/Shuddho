# Rukh AI security audit — bounded source and service review

## Verified
- Coworker frontend obtains a Supabase Auth session and provides the current user's access token to the Coworker API client.
- Conversation endpoints take an authenticated `Identity` and call owner-scoped service methods.
- Direct reply generation explicitly has no tools, live web access, file contents, account access or action permissions; Agent dispatch is a separate endpoint.
- No service-role key or private provider credential was added to browser code or this patch.
- Supabase `shuddho-staging` reports ACTIVE_HEALTHY; public schema has no tables; security and performance advisors returned no lints.

## Not verified
- Live cross-user API access, token expiry/refresh and deployed RLS behavior.
- Render Postgres ownership/permissions, backup/restore and worker access boundaries.
- Browser CSP, deployment secrets and Vercel environment separation.
- Formal penetration testing or independent human security review.

No security controls, RLS policies, environment variables, secrets, database schemas or production services were changed in this recovery.
