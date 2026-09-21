# Agent Evaluation and Production Staging Gates

This increment converts Coworker release readiness from an informal checklist into repeatable evidence.

## What CI proves

CI runs the existing Coworker integration suite plus `scripts/agent_eval.py` in offline mode.

The offline evaluation:
- uses only checked-in, non-sensitive fixtures;
- exercises the server-owned bounded routing contract;
- verifies the exact expected tool sequence;
- rejects consequential tools such as `email.send` and `calendar.create` from ordinary planning cases;
- includes English plus mixed-language cases so multilingual regressions are visible without claiming broad language quality coverage.

CI is application-contract evidence only. It does not prove real DeepSeek output quality, production identity, storage, Temporal, backups, or provider integrations.

## Live planner evaluation

Run only in controlled staging with a backend-only `DEEPSEEK_API_KEY`:

```bash
uv run --extra coworker python scripts/agent_eval.py --live --min-pass-rate 1.0 --output /tmp/agent-eval.json
```

Do not run paid live evaluation in CI. Do not add user prompts, user files, secrets, hidden reasoning, or production data to the fixture set or generated artifacts.

The initial release threshold is 100% on this deliberately small contract set. Expanding the fixture set is preferred over lowering the threshold when new tools or languages are introduced.

## Production staging gate

Copy `docs/staging-evidence.template.json` outside the repository, replace each pending item with:

```json
{"status":"passed","evidence":"ticket/run/dashboard reference"}
```

Then run:

```bash
uv run python scripts/staging_gate.py --evidence /secure/path/staging-evidence.json --require-research --require-actions
```

The command exits non-zero and reports `NO-GO` until every required gate passes.

Required base evidence:
- repository CI including Coworker/Temporal recovery;
- managed identity and owner-isolation validation;
- TLS PostgreSQL and migrations;
- private object storage and owner-scoped downloads;
- production Temporal plus worker restart/replay validation;
- live DeepSeek call and live planner evaluation;
- backup/restore exercise;
- retention/deletion exercise;
- two-branch parallel restart with no duplicate tasks/artifacts;
- fan-in dependency enforcement;
- feature-flag rollback from v2 to v1.

Research and approved-action evidence is required only when those capabilities are intended to be enabled.

## Minimum conditions to enable Coworker

Do not enable `SHUDDHO_COWORKER_ENABLED` or `SHUDDHO_AGENT_RUNTIME_ENABLED` for general production traffic unless the staging gate returns `GO`.

For the first production cohort:
- keep intelligent planning, memory, handoffs, dependency graph, parallel execution, research, and actions independently flaggable;
- enable only capabilities with completed evidence;
- begin with a small approved cohort;
- retain an immediate flag rollback path;
- monitor queue age, task success, provider errors, retries, latency, token use, storage growth, and action outcomes.

A green gate authorizes a controlled rollout, not unrestricted autonomy or a global scale claim.
