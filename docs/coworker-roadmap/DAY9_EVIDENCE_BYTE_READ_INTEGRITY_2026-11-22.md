# Day 9 — single-read integrity for independently held evidence (22 Nov 2026)

**Status: SOURCE_ONLY / NO-GO.** Implements a narrow Part 05 Day 9 source-integrity correction; this is not independent human D custody or an operated recovery receipt.

## Acceptance contract

- **Parent:** #737; **daily tracker:** #735 (D09.T03/T04/T09); **external dependency:** #665.
- **Base:** `main` at `4b055bcaab83151cca1478ab52ee121f5b2f74f7`; **review branch:** `fix/day9-evidence-verified-byte-reads-20261122`; **PR:** #876 (draft).
- **Defect:** `scripts/ruke_pilot_eval.py` previously checked a pathname with `is_file`/`stat`, hashed `read_bytes()`, and then parsed a *separate* `read_text()`. `external_heldout` repeated this across `sha256` and `read_jsonl`. A changed pathname could substitute input after the claimed hash/mode validation. The reported corpus SHA would no longer authenticate the bytes evaluated.
- **Scope:** `_read_evidence_bytes` uses one `O_NOFOLLOW | O_NONBLOCK` descriptor, verifies a regular inode with `fstat`, reads at most `MAX_BYTES + 1`, and rejects an oversized result if the file grows during reading. JSON and JSONL consume that exact buffer; the external holdout checks its read-only inode mode, pinned SHA-256, and its 40-case structure using the same bytes. Manifest, evidence, and candidate-output report hashes now use the **same buffer parsed by the release operator** (`_read_json_and_sha256`, `_read_jsonl_and_sha256`); the D-only blinding key is read and mode-checked from one descriptor as well. `sha256` uses the same bounded reader.
- **Non-goals:** No new storage authority, human-signature proof, real corpus contents, answer key, provider call, schema migration, runtime flag, deployment, or admission action.

## Reproduction and verification

Three adversarial tests were committed first at `e230ca0d3fd8cbeed708288155db6735f84cfd5b`. They independently model a replacement after the first hash read (JSON and JSONL) and a holdout where the second parse would return different source-hash bytes. Test fixtures are synthetic; the holdout remains outside the checkout and permissioned read-only for the file-mode check. Two additional digest-binding and one private-key regression were added after finding remaining double-open sites. These synthetic tests are **not** an operated 40-case first-run or human-reviewed result.

Run on the exact final PR SHA:

```bash
uv run --locked --extra coworker pytest -q tests/test_ruke_pilot_eval.py tests/test_day10_release_decision.py tests/test_cohort_release_gate.py tests/test_staging_release_freeze.py
uv run --locked --extra coworker python -m scripts.ruke_pilot_eval validate-registry
uv run --locked --extra coworker python -m scripts.ruke_pilot_eval preflight
uv run --locked --extra coworker python -m scripts.release_contract_check
```

Then require final-head GitHub Actions jobs, protected-branch ruleset enforcement and independent review; results must be read back from GitHub, not assumed from this document. Test-only CI may be cancelled by subsequent pushes; a cancelled run must not be reported as observed RED.

## Unchanged release blockers

1. **Human D:** replace exposed candidate cases; freeze the answers and rubric outside the repo; prove D allowed/developer denied before run; retain private access logs and all 40 immutable first attempts with 80 blind score records, independent security results and adjudication.
2. **Owner C and D:** run and independently authenticate 20 distinct PostgreSQL/Temporal/private-storage recovery receipts bound to one frozen rollout; verify exact API/worker/schema/model identity, 43 boolean flags and source checks.
3. **Founder and Owner C:** approve spending, scope and rollback independently, then operate the canonical Day 10 decision and a separately authorized 5–10-user canary. No approval or actual admission is inferred.

**Resume:** read PR #876 exact-head checks and review; after independent merge, D/C run the documented protected evaluator with new immutable paths. Never reuse the developer-visible holdout, alter first-run receipts or promote Day 9 / Day 10 exit status without authenticated operated evidence.
