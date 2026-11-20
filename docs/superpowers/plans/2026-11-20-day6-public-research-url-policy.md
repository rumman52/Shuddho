# Day 6 public research URL identity hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. TDD and verification-before-completion are mandatory.

**Goal:** Stop the Day 6 research-provenance receipt validator from accepting private or link-local literal network destinations as purported independently verified public HTTPS sources.

**Architecture:** Only the external receipt consistency validator is changed; no browser/worker/research downloader code or hosted provider path is touched. Use the Python standard library `ipaddress` to classify IPv4/IPv6 address literals, normalizing DNS hostnames to reject localhost/local suffixes. Preserve legitimate public HTTPS DNS and public IP literals. The validator cannot authenticate retrieval, resolve DNS, or attest that platform receipts are real.

**Tech Stack:** Python 3 standard library, pytest, GitHub Actions.

**Spec:** The original operator-provided `03_Rukh_AI_Product_Workflows(1).docx`, Part 03 Days 3–6, particularly Day 6 D06.T02/D06.G01 and release evidence. It requires approved source title, URL/private reference, retrieval time, digest and independently verified support. This code change applies only to the existing public HTTPS URL receipt path; adding a private-version reference schema is out of scope.

## Global Constraints

- The source-level verifier returns `evidence_internally_consistent_not_live_attested` and must not become a hosted PASS verifier.
- No provider, model call, external sends, live owner accounts, staging deploys, migrations, paid resource provisioning, or governance bypass.
- Keep each independent correction a bounded PR from current main.
- Require all Days 3–6 mandatory receipt-contract tests with zero skips and inspect actual GitHub Actions run/commit.

## Review Focus

- Link-local IPv4 (`169.254.169.254`) and RFC1918 address outside the previous ad hoc list (`172.17.0.1`) must reject.
- IPv6 loopback, unique local and link-local literals must reject.
- `localhost.` and `service.local` must reject although the prior hostname string equality misses them.
- Genuine public HTTPS DNS `example.org` and public literal IPv4/IPv6 must remain valid.
- No DNS resolution or public-network retrieval is performed; the operator independently authenticates all receipt source reads.

---

### Task 1: RED — adversarial receipt tests

**Files:**
- Modify: `tests/test_staging_days3_6_acceptance.py`

**Interfaces:**
- Input: `evidence()[4]["cases"]` research source `citations[0]["url"]`.
- Expected: `gate.Days36EvidenceError` with current `public HTTPS` error label.

- [ ] Add a parametrized rejection test for the private IPv4, IPv6, local DNS and localhost-with-trailing-dot URL cases.
- [ ] Add a positive public IP literal and public DNS variant control.
- [ ] Commit test-only snapshot; run its exact-head GitHub Actions and observe **expected failure** from the new negative cases.

### Task 2: GREEN — minimal canonical hostname policy

**Files:**
- Modify: `scripts/staging_days3_6_acceptance.py`

- [ ] Import `ipaddress` and classify parsed `hostname` using `ipaddress.ip_address(host)`; reject `not is_global`.
- [ ] For non-IP DNS hostnames, reject `localhost` and DNS suffixes `.localhost`/`.local`, including a trailing dot; retain existing public-domain shape and HTTPS/no-credentials requirements.
- [ ] Preserve existing literal IPv4/IPv6 public-address behavior without DNS lookups.
- [ ] Re-run mandatory zero-skip contract test module and general Python CI suite on implementation SHA.

### Task 3: Review and delivery

- [ ] Inspect RED and GREEN test logs, head SHA, required jobs and governance failures.
- [ ] Open one bounded GitHub PR, independently review and do not merge through governance failures.
- [ ] Update Linear MD-7 with the PR, tested SHA and accurate non-hosted acceptance status.
