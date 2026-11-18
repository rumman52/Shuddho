"""Fail-closed consistency checks for *operated* Days 3–6 staging receipts.

This does not call a provider, deploy software, certify a reviewer, or turn a
synthetic fixture into hosted acceptance. Independently gather and verify the
platform receipts before anyone marks a roadmap acceptance row PASS.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit


class Days36EvidenceError(ValueError):
    pass


SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
WORKFLOWS = {"research", "report_email"}
LANGUAGES = {"bn", "en"}
NEGATIVES = {"foreign", "expired", "deleted", "stale", "wrong_version"}
BOUND = (
    "release_id", "source_revision", "runtime_manifest_sha256",
    "rollout_manifest_sha256", "api_deployment_id", "worker_deployment_id", "database_revision",
    "provider", "model_id", "owner_a_ref", "owner_b_ref",
)
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024


def need(ok: bool, message: str) -> None:
    if not ok:
        raise Days36EvidenceError(message)


def obj(value: object, label: str) -> dict:
    need(isinstance(value, dict), f"{label} must be an object")
    return value


def text(value: object, label: str) -> str:
    need(isinstance(value, str) and bool(value.strip()), f"{label} is missing")
    return value


def sha(value: object, label: str, pattern=SHA256) -> str:
    need(isinstance(value, str) and bool(pattern.fullmatch(value)), f"{label} is not a canonical digest")
    return value


def count(value: object, label: str, expected: int | None = None) -> int:
    need(type(value) is int and value >= 0, f"{label} must be a nonnegative integer")
    if expected is not None:
        need(value == expected, f"{label} must equal {expected}")
    return value


def when(value: object, label: str) -> datetime:
    text(value, label)
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Days36EvidenceError(f"{label} has an invalid timestamp") from None
    need(t.tzinfo is not None, f"{label} must include a timezone")
    t = t.astimezone(timezone.utc)
    need(t <= datetime.now(timezone.utc) + timedelta(minutes=5), f"{label} is from the future")
    return t


def referenced(value: object, label: str) -> str:
    return text(value, label)


def bound(release: dict, receipt: object, label: str, *, after: datetime) -> tuple[dict, datetime]:
    row = obj(receipt, label)
    need(row.get("status") == "passed" and row.get("mode") == "hosted",
         f"{label} has no operated hosted pass")
    for key in BOUND:
        need(row.get(key) == release.get(key), f"{label} does not match frozen {key}")
    referenced(row.get("evidence_ref"), f"{label}.evidence_ref")
    started = when(row.get("started_at"), f"{label}.started_at")
    checked = when(row.get("verified_at"), f"{label}.verified_at")
    need(after <= started <= checked, f"{label} predates frozen deployment or reverses time")
    return row, checked


def check_day3(release: dict, data: object, frozen: datetime) -> datetime:
    day, completed = bound(release, data, "day3", after=frozen)
    answers = day.get("answers")
    need(isinstance(answers, list) and len(answers) == 2, "day3 requires both language answers")
    seen, providers = set(), set()
    for i, item in enumerate(answers):
        answer = obj(item, f"day3.answers[{i}]")
        language = answer.get("language")
        need(language in LANGUAGES and language not in seen, "day3 requires distinct bn/en answers")
        seen.add(language)
        provider_id = referenced(answer.get("provider_request_id"), "day3.provider_request_id")
        need(provider_id not in providers, "day3 reuses a provider request")
        providers.add(provider_id)
        for field in ("answer_sha256", "selected_document_sha256"):
            sha(answer.get(field), f"day3.{field}")
        ids = answer.get("citation_ids")
        need(isinstance(ids, list) and bool(ids) and all(
            isinstance(x, str) and re.fullmatch(r"src-[1-5]", x) for x in ids
        ), "day3 requires bounded owner-verified citations")
        need(answer.get("factual_check") is True and answer.get("owner_b_denied") is True,
             "day3 lacks factual or owner isolation evidence")
        referenced(answer.get("answer_receipt_ref"), "day3.answer_receipt_ref")
    need(seen == LANGUAGES, "day3 missing language")
    rev = obj(day.get("revocation"), "day3.revocation")
    start = when(rev.get("provider_started_at"), "day3.revocation.provider_started_at")
    revoked = when(rev.get("revoked_at"), "day3.revocation.revoked_at")
    finish = when(rev.get("provider_finished_at"), "day3.revocation.provider_finished_at")
    need(frozen <= start < revoked < finish <= completed, "day3 revocation was not mid-inference")
    referenced(rev.get("provider_request_id"), "day3.revocation.provider_request_id")
    referenced(rev.get("revocation_receipt_ref"), "day3.revocation.revocation_receipt_ref")
    count(rev.get("visible_deltas_after_revoke"), "day3.revocation.visible_deltas_after_revoke", 0)
    count(rev.get("persisted_stale_answers"), "day3.revocation.persisted_stale_answers", 0)
    need(rev.get("source_revoked") is True and rev["provider_request_id"] not in providers,
         "day3 needs a distinct revoked provider request")
    for key in ("agent_runs_before", "agent_runs_after", "agent_outbox_before", "agent_outbox_after"):
        count(day.get(key), "day3." + key, 0)
    return completed


def check_day4(release: dict, data: object, frozen: datetime) -> datetime:
    day, completed = bound(release, data, "day4", after=frozen)
    need(day.get("brief_language") == "bn", "day4 has no Bangla reviewed brief")
    initial = sha(day.get("initial_digest"), "day4.initial_digest")
    edited = sha(day.get("edited_digest"), "day4.edited_digest")
    need(initial != edited and day.get("approved_digest") == edited
         and day.get("start_digest") == edited, "day4 Start did not use reapproved edit")
    edit_at = when(day.get("edited_at"), "day4.edited_at")
    approved_at = when(day.get("approved_at"), "day4.approved_at")
    start_at = when(day.get("start_at"), "day4.start_at")
    need(frozen <= edit_at < approved_at <= start_at <= completed, "day4 edit/approval/Start order invalid")
    run_id = referenced(day.get("agent_run_id"), "day4.agent_run_id")
    referenced(day.get("start_receipt_ref"), "day4.start_receipt_ref")
    need(day.get("owner_b_denied") is True, "day4 lacks independent owner-B denial")
    referenced(day.get("owner_b_denial_ref"), "day4.owner_b_denial_ref")
    count(day.get("agent_runs_before"), "day4.agent_runs_before")
    count(day.get("agent_runs_after"), "day4.agent_runs_after",
          day["agent_runs_before"] + 1)
    count(day.get("outbox_before"), "day4.outbox_before")
    count(day.get("outbox_after"), "day4.outbox_after", day["outbox_before"] + 1)
    replay = obj(day.get("retry"), "day4.retry")
    need(replay.get("same_run_id") == run_id and replay.get("http_status") in {200, 202},
         "day4 duplicate Start returned a new run")
    count(replay.get("additional_runs"), "day4.retry.additional_runs", 0)
    count(replay.get("additional_outbox"), "day4.retry.additional_outbox", 0)
    race = obj(day.get("start_edit_race"), "day4.start_edit_race")
    need(race.get("http_status") == 409, "day4 concurrent Start/edit did not conflict")
    raced = when(race.get("started_at"), "day4.start_edit_race.started_at")
    changed = when(race.get("edit_committed_at"), "day4.start_edit_race.edit_committed_at")
    responded = when(race.get("responded_at"), "day4.start_edit_race.responded_at")
    need(frozen <= raced < changed < responded <= completed,
         "day4 has no proven overlapping Start/edit race")
    count(race.get("additional_runs"), "day4.start_edit_race.additional_runs", 0)
    count(race.get("additional_outbox"), "day4.start_edit_race.additional_outbox", 0)
    for key in ("retry_receipt_ref", "race_receipt_ref"):
        referenced(day.get(key), "day4." + key)
    return completed


def check_day5(release: dict, data: object, frozen: datetime) -> datetime:
    day, completed = bound(release, data, "day5", after=frozen)
    arms = day.get("arms")
    need(isinstance(arms, list) and len(arms) == 3, "day5 needs none/v1/v2 model calls")
    keys, provider_ids, run_ids = set(), set(), set()
    facts, outputs = {}, {}
    for item in arms:
        arm = obj(item, "day5.arm")
        name = arm.get("name")
        need(name in {"none", "v1", "v2"} and name not in keys, "day5 has missing/duplicate arm")
        keys.add(name)
        for key in ("prompt_sha256", "source_sha256", "model_context_sha256", "output_sha256"):
            sha(arm.get(key), "day5.arm." + key)
        need(arm.get("provider") == release["provider"] and arm.get("model_id") == release["model_id"],
             "day5 model drifted")
        count(arm.get("budget_tokens"), "day5.arm.budget_tokens", release["budget_tokens"])
        p = referenced(arm.get("provider_request_id"), "day5.provider_request_id")
        r = referenced(arm.get("agent_run_id"), "day5.agent_run_id")
        referenced(arm.get("provider_receipt_ref"), "day5.provider_receipt_ref")
        need(p not in provider_ids and r not in run_ids, "day5 must run three independent model calls")
        provider_ids.add(p)
        run_ids.add(r)
        facts[name] = (arm.get("fact_id"), arm.get("fact_version"))
        outputs[name] = (arm["output_sha256"], text(arm.get("observed_claim"), "day5.observed_claim"), r)
    need(keys == {"none", "v1", "v2"}, "day5 is missing an arm")
    common = arms[0]
    for arm in arms[1:]:
        need(arm["prompt_sha256"] == common["prompt_sha256"]
             and arm["source_sha256"] == common["source_sha256"], "day5 source/prompt was not held constant")
    need(facts["none"] == (None, None), "day5 none arm imported a memory")
    for name in ("v1", "v2"):
        need(type(facts[name][1]) is int, "day5 pinned fact versions must be exact integers")
    context_hashes = {arm["model_context_sha256"] for arm in arms}
    need(len(context_hashes) == 3, "day5 did not compare three distinct model memory contexts")
    fact_id = text(facts["v1"][0], "day5.v1.fact_id")
    need(facts["v2"] == (fact_id, 2) and facts["v1"] == (fact_id, 1),
         "day5 did not compare selected fact v1 with corrected v2")
    need(outputs["v1"][0] != outputs["v2"][0] and outputs["v1"][1] != outputs["v2"][1],
         "day5 has no witnessed changed factual output")
    unselected = obj(day.get("unselected_memory"), "day5.unselected_memory")
    need(unselected.get("absent_from_all_model_inputs") is True
         and unselected.get("unselected_fact_id") != fact_id,
         "day5 has no same-category unselected-memory exclusion proof")
    referenced(unselected.get("unselected_fact_id"), "day5.unselected_fact_id")
    referenced(unselected.get("evidence_ref"), "day5.unselected.evidence_ref")
    exclusions = day.get("exclusions")
    need(isinstance(exclusions, list) and len(exclusions) == len(NEGATIVES),
         "day5 missing denial proofs")
    seen = set()
    for row in exclusions:
        e = obj(row, "day5.exclusion")
        kind = e.get("kind")
        need(kind in NEGATIVES and kind not in seen, "day5 exclusion missing/duplicate")
        seen.add(kind)
        need(e.get("http_status") in {403, 404, 409, 410, 422},
             f"day5 {kind} did not return an explicit denial")
        count(e.get("model_calls_after_denial"), "day5.model_calls_after_denial", 0)
        referenced(e.get("evidence_ref"), "day5.exclusion.evidence_ref")
    replay = obj(day.get("historical_replay"), "day5.historical_replay")
    need(replay.get("agent_run_id") == outputs["v1"][2]
         and replay.get("output_sha256") == outputs["v1"][0],
         "day5 historical v1 replay changed persisted run/output")
    count(replay.get("new_outbox_effects"), "day5.historical_replay.new_outbox_effects", 0)
    referenced(replay.get("evidence_ref"), "day5.historical_replay.evidence_ref")
    return completed


def check_day6(release: dict, data: object, frozen: datetime) -> datetime:
    day, completed = bound(release, data, "day6", after=frozen)
    cases = day.get("cases")
    need(isinstance(cases, list) and len(cases) == 4, "day6 needs both workflows in both languages")
    keys, runs, requests = set(), set(), set()
    for case in cases:
        row = obj(case, "day6.case")
        key = (row.get("workflow"), row.get("language"))
        need(key[0] in WORKFLOWS and key[1] in LANGUAGES and key not in keys,
             "day6 duplicate/missing workflow-language case")
        keys.add(key)
        run = text(row.get("run_id"), "day6.case.run_id")
        model_request = text(row.get("provider_request_id"), "day6.case.provider_request_id")
        need(run not in runs and model_request not in requests, "day6 reused model/run identity")
        runs.add(run)
        requests.add(model_request)
        sha(row.get("output_sha256"), "day6.case.output_sha256")
        referenced(row.get("provider_receipt_ref"), "day6.case.provider_receipt_ref")
        need(row.get("factual_check") is True, "day6 lacks case-specific factual verification")
        files = row.get("native_files")
        need(isinstance(files, list) and len(files) >= 2, "day6 native files are missing")
        extensions, object_keys = set(), set()
        for f in files:
            native = obj(f, "day6.native_file")
            ext = native.get("extension")
            need(ext in {"docx", "pdf"} and ext not in extensions,
                 "day6 must open actual DOCX and PDF outputs")
            extensions.add(ext)
            key_id = text(native.get("artifact_id"), "day6.artifact_id")
            need(key_id not in object_keys, "day6 duplicated a file artifact ID")
            object_keys.add(key_id)
            sha(native.get("sha256"), "day6.native_file.sha256")
            count(native.get("byte_size"), "day6.native_file.byte_size")
            need(native["byte_size"] > 0, "day6 native file has zero bytes")
            need(native.get("mime") == {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                       "pdf": "application/pdf"}[ext], "day6 native MIME mismatch")
            need(native.get("owner_a_opened") is True and native.get("owner_a_hash_verified") is True
                 and native.get("owner_b_http_status") in {403, 404},
                 "day6 requires opened A file and denied B file")
            referenced(native.get("download_receipt_ref"), "day6.download_receipt_ref")
            referenced(native.get("owner_b_denial_ref"), "day6.owner_b_denial_ref")
        need(extensions == {"docx", "pdf"}, "day6 is missing an opened native format")
        if key[0] == "research":
            sources = row.get("citations")
            need(isinstance(sources, list) and len(sources) >= 3,
                 "day6 research must cite three independently checked sources")
            for source in sources:
                citation = obj(source, "day6.research_citation")
                referenced(citation.get("source_id"), "day6.source_id")
                referenced(citation.get("title"), "day6.source.title")
                url = text(citation.get("url"), "day6.source.url")
                parsed = urlsplit(url)
                host = parsed.hostname or ""
                need(parsed.scheme == "https" and bool(host) and "." in host
                     and parsed.username is None and parsed.password is None
                     and host != "localhost" and not host.startswith(("127.", "10.", "192.168.", "172.16.")),
                     "day6 research source URL must be a public HTTPS source without credentials")
                sha(citation.get("sha256"), "day6.source.sha256")
                retrieved = when(citation.get("retrieved_at"), "day6.source.retrieved_at")
                need(retrieved <= completed, "day6 source retrieval postdates verified comparison")
                need(citation.get("quote_verified") is True, "day6 citation quote not verified")
        else:
            email = obj(row.get("email_draft"), "day6.email_draft")
            need(email.get("state") == "unsent" and email.get("send_enabled") is False,
                 "day6 generated an external-send action")
            referenced(email.get("draft_receipt_ref"), "day6.draft_receipt_ref")
    need(keys == {(workflow, language) for workflow in WORKFLOWS for language in LANGUAGES},
         "day6 language/workflow matrix incomplete")
    development = day.get("development_cases")
    need(isinstance(development, list) and len(development) == 40,
         "day6 has not executed the 40-case development registry")
    from collections import Counter
    observed, accepted, ids, model_requests = Counter(), Counter(), set(), set()
    for case in development:
        row = obj(case, "day6.development_case")
        key = (row.get("workflow"), row.get("language"))
        need(key in keys, "day6 development case has an unapproved workflow/language")
        ident = text(row.get("id"), "day6.development_case.id")
        provider = text(row.get("provider_request_id"), "day6.development_case.provider_request_id")
        need(ident not in ids and provider not in model_requests,
             "day6 development case reused identity or model invocation")
        ids.add(ident)
        model_requests.add(provider)
        need(row.get("factual_check") is True and row.get("owner_isolation") is True
             and row.get("citation_check") is True and row.get("no_send") is True,
             "day6 development case failed a hard factual/security boundary")
        score = count(row.get("quality_score"), "day6.development_case.quality_score")
        need(score <= 8, "day6 quality score must be bounded to 8")
        referenced(row.get("evidence_ref"), "day6.development_case.evidence_ref")
        observed[key] += 1
        accepted[key] += int(score >= 7)
    need(all(observed[key] == 10 and accepted[key] >= 9 for key in keys),
         "day6 development quality is below 9/10 in a language/workflow cell")
    reconnect = obj(day.get("reconnect"), "day6.reconnect")
    need(reconnect.get("run_id_before") in runs
         and reconnect.get("run_id_after") == reconnect.get("run_id_before")
         and reconnect.get("worker_before_id") != reconnect.get("worker_after_id"),
         "day6 reconnect did not preserve the same run across real worker replacement")
    for key in ("worker_before_id", "worker_after_id", "worker_replacement_receipt_ref",
                "reconnect_receipt_ref"):
        referenced(reconnect.get(key), "day6.reconnect." + key)
    run_started = when(reconnect.get("run_started_at"), "day6.reconnect.run_started_at")
    disconnected = when(reconnect.get("browser_disconnected_at"), "day6.reconnect.browser_disconnected_at")
    restarted = when(reconnect.get("worker_restarted_at"), "day6.worker_restarted_at")
    reconnected = when(reconnect.get("browser_reconnected_at"), "day6.reconnect.browser_reconnected_at")
    run_finished = when(reconnect.get("run_finished_at"), "day6.reconnect.run_finished_at")
    need(frozen <= run_started < disconnected < restarted < reconnected < run_finished <= completed,
         "day6 browser reconnect/worker replacement did not occur within the same active run")
    count(reconnect.get("additional_agent_runs"), "day6.additional_agent_runs", 0)
    count(reconnect.get("additional_outbox_effects"), "day6.additional_outbox_effects", 0)
    send = obj(day.get("provider_send_audit"), "day6.provider_send_audit")
    before_at = when(send.get("before_at"), "day6.provider_send_audit.before_at")
    after_at = when(send.get("after_at"), "day6.provider_send_audit.after_at")
    need(frozen <= before_at <= when(day["started_at"], "day6.started_at")
         and restarted < after_at <= completed,
         "day6 external send audit does not bracket the operated exercise")
    count(send.get("before"), "day6.provider_send_audit.before", 0)
    count(send.get("after"), "day6.provider_send_audit.after", 0)
    referenced(send.get("external_provider_receipt_ref"), "day6.provider_send_audit.external_provider_receipt_ref")
    return completed


def validate(freeze: object, day3: object, day4: object, day5: object,
             day6: object, review: object, *, expected_revision: str) -> dict:
    """Validate internal consistency only; external receipts remain untrusted."""
    sha(expected_revision, "expected_revision", SHA40)
    release = obj(freeze, "freeze")
    need(release.get("status") == "frozen" and release.get("environment") == "staging",
         "No frozen staging release")
    need(release.get("source_revision") == expected_revision,
         "Requested source differs from frozen staging candidate")
    sha(release.get("runtime_manifest_sha256"), "freeze.runtime_manifest_sha256")
    sha(release.get("rollout_manifest_sha256"), "freeze.rollout_manifest_sha256")
    release_id = text(release.get("release_id"), "freeze.release_id")
    frozen = when(release.get("frozen_at"), "freeze.frozen_at")
    for key in ("api_deployment_id", "worker_deployment_id", "database_revision",
                "provider", "model_id", "owner_a_ref", "owner_b_ref", "operator_id"):
        text(release.get(key), "freeze." + key)
    need(release["api_deployment_id"] != release["worker_deployment_id"],
         "API and worker deployments must be independently identified")
    need(release["owner_a_ref"] != release["owner_b_ref"], "Independent synthetic owners required")
    source_db_revision = text(release.get("source_database_revision"), "freeze.source_database_revision")
    need(source_db_revision == release["database_revision"],
         "The staged database revision differs from the expected source migration")
    for label in ("api_deployment_receipt_ref", "worker_deployment_receipt_ref",
                  "database_revision_receipt_ref", "provider_budget_approval_ref",
                  "source_ci_run_ref", "governance_audit_receipt_ref"):
        referenced(release.get(label), "freeze." + label)
    for label in ("api_deployed_at", "worker_deployed_at", "database_revision_verified_at"):
        need(when(release.get(label), "freeze." + label) <= frozen,
             "Release freeze predates an independently observed deployment/schema readback")
    count(release.get("budget_tokens"), "freeze.budget_tokens")
    need(release["budget_tokens"] > 0, "Model budget must be approved and nonzero")
    for key in ("api_source_revision", "worker_source_revision"):
        need(release.get(key) == expected_revision, f"freeze.{key} does not match")
    if release.get("source_ci_status") != "passed" or release.get("governance_status") != "passed":
        raise Days36EvidenceError("Source CI and independent governance must both have passed")
    times = {
        "day3": check_day3(release, day3, frozen),
        "day4": check_day4(release, day4, frozen),
        "day5": check_day5(release, day5, frozen),
        "day6": check_day6(release, day6, frozen),
    }
    reviewed = obj(review, "independent_review")
    for field in BOUND:
        need(reviewed.get(field) == release.get(field),
             f"independent_review changed frozen {field}")
    need(reviewed.get("status") == "passed"
         and reviewed.get("role") == "independent_reviewer"
         and reviewed.get("independent_platform_readback") is True,
         "Independent reviewer/platform verification missing")
    reviewer = text(reviewed.get("reviewer_id"), "independent_review.reviewer_id")
    need(reviewer != release["operator_id"], "Operator cannot independently review their own exercise")
    referenced(reviewed.get("review_evidence_ref"), "independent_review.review_evidence_ref")
    when_reviewed = when(reviewed.get("reviewed_at"), "independent_review.reviewed_at")
    need(when_reviewed >= max(times.values()), "Independent review predates a workflow")
    conclusions = obj(reviewed.get("days"), "independent_review.days")
    need(set(conclusions) == set(times) and all(conclusions.get(k) is True for k in times),
         "No independent yes/no judgment for all Days 3–6")
    return {
        "status": "evidence_internally_consistent_not_live_attested",
        "release_id": release_id,
        "source_revision": expected_revision,
        "runtime_manifest_sha256": release["runtime_manifest_sha256"],
        "rollout_manifest_sha256": release["rollout_manifest_sha256"],
        "source_database_revision": source_db_revision,
        "workflow_days": sorted(times),
        "caveat": "Operator-provided receipts require direct, independent platform authentication; this script cannot certify hosted execution.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("freeze", "day3", "day4", "day5", "day6", "review"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        need(os.getenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT") == "true",
             "Synthetic staging-account guard is required")
        need(os.getenv("SHUDDHO_STAGING_ALLOW_DAYS36_VERIFICATION") == "true",
             "Days 3–6 staging verification guard is required")
        need(args.output.parent.is_dir() and not args.output.exists() and not args.output.is_symlink(),
             "A new private output path is required")
        inputs = []
        for path in (args.freeze, args.day3, args.day4, args.day5, args.day6, args.review):
            need(path.is_file() and not path.is_symlink()
                 and 0 < path.stat().st_size <= MAX_EVIDENCE_BYTES,
                 "Evidence input is absent, symbolic, empty or too large")
            inputs.append(json.loads(path.read_text(encoding="utf-8")))
        decision = validate(*inputs, expected_revision=args.expected_revision)
        from scripts.staging_release_evidence import write_private_json
        write_private_json(args.output, decision)
        print(json.dumps({"status": decision["status"], "output": str(args.output)}))
    except (Days36EvidenceError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "rejected",
                          "error": str(exc) if isinstance(exc, Days36EvidenceError) else type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
