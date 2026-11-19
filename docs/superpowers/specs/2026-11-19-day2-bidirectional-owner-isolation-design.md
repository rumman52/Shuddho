# Day 2 Bidirectional Owner-Isolation Design

## Intent

The Day 2 operator must prove that two distinct synthetic owners can access their own private documents and generated artifacts, while each owner is denied access to the other owner's resources. The current operator exercises only B-to-A denial and emits a single `owner_isolation: "passed"` value, which is too weak for tracker D02.T08.

## Goals

- Verify distinct owner and workspace identities without recording raw account identifiers.
- Create one synthetic TXT control document as owner B and upload owner A's selected private PDF through the normal private upload path.
- Verify positive owner reads and cross-owner document read/write denial in both directions.
- Verify each accepted JWT's issuer, audience, expiry, subject and authenticated API subject-to-account binding without retaining raw claims or tokens.
- Verify owner-scoped document listings exclude the other owner's document.
- Verify positive artifact content/download access and cross-owner content/download denial in both directions.
- Emit structured, non-secret directional evidence and require the acceptance gate to validate it.
- Keep owner A's PDF report as the only provider-backed task in this operator run.

## Non-goals

- Provision or restart a Render worker, create Auth users, create credentials, call a model outside the one owner-A task, migrate staging, or perform backup/restore.
- Create a second provider-backed task solely to manufacture an owner-B artifact.
- Treat source tests, CI, or evidence consistency as hosted staging acceptance.

## Approaches considered

1. **Create a second owner-B model task.** This would produce a B-owned artifact through the ordinary task path, but adds a second provider invocation and conflicts with the one-task objective and current no-spend authorization boundary.
2. **Keep the existing A-to-B-only checks.** This is the smallest patch, but it does not meet the explicit two-direction requirement in D02.T08.
3. **Require an existing synthetic B-owned control artifact and test both owners against both artifacts; create a B-owned TXT document during the run.** This keeps the single provider-backed A task, adds no model call, and fails before private writes if the B artifact is absent or not actually owned by B.

**Chosen approach: 3.** The B-owned control artifact must be prepared independently through an already-authorized synthetic workflow and supplied by ID. The operator verifies B's positive access and A's denial; it never assumes an artifact exists and never manufactures one.

## Design

- Add required CLI input `--owner-b-artifact-id`; normalize it as a UUID.
- Before creating either document or task, read both owners' artifact catalogs. Require the supplied artifact to appear in B's catalog and not A's. Verify B can read its content and obtain a valid private signed download; verify A receives 404 for both routes. Check content size and SHA-256 against the API metadata.
- Create the B-owned synthetic TXT document and the A-owned selected PDF document. Verify each owner's positive content read, the opposite owner's denied content read and upload, and each owner's listing excludes the foreign document.
- After the A report task completes, verify the A artifact is present only in A's catalog, is retrievable by A with matching size/SHA-256, and returns 404 to B for content and download. Verify B's catalog does not contain A's artifact.
- Replace the string owner-isolation result with a structured receipt containing owner A/B document IDs, artifact IDs, positive access statuses, foreign 404 statuses, and foreign-list exclusion statuses. Do not include tokens, source bytes, signed URLs, or account IDs.
- Make `staging_day2_acceptance.py` validate both owner records, all required statuses, and distinct resource IDs. Recovery and restore must continue to carry the exact nested receipt unchanged.
- Update the Day 2 contract to state the B-owned artifact precondition and the fail-closed two-direction behavior.

## Operational boundary

The implementation is source-only. Current staging readbacks show schema 0070, zero Auth users and storage objects, no persistent worker, and no approved restore target. Do not run the hosted operator, provision resources, migrate, seed, or call the model until the existing owner-approval and release gates are satisfied.
