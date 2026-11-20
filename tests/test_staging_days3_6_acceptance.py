"""Synthetic adversarial contract tests, NOT hosted Days 3–6 evidence."""
from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import staging_days3_6_acceptance as gate

SHA = "a" * 40
DIGEST = "b" * 64
D2 = "c" * 64
D3 = "d" * 64
D4 = "e" * 64
D5 = "f" * 64
T0 = "2026-11-18T00:00:00Z"
T1 = "2026-11-18T01:00:00Z"
T2 = "2026-11-18T02:00:00Z"
T3 = "2026-11-18T03:00:00Z"
T4 = "2026-11-18T04:00:00Z"
T5 = "2026-11-18T05:00:00Z"
T7 = "2026-11-18T07:00:00Z"
T8 = "2026-11-18T08:00:00Z"


def bound(freeze):
    return {key: freeze[key] for key in gate.BOUND}


def stamp(freeze, start, finish):
    return {
        **bound(freeze),
        "status": "passed", "mode": "hosted",
        "evidence_ref": "redacted-owned-hosted-receipt",
        "started_at": start, "verified_at": finish,
    }


def evidence():
    freeze = {
        "status": "frozen", "environment": "staging", "release_id": "release-A",
        "source_revision": SHA, "runtime_manifest_sha256": DIGEST,
        "rollout_manifest_sha256": D2,
        "api_deployment_id": "dep-api-A", "worker_deployment_id": "dep-worker-A",
        "database_revision": "0072_merge_0071_heads",
        "source_database_revision": "0072_merge_0071_heads",
        "api_deployment_receipt_ref": "render-api-deployment-witness",
        "worker_deployment_receipt_ref": "render-worker-deployment-witness",
        "database_revision_receipt_ref": "supabase-schema-witness",
        "provider_budget_approval_ref": "founder-approved-model-budget",
        "source_ci_run_ref": "github-exact-head-run",
        "governance_audit_receipt_ref": "independent-governance-readback",
        "api_deployed_at": T0, "worker_deployed_at": T0,
        "database_revision_verified_at": T0,
        "api_source_revision": SHA, "worker_source_revision": SHA,
        "provider": "provider-test", "model_id": "model-test", "budget_tokens": 900,
        "owner_a_ref": "synthetic-A", "owner_b_ref": "synthetic-B",
        "operator_id": "operator-C", "frozen_at": T0,
        "source_ci_status": "passed", "governance_status": "passed",
    }
    day3 = {
        **stamp(freeze, T1, T2),
        "answers": [{
            "language": language, "provider_request_id": "model-answer-" + language,
            "answer_sha256": D2, "selected_document_sha256": D3,
            "citation_ids": ["src-1"], "factual_check": True, "owner_b_denied": True,
            "answer_receipt_ref": "owned-answer-" + language,
        } for language in ("bn", "en")],
        "revocation": {
            "provider_started_at": "2026-11-18T01:05:00Z",
            "revoked_at": "2026-11-18T01:15:00Z",
            "provider_finished_at": "2026-11-18T01:20:00Z",
            "provider_request_id": "model-revoke-A",
            "revocation_receipt_ref": "revoke-event-A", "source_revoked": True,
            "visible_deltas_after_revoke": 0, "persisted_stale_answers": 0,
        },
        "agent_runs_before": 0, "agent_runs_after": 0,
        "agent_outbox_before": 0, "agent_outbox_after": 0,
    }
    day4 = {
        **stamp(freeze, "2026-11-18T02:30:00Z", T3),
        "brief_language": "bn",
        "initial_digest": D2, "edited_digest": D3,
        "approved_digest": D3, "start_digest": D3,
        "edited_at": "2026-11-18T02:35:00Z",
        "approved_at": "2026-11-18T02:40:00Z",
        "start_at": "2026-11-18T02:45:00Z",
        "agent_run_id": "run-day4-A", "start_receipt_ref": "start-event-A",
        "owner_b_denied": True, "owner_b_denial_ref": "day4-B-denial",
        "agent_runs_before": 3, "agent_runs_after": 4,
        "outbox_before": 7, "outbox_after": 8,
        "retry": {"same_run_id": "run-day4-A", "http_status": 202,
                  "additional_runs": 0, "additional_outbox": 0},
        "start_edit_race": {
            "http_status": 409, "additional_runs": 0, "additional_outbox": 0,
            "started_at": "2026-11-18T02:46:00Z",
            "edit_committed_at": "2026-11-18T02:47:00Z",
            "responded_at": "2026-11-18T02:48:00Z",
        },
        "retry_receipt_ref": "retry-event-A", "race_receipt_ref": "race-event-A",
    }
    arms = []
    for name, index in (("none", 0), ("v1", 1), ("v2", 2)):
        arms.append({
            "name": name, "prompt_sha256": D2, "source_sha256": D3,
            "model_context_sha256": [D2, D3, D4][index],
            "output_sha256": [D3, D4, D5][index],
            "provider_request_id": f"model-request-{name}", "agent_run_id": f"run-{name}",
            "provider_receipt_ref": f"model-proof-{name}",
            "provider": freeze["provider"], "model_id": freeze["model_id"],
            "budget_tokens": freeze["budget_tokens"],
            "fact_id": None if name == "none" else "fact-A",
            "fact_version": None if name == "none" else index,
            "observed_claim": ["No memory claim", "Original fact", "Corrected fact"][index],
        })
    day5 = {
        **stamp(freeze, "2026-11-18T03:30:00Z", T4), "arms": arms,
        "exclusions": [{
            "kind": name, "http_status": 409, "model_calls_after_denial": 0,
            "evidence_ref": f"denial-{name}",
        } for name in sorted(gate.NEGATIVES)],
        "unselected_memory": {
            "unselected_fact_id": "unselected-same-category",
            "absent_from_all_model_inputs": True,
            "evidence_ref": "provider-context-digest-attestation",
        },
        "historical_replay": {
            "agent_run_id": "run-v1", "output_sha256": D4,
            "new_outbox_effects": 0, "evidence_ref": "replay-v1",
        },
    }

    cases = []
    for workflow in sorted(gate.WORKFLOWS):
        for language in sorted(gate.LANGUAGES):
            key = f"{workflow}-{language}"
            row = {
                "workflow": workflow, "language": language,
                "run_id": f"run-{key}", "provider_request_id": f"provider-{key}",
                "provider_receipt_ref": f"provider-proof-{key}",
                "output_sha256": D4, "factual_check": True,
                "native_files": [{
                    "artifact_id": f"{key}-{ext}",
                    "extension": ext, "sha256": D5, "byte_size": 512,
                    "mime": {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             "pdf": "application/pdf"}[ext],
                    "owner_a_opened": True, "owner_a_hash_verified": True,
                    "owner_b_http_status": 404, "download_receipt_ref": f"owned-file-{key}-{ext}",
                    "owner_b_denial_ref": f"denied-file-{key}-{ext}",
                } for ext in ("docx", "pdf")],
            }
            if workflow == "research":
                row["citations"] = [{
                    "source_id": f"source-{i}", "url": f"https://example.org/study-{i}",
                    "title": f"Synthetic study {i}",
                    "sha256": D2, "retrieved_at": T5, "quote_verified": True,
                } for i in (1, 2, 3)]
            else:
                row["email_draft"] = {
                    "state": "unsent", "send_enabled": False,
                    "draft_receipt_ref": "owned-email-draft-" + key,
                }
            cases.append(row)
    day6 = {
        **stamp(freeze, T5, T7), "cases": cases,
        "development_cases": [{
            "id": f"{workflow}-{language}-{n}",
            "workflow": workflow, "language": language,
            "provider_request_id": f"development-model-{workflow}-{language}-{n}",
            "factual_check": True, "owner_isolation": True,
            "citation_check": True, "no_send": True,
            "quality_score": 8, "evidence_ref": f"dev-case-{workflow}-{language}-{n}",
        } for workflow in sorted(gate.WORKFLOWS)
          for language in sorted(gate.LANGUAGES) for n in range(10)],
        "reconnect": {
            "run_id_before": "run-research-bn", "run_id_after": "run-research-bn",
            "worker_before_id": "worker-A", "worker_after_id": "worker-B",
            "worker_replacement_receipt_ref": "replacement-evt",
            "reconnect_receipt_ref": "connection-evt",
            "run_started_at": "2026-11-18T05:15:00Z",
            "browser_disconnected_at": "2026-11-18T05:45:00Z",
            "worker_restarted_at": "2026-11-18T06:00:00Z",
            "browser_reconnected_at": "2026-11-18T06:10:00Z",
            "run_finished_at": "2026-11-18T06:20:00Z",
            "additional_agent_runs": 0, "additional_outbox_effects": 0,
        },
        "provider_send_audit": {
            "before": 0, "after": 0,
            "before_at": "2026-11-18T04:59:00Z", "after_at": "2026-11-18T06:59:00Z",
            "external_provider_receipt_ref": "send-audit-service",
        },
    }
    review = {
        **bound(freeze), "status": "passed", "role": "independent_reviewer",
        "independent_platform_readback": True,
        "reviewer_id": "reviewer-D", "review_evidence_ref": "d-attestation",
        "reviewed_at": T8,
        "days": {"day3": True, "day4": True, "day5": True, "day6": True},
    }
    return [freeze, day3, day4, day5, day6, review]


def validate(args):
    return gate.validate(*args, expected_revision=SHA)


def test_consistent_synthetic_receipts_are_not_automatically_a_hosted_pass():
    result = validate(evidence())
    assert result["status"] == "evidence_internally_consistent_not_live_attested"
    assert result["workflow_days"] == ["day3", "day4", "day5", "day6"]
    assert "independent" in result["caveat"].lower()


@pytest.mark.parametrize("target, path, new_value", [
    (0, ("source_revision",), "b" * 40),
    (0, ("worker_source_revision",), "b" * 40),
    (0, ("source_ci_status",), "skipped"),
    (0, ("governance_status",), "missing"),
    (0, ("rollout_manifest_sha256",), "not-a-digest"),
    (0, ("source_database_revision",), "0070"),
    (0, ("database_revision_receipt_ref",), ""),
    (0, ("worker_deployed_at",), T1),
    (0, ("worker_deployment_id",), "dep-api-A"),
    (0, ("owner_b_ref",), "synthetic-A"),
    (1, ("source_revision",), "b" * 40),
    (1, ("mode",), "simulated"),
    (1, ("agent_runs_after",), 1),
    (1, ("agent_outbox_after",), 1),
    (1, ("answers", 0, "citation_ids"), ["src-99"]),
    (1, ("answers", 1, "language"), "bn"),
    (1, ("revocation", "revoked_at"), "2026-11-18T01:25:00Z"),
    (1, ("revocation", "visible_deltas_after_revoke"), 1),
    (1, ("revocation", "persisted_stale_answers"), 1),
    (2, ("start_digest",), D2),
    (2, ("approved_digest",), D2),
    (2, ("agent_runs_after",), 5),
    (2, ("outbox_after",), 9),
    (2, ("retry", "additional_runs"), 1),
    (2, ("start_edit_race", "http_status"), 200),
    (2, ("start_edit_race", "edit_committed_at"), "2026-11-18T02:49:00Z"),
    (2, ("owner_b_denied",), False),
    (3, ("unselected_memory", "absent_from_all_model_inputs"), False),
    (3, ("arms", 2, "fact_version"), 3),
    (3, ("arms", 1, "fact_version"), True),
    (3, ("arms", 2, "provider"), "different-provider"),
    (3, ("arms", 1, "prompt_sha256"), D4),
    (3, ("arms", 2, "observed_claim"), "Original fact"),
    (3, ("exclusions", 0, "model_calls_after_denial"), 1),
    (3, ("historical_replay", "new_outbox_effects"), 1),
    (4, ("cases", 0, "native_files", 0, "owner_b_http_status"), 200),
    (4, ("cases", 0, "native_files", 0, "owner_a_hash_verified"), False),
    (4, ("cases", 0, "native_files", 1, "mime"), "application/pdf_wrong"),
    (4, ("cases", 2, "citations", 0, "quote_verified"), False),
    (4, ("cases", 2, "citations", 0, "retrieved_at"), "2026-11-18T09:00:00Z"),
    (4, ("development_cases", 0, "quality_score"), 9),
    (4, ("development_cases", 1, "no_send"), False),
    (4, ("reconnect", "worker_after_id"), "worker-A"),
    (4, ("reconnect", "run_finished_at"), "2026-11-18T05:50:00Z"),
    (4, ("reconnect", "browser_reconnected_at"), "2026-11-18T05:55:00Z"),
    (4, ("reconnect", "additional_agent_runs"), 1),
    (4, ("provider_send_audit", "after"), 1),
    (4, ("provider_send_audit", "before_at"), T7),
    (4, ("cases", 0, "native_files", 0, "owner_b_denial_ref"), ""),
    (5, ("role",), "operator"),
    (5, ("independent_platform_readback",), False),
    (5, ("reviewer_id",), "operator-C"),
    (5, ("reviewed_at",), T1),
    (5, ("days", "day6"), False),
])
def test_missing_foreign_stale_or_unverified_receipt_fails_closed(target, path, new_value):
    args = evidence()
    node = args[target]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = new_value
    with pytest.raises(gate.Days36EvidenceError):
        validate(args)


def test_no_receipts_no_pass_and_explicit_empty_selection_exclusions():
    args = evidence()
    for target in (1, 2, 3, 4, 5):
        value = deepcopy(args)
        value[target] = {}
        with pytest.raises(gate.Days36EvidenceError):
            validate(value)
    args = evidence()
    args[3]["exclusions"].pop()
    with pytest.raises(gate.Days36EvidenceError, match="denial"):
        validate(args)
    args = evidence()
    args[3]["arms"][0]["fact_id"] = "unselected-fact"
    with pytest.raises(gate.Days36EvidenceError, match="none arm"):
        validate(args)


def test_day6_quality_fails_when_two_of_ten_cases_in_one_cell_fail():
    args = evidence()
    # 9/10 is acceptable, 8/10 is not. Keep the other 30 cases green.
    args[4]["development_cases"][0]["quality_score"] = 0
    assert validate(args)["status"] == "evidence_internally_consistent_not_live_attested"
    args[4]["development_cases"][1]["quality_score"] = 0
    with pytest.raises(gate.Days36EvidenceError, match="quality"):
        validate(args)


def test_day3_direct_chat_allows_existing_owner_runs_with_zero_new_effects():
    args = evidence()
    args[1].update({
        "agent_runs_before": 3, "agent_runs_after": 3,
        "agent_outbox_before": 7, "agent_outbox_after": 7,
    })
    # Direct chat has no NEW AgentRun or outbox effects; old work may exist.
    assert validate(args)["status"] == "evidence_internally_consistent_not_live_attested"


@pytest.mark.parametrize("field", ["agent_runs_after", "agent_outbox_after"])
def test_day3_preexisting_counts_still_deny_new_chat_side_effects(field):
    args = evidence()
    args[1].update({
        "agent_runs_before": 3, "agent_runs_after": 3,
        "agent_outbox_before": 7, "agent_outbox_after": 7,
    })
    args[1][field] += 1
    with pytest.raises(gate.Days36EvidenceError, match="day3"):
        validate(args)


def test_counts_reject_bools_and_noncanonical_hashes():
    args = evidence()
    args[1]["agent_runs_after"] = False
    with pytest.raises(gate.Days36EvidenceError):
        validate(args)
    args = evidence()
    args[4]["cases"][0]["native_files"][0]["sha256"] = "ABCDEF" * 10 + "1234"
    with pytest.raises(gate.Days36EvidenceError):
        validate(args)


def test_timestamp_requires_timezone_and_attestation_after_all_days():
    args = evidence()
    args[4]["started_at"] = "2026-11-18T05:00:00"
    with pytest.raises(gate.Days36EvidenceError, match="timezone"):
        validate(args)
    args = evidence()
    args[5]["reviewed_at"] = "2026-11-18T06:00:00Z"
    with pytest.raises(gate.Days36EvidenceError, match="predates"):
        validate(args)


@pytest.mark.parametrize(("first", "second", "extension"), [
    (0, 1, "docx"),  # Same workflow, different output language.
    (0, 2, "pdf"),   # Same language, different workflow.
    (1, 3, "docx"),  # Cross-language and cross-workflow.
])
def test_day6_cannot_reuse_native_artifact_identity_across_cases(first, second, extension):
    args = evidence()
    files1 = args[4]["cases"][first]["native_files"]
    files2 = args[4]["cases"][second]["native_files"]
    source = next(item for item in files1 if item["extension"] == extension)
    copy = next(item for item in files2 if item["extension"] == extension)
    # Different bytes and independently named receipts cannot turn one stored
    # artifact identity into two independently generated user deliverables.
    copy["artifact_id"] = source["artifact_id"]
    copy["sha256"] = D4
    assert copy["download_receipt_ref"] != source["download_receipt_ref"]
    with pytest.raises(gate.Days36EvidenceError, match="reused across"):
        validate(args)
