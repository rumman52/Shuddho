# Day 2 — private, dated Founder + C authorization receipt

Source: original `02_Rukh_AI_Private_Staging.docx`, Part 02 pages 1 and 4, D02.T05 and D02.G05; Day 2 operator contract.

The final `staging_day2_acceptance.py` checks release/task/recovery/restore **technical consistency**. It now also requires an *operator-recorded* authorization receipt. This file is **not** the Founder or C issuing permission. Only an independently sourced, dated decision can authorize live staging resources, migrations, credentials, private restore or paid provider activity. If that decision does not exist, leave the record absent and the hosted gate BLOCKED.

## Protected file and minimal schema

Place a JSON object at `/secure/day2/founder-c-authorization.json` with file mode `0600`, not a symlink. Create it only after verifying separate original Founder and C change/approval records. Use a secure directory outside Git, CI logs, connected dashboards and shared chat. The CLI refuses world/group-readable receipts and duplicate JSON keys. Never include JWTs, passwords, signed object URLs, model responses, private document data, personal names or plaintext account IDs.

**Illustrative schema only. All angle-bracket values below are unverified placeholders and cannot pass validation until replaced by true evidence. Never copy the template to fabricate approval.**

```json
{
  "schema_version": 1,
  "status": "operator_recorded",
  "environment": "staging",
  "release_id": "<exact frozen release ID>",
  "source_revision": "<reviewed immutable 40-char commit SHA>",
  "rollout_manifest_sha256": "<SHA-256 of frozen rollout>",
  "provider_policy_sha256": "<SHA-256 of approved provider policy>",
  "build_reference": "<frozen immutable API+worker build reference>",
  "deployment_reference": "<approved deployment/change reference>",
  "hosting": {
    "provider": "<approved provider>",
    "workspace_reference": "<approved staging workspace>",
    "api_service_reference": "<approved staging API service ID>",
    "worker_service_reference": "<staging worker service name at creation, independently verified deployed ID afterwards>",
    "worker_region": "<approved Render region>",
    "worker_plan": "<approved Render paid plan SKU>"
  },
  "budget": {
    "currency": "<ISO 4217 uppercase code>",
    "max_spend_minor_units": 1,
    "maximum_duration_minutes": 1,
    "max_provider_attempts": 1
  },
  "isolated_restore": {
    "database_fingerprint": "<exact isolated target fingerprint SHA-256>",
    "storage_fingerprint": "<exact isolated bucket fingerprint SHA-256>",
    "api_origin_sha256": "<SHA-256 of approved isolated API HTTPS origin>"
  },
  "rollback": {
    "owner_reference": "<documented on-call rollback owner>",
    "procedure_reference": "<tested rollback/change procedure>"
  },
  "approvals": {
    "founder": {
      "decision": "approved",
      "approved_at": "<dated original Founder decision ISO-8601 with timezone>",
      "reference": "<protected original Founder approval ticket>"
    },
    "operator_c": {
      "decision": "approved",
      "approved_at": "<dated original operator C decision ISO-8601 with timezone>",
      "reference": "<separate protected operator C change ticket>"
    }
  },
  "valid_from": "<approved window start with timezone>",
  "valid_until": "<approved window end with timezone>"
}
```

`max_spend_minor_units` is a **ceiling**, in the currency's standard minor units (for example, USD cents); it is not a spent amount or provider billing proof. `maximum_duration_minutes` must bound `valid_until - valid_from`, and the two dated approvals must precede the window. The window must cover the **original 0070 preseed attestation**, release preparation and the final isolated backup/restore verification. The worker and API service references must be distinct, and `hosting.worker_region` and `hosting.worker_plan` must be included in the same dated decision. The preprovision guard binds the prospective name; after the worker exists, D must independently inspect its actual service ID, region and paid plan. Restore database/storage fingerprints and restored HTTPS API origin hash must match the actual verified archive receipt.

`max_provider_attempts` is compared with **the primary owner-A PDF task only**. It is not authorization to spend money on a separate owner-B task-output control, cloud hosts, model retries outside that task, or object storage. The operator and reviewer must inspect actual invoices, API provider policies and service deployments separately.

## Operator invocation

After authorization, original archive and both isolated restores **actually exist**, and the task and active worker restart have been observed:

```bash
uv run --extra coworker python scripts/staging_day2_acceptance.py \
  --freeze /secure/day2/release-frozen.json \
  --execution /secure/day2/document-execution.json \
  --recovery /secure/day2/temporal-recovery.json \
  --restored /secure/day2/restore-evidence.json \
  --authorization /secure/day2/founder-c-authorization.json \
  --expected-revision "<reviewed-40-character-SHA>" \
  --output /secure/day2/identity-consistency.json
```

The receipt is hashed into `authorization_evidence.receipt_sha256`. The final evidence includes `status=operator_recorded_requires_independent_review`, bounded nonsecret limits and `required_independent_verification=true`. Raw approval references are **not** copied into the final JSON. It still produces `status=evidence_consistent` **not hosted PASS**. Independent D must review the real original Founder/C decisions, cost/host/duration bounds, restore target provenance, actual worker restart, provider inference, protected account isolation, and rollback readiness, then record signed release gate acceptance. Never start Part 04 solely from this output.

## Source-only tests

`tests/test_staging_day2_acceptance.py` supplies a synthetic mock approval receipt in source tests, then checks that no receipt, wrong authorizations, later approvals, expired windows, excessive model attempts, changed resource digests, duplicate approval references, public file modes, symlinks and duplicate JSON keys are rejected. These tests do **not** establish human consent.


## Gate before PA-10 paid worker provisioning (D02.T05 / G05)

The final acceptance check above happens **too late** to protect against
unapproved paid compute. The manual
`.github/workflows/provision-pa10-staging-worker.yml` workflow now requires
an **independent pre-provision gate** before its first
`render services create/update`. It remains a fail-closed gate even if
someone types `PROVISION` into the workflow dispatch form.

After separate **actual dated Founder and C approvals** have been
independently inspected and protected by the environment owners, provision
the `pa10-staging` GitHub Actions environment secret:

- **Secret name:** `PA10_DAY2_FOUNDER_C_AUTHORIZATION_B64`. Its value is
  base64 of the actual private **schema-v1** JSON decision. Do not put that
  JSON in workflow-dispatch inputs, repository variables, public artifacts,
  CI logs, PostHog, Linear comments, or GitHub PRs.
- **Required scope:** `source_revision` equals the exact
  `GITHUB_SHA` being provisioned; `environment=staging`;
  `hosting.provider=Render`; `hosting.workspace_reference` equals
  `tea-d6ok4okhg0os73erkdv0`;
  `hosting.api_service_reference` equals the observed staging API
  `srv-dav98otg1s2s73cod4gg`; and
  `hosting.worker_service_reference` equals the **prospective** name
  `shuddho-worker-staging`; `hosting.worker_region=oregon` and
  `hosting.worker_plan=0.5c-512mb` must match the concrete
  `render services create/update` command arguments. A new paid worker
  does not yet have an ID; D independently checks its returned Render ID,
  region, SKU and billed pricing **after** the operation.
- **Budget:** `currency=USD`, positive
  `budget.max_spend_minor_units` in USD cents,
  `budget.maximum_duration_minutes` long enough for
  `valid_from`–`valid_until` but at most seven days, and a positive
  `max_provider_attempts` ceiling. The worker check does not measure
  actual spend or grant approval for model calls. Independently obtain the
  worker plan's current price, projected total including storage and
  provider charges, billing guards, and a stop/rollback action before use.
  The exact `worker_plan` and `worker_region` match ensures plan/region
  scope; it **does not calculate or enforce a dollar ceiling**, stop an
  instance on expiry, or prove the original approvals.
- **Decision timing:** distinct `approvals.founder` and
  `approvals.operator_c` approved-decision references, both dated no
  later than `valid_from`, and the **current actual UTC time** inside
  the approved `valid_from`–`valid_until` window. Expired, pending,
  mixed-source or self-declared `status=passed` records are rejected.
- **Recovery and rollback:** nonempty rollback owner and procedure refs,
  along with nonempty, distinct SHA-256 fingerprints for the approved
  isolated PostgreSQL, object-storage and restored HTTPS API targets.
  These references are placeholders for the independently reviewed actual
  resources; the source-only validator cannot prove that resources exist
  or are truly isolated. The existing final Day 2 restore verification
  binds those fingerprints to observed targets.

The protected job decodes the secret to a temporary local **0600** file,
checks it with `python3 -m scripts.staging_paid_worker_authorization`
against the exact dispatch commit and staging identity, emits only a redacted
receipt SHA-256 and bounds, then deletes the temporary file. **An absent
secret fails closed**; this patch deliberately does not install or invent
an approval.

Important: a plausible JSON file or its existence in GitHub Secrets is
*not proof of Founder or C consent*. Authorized environment owners and
independent reviewer D must inspect the original signed/ticketed decisions,
their scope and change window, actual budget/cost, worker deployment and
provider audit trail. The `PROVISION` input cannot replace those human
decisions. Production is outside this workflow.

For read-only inventory, continue using the nonprovisioning PA-10 preflight.
Do not turn the new guard off to make a hosted gate pass. When authorization
expires, do not provision or refresh a worker merely because source CI is green.
