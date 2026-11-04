# Rukh AI staging qualification — 4 November 2026

<badge>NOT QUALIFIED</badge>

No Render service or database was queried or changed during this task. Workspace discovery returned one workspace, `Rumman` (ID `tea-d6ok4okhg0os73erkdv0`), but the workspace must be explicitly confirmed by the user before service-level inspection.

Required before staging qualification:
1. Confirm the Render workspace and identify the intended staging API, worker and database.
2. Verify API/worker source revision parity and health checks.
3. Confirm database identity, expiry, backup/export and a tested restore path before migrations.
4. Verify staging is isolated from production data and secrets.
5. Run authentication, conversation, assistant-reply, Agent dispatch, approval, cancellation and artifact flows.
6. Capture browser evidence at 1440×900, 1280×800, 1024×768, 768×1024 and 390×844.
7. Verify PostHog ingestion and privacy-safe event properties.
8. Record exact service IDs, deployed SHAs, test output and rollback reference.

No migration, restore, deploy, paid provisioning or environment change was performed.
