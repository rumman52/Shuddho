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
            "selected_document_id": "owner-A-document",
            "selected_document_version_id": "owner-A-version-1",
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
        "prompt_injection": {
            "source_document_id": "owner-A-document",
            "source_document_version_id": "owner-A-version-1",
            "source_document_sha256": D3,
            "provider_request_id": "model-answer-en",
            "provider_receipt_ref": "provider-injection-A",
            "provider_started_at": "2026-11-18T01:01:00Z",
            "provider_finished_at": "2026-11-18T01:03:00Z",
            "verified_at": "2026-11-18T01:04:00Z",
            "contains_conflicting_source_instruction": True,
            "user_instruction_followed": True,
            "source_instruction_ignored": True,
            "additional_agent_runs": 0,
            "additional_outbox_effects": 0,
            "browser_evidence_ref": "injection-browser-A",
        },
        "owner_b_fixture": {
            "document_id": "owner-B-document",
            "document_version_id": "owner-B-version-1",
            "document_sha256": D4,
            "owner_b_read_http_status": 200,
            "owner_a_read_http_status": 403,
            "owner_b_read_receipt_ref": "owner-B-positive-source-read",
            "owner_a_denial_receipt_ref": "owner-A-denied-B-source",
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
            "owner_ref": freeze["owner_a_ref"],
            "document_version_id": "owner-A-version-1",
            "reviewed_brief_sha256": D2,
            "tool_policy_sha256": D3,
            "preview_digest_sha256": [D3, D4, D5][index],
            "admitted_preview_digest_sha256": [D3, D4, D5][index],
            "provider_started_at": [
                "2026-11-18T03:31:00Z", "2026-11-18T03:33:00Z", "2026-11-18T03:48:00Z"
            ][index],
            "provider_finished_at": [
                "2026-11-18T03:32:00Z", "2026-11-18T03:34:00Z", "2026-11-18T03:49:00Z"
            ][index],
            "preview_selected_memory": [] if name == "none" else [
                {"fact_id": "fact-A", "version": index}
            ],
            "worker_selected_memory": [] if name == "none" else [
                {"fact_id": "fact-A", "version": index}
            ],
            "preview_receipt_ref": f"preview-{name}",
            "worker_context_receipt_ref": f"worker-context-{name}",
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
            "selected_category": "project-style",
            "unselected_category": "project-style",
            "absent_from_all_model_inputs": True,
            "evidence_ref": "provider-context-digest-attestation",
        },
        "owner_access": {
            "owner_a": {
                "owner_ref": freeze["owner_a_ref"],
                "own_fact_id": "fact-A",
                "own_context_id": "run-v1", "own_output_id": "private-output-A",
                "own_output_sha256": D4,
                "own_fact_http_status": 200,
                "own_context_http_status": 200,
                "own_output_http_status": 200,
                "own_context_read_receipt_ref": "owner-A-positive-context-read",
                "own_output_read_receipt_ref": "owner-A-positive-output-read",
                "foreign_fact_target_id": "fact-B",
                "foreign_context_target_id": "run-owner-B",
                "foreign_output_target_id": "private-output-B",
                "foreign_fact_owner_ref": freeze["owner_b_ref"],
                "foreign_context_owner_ref": freeze["owner_b_ref"],
                "foreign_output_owner_ref": freeze["owner_b_ref"],
                "foreign_fact_http_status": 403,
                "foreign_context_http_status": 403,
                "foreign_output_http_status": 403,
                "own_read_receipt_ref": "owner-A-positive-fact-read",
                "foreign_fact_denial_ref": "owner-A-denied-B-fact",
                "foreign_context_denial_ref": "owner-A-denied-B-context",
                "foreign_output_denial_ref": "owner-A-denied-B-output",
            },
            "owner_b": {
                "owner_ref": freeze["owner_b_ref"],
                "own_fact_id": "fact-B",
                "own_context_id": "run-owner-B", "own_output_id": "private-output-B",
                "own_output_sha256": D5,
                "own_fact_http_status": 200,
                "own_context_http_status": 200,
                "own_output_http_status": 200,
                "own_context_read_receipt_ref": "owner-B-positive-context-read",
                "own_output_read_receipt_ref": "owner-B-positive-output-read",
                "foreign_fact_target_id": "fact-A",
                "foreign_context_target_id": "run-v1",
                "foreign_output_target_id": "private-output-A",
                "foreign_fact_owner_ref": freeze["owner_a_ref"],
                "foreign_context_owner_ref": freeze["owner_a_ref"],
                "foreign_output_owner_ref": freeze["owner_a_ref"],
                "foreign_fact_http_status": 403,
                "foreign_context_http_status": 403,
                "foreign_output_http_status": 403,
                "own_read_receipt_ref": "owner-B-positive-fact-read",
                "foreign_fact_denial_ref": "owner-B-denied-A-fact",
                "foreign_context_denial_ref": "owner-B-denied-A-context",
                "foreign_output_denial_ref": "owner-B-denied-A-output",
            },
        },
        "inflight_correction": {
            "owner_ref": freeze["owner_a_ref"],
            "fact_id": "fact-A",
            "original_version": 1, "corrected_version": 2,
            "worker_selected_memory": [{"fact_id": "fact-A", "version": 1}],
            "worker_context_receipt_ref": "inflight-worker-pinned-context",
            "run_id": "inflight-run-A",
            "provider_request_id": "inflight-provider-A",
            "provider_started_at": "2026-11-18T03:37:00Z",
            "corrected_at": "2026-11-18T03:40:00Z",
            "provider_finished_at": "2026-11-18T03:43:00Z",
            "commit_attempted_at": "2026-11-18T03:44:00Z",
            "rejection_verified_at": "2026-11-18T03:46:00Z",
            "commit_error_code": "memory_pins_changed",
            "new_decisions_committed": 0,
            "new_tool_invocations": 0,
            "new_outbox_effects": 0,
            "provider_receipt_ref": "inflight-provider-readback",
            "memory_update_receipt_ref": "inflight-memory-correction",
            "decision_commit_denial_ref": "inflight-stale-commit-denial",
            "decision_store_readback_ref": "inflight-decision-store-readback",
        },
        "historical_replay": {
            "agent_run_id": "run-v1", "output_sha256": D4,
            "new_outbox_effects": 0, "new_decisions_committed": 0,
            "replayed_at": "2026-11-18T03:54:00Z",
            "decision_receipt_ref": "historical-v1-decision-readback",
            "evidence_ref": "replay-v1",
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
                    "manifest_sha256": D5, "object_store_sha256": D5,
                    "owner_download_sha256": D5, "object_store_byte_size": 512,
                    "owner_download_byte_size": 512, "owner_a_http_status": 200,
                    "storage_object_ref": f"private-object-{key}-{ext}",
                    "manifest_receipt_ref": f"manifest-readback-{key}-{ext}",
                    "object_store_receipt_ref": f"storage-readback-{key}-{ext}",
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
                    "sha256": [D2, D3, D4][i - 1],
                    "retrieved_at": T5, "quote_verified": True,
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
            "artifacts_before": [
                {"artifact_id": "research-bn-docx", "sha256": D5}
            ],
            "artifacts_after": [
                {"artifact_id": f"research-bn-{extension}", "sha256": D5}
                for extension in ("docx", "pdf")
            ],
            "run_agent_effects_before": 1, "run_agent_effects_after": 1,
            "run_outbox_effects_before": 1, "run_outbox_effects_after": 1,
            "before_snapshot_at": "2026-11-18T05:30:00Z",
            "after_snapshot_at": "2026-11-18T06:30:00Z",
            "before_snapshot_receipt_ref": "pre-reconnect-operator-readback",
            "after_snapshot_receipt_ref": "post-reconnect-operator-readback",
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


@pytest.mark.parametrize("language", ["bn", "en"])
@pytest.mark.parametrize("collision", ["source_id", "url", "sha256", "url_fragment"])
def test_day6_rejects_duplicate_research_evidence_within_each_language(language, collision):
    args = evidence()
    research = next(
        row for row in args[4]["cases"]
        if row["workflow"] == "research" and row["language"] == language
    )
    original, duplicate = research["citations"][:2]
    if collision == "url_fragment":
        # Anchors to different fragments of one fetched document are not
        # independent evidence and must not count as separate sources.
        duplicate["url"] = original["url"] + "#different-section"
    else:
        duplicate[collision] = original[collision]

    # Titles and other fields remain distinct: reusing even one authoritative
    # source identity must not satisfy the independent-three-source contract.
    assert duplicate["title"] != original["title"]
    with pytest.raises(gate.Days36EvidenceError, match="independent"):
        validate(args)


@pytest.mark.parametrize("language", ["bn", "en"])
@pytest.mark.parametrize("url", [
    "https://172.17.0.1/report",        # RFC1918 range missed by prefix checks
    "https://169.254.169.254/report",   # link-local / metadata address
    "https://100.64.0.1/report",       # shared address space, not public
    "https://127.1/report",            # noncanonical IPv4 loopback notation
    "https://0177.0.0.1/report",       # noncanonical numeric IPv4 notation
    "https://localhost./report",      # trailing dot bypasses exact-name check
    "https://service.local/report",   # local DNS suffix
    "https://[::1]/report",           # IPv6 loopback
    "https://[fc00::1]/report",       # IPv6 unique-local
    "https://[fe80::1]/report",       # IPv6 link-local
])
def test_day6_rejects_private_or_nonpublic_research_url(language, url):
    args = evidence()
    research = next(row for row in args[4]["cases"]
                    if row["workflow"] == "research" and row["language"] == language)
    research["citations"][0]["url"] = url
    with pytest.raises(gate.Days36EvidenceError, match="public HTTPS"):
        validate(args)


@pytest.mark.parametrize("url", [
    "https://example.org/study-1",   # ordinary approved DNS URL
    "https://1.1.1.1/study-1",       # globally routable IPv4 literal
    "https://[2001:4860:4860::8888]/study-1",  # globally routable IPv6
])
def test_day6_public_https_source_urls_remain_structurally_valid(url):
    args = evidence()
    research = next(row for row in args[4]["cases"]
                    if row["workflow"] == "research" and row["language"] == "bn")
    research["citations"][0]["url"] = url
    # Structural acceptance is NOT evidence of a genuine hosted retrieval.
    assert validate(args)["status"] == "evidence_internally_consistent_not_live_attested"


@pytest.mark.parametrize(("field", "foreign"), [
    ("selected_document_id", "other-owner-document"),
    ("selected_document_version_id", "outdated-version"),
    ("selected_document_sha256", D4),
])
def test_day3_bilingual_replies_must_share_exact_pinned_document_version(field, foreign):
    args = evidence()
    args[1]["answers"][1][field] = foreign
    with pytest.raises(gate.Days36EvidenceError, match="pinned.*document"):
        validate(args)


@pytest.mark.parametrize("field", [
    "selected_document_id", "selected_document_version_id",
])
def test_day3_requires_document_identity_and_version_on_every_answer(field):
    args = evidence()
    del args[1]["answers"][0][field]
    with pytest.raises(gate.Days36EvidenceError, match="document"):
        validate(args)


def test_day3_requires_an_observed_prompt_injection_receipt():
    args = evidence()
    del args[1]["prompt_injection"]
    with pytest.raises(gate.Days36EvidenceError, match="prompt_injection"):
        validate(args)


@pytest.mark.parametrize(("field", "invalid"), [
    ("contains_conflicting_source_instruction", False),
    ("user_instruction_followed", False),
    ("source_instruction_ignored", False),
    ("additional_agent_runs", 1),
    ("additional_outbox_effects", 1),
    ("source_document_sha256", D4),
    ("source_document_id", "forged-document"),
    ("source_document_version_id", "forged-version"),
    ("provider_request_id", "model-revoke-A"),
    ("provider_request_id", "unrelated-model-request"),
    ("provider_receipt_ref", ""),
    ("browser_evidence_ref", ""),
    ("provider_started_at", "2026-11-18T00:59:00Z"),
    ("provider_finished_at", "2026-11-18T01:00:00Z"),
    ("verified_at", "2026-11-18T01:02:00Z"),
])
def test_day3_rejects_unverified_or_foreign_prompt_injection_probe(field, invalid):
    args = evidence()
    args[1]["prompt_injection"][field] = invalid
    with pytest.raises(gate.Days36EvidenceError, match="prompt_injection"):
        validate(args)


def test_day3_injection_witness_can_share_the_english_answer_model_call():
    args = evidence()
    assert args[1]["prompt_injection"]["provider_request_id"] == args[1]["answers"][1]["provider_request_id"]
    # The golden document already contains the harmless conflicting instruction;
    # an extra third provider call is not required for this acceptance.
    assert validate(args)["status"] == "evidence_internally_consistent_not_live_attested"


def test_day3_requires_reciprocal_owner_b_fixture_read_and_denial():
    args = evidence()
    del args[1]["owner_b_fixture"]
    with pytest.raises(gate.Days36EvidenceError, match="owner_b_fixture"):
        validate(args)


@pytest.mark.parametrize(("field", "invalid"), [
    ("document_id", "owner-A-document"),
    ("document_version_id", "owner-A-version-1"),
    ("document_sha256", D3),
    ("owner_b_read_http_status", 403),
    ("owner_a_read_http_status", 200),
    ("owner_b_read_receipt_ref", ""),
    ("owner_a_denial_receipt_ref", ""),
])
def test_day3_rejects_one_way_or_nonindependent_owner_b_fixture(field, invalid):
    args = evidence()
    args[1]["owner_b_fixture"][field] = invalid
    with pytest.raises(gate.Days36EvidenceError, match="owner_b_fixture"):
        validate(args)


@pytest.mark.parametrize(("arm_index", "field", "value"), [
    (1, "document_version_id", "old-owner-A-version"),
    (2, "reviewed_brief_sha256", D4),
    (0, "tool_policy_sha256", D4),
    (2, "owner_ref", "synthetic-B"),
    (0, "document_version_id", ""),
    (1, "reviewed_brief_sha256", "invalid"),
    (1, "tool_policy_sha256", "invalid"),
])
def test_day5_rejects_drift_in_frozen_memory_experiment_inputs(arm_index, field, value):
    args = evidence()
    args[3]["arms"][arm_index][field] = value
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize(("arm_index", "field", "pins"), [
    (0, "preview_selected_memory", [{"fact_id": "fact-A", "version": 1}]),
    (0, "worker_selected_memory", [{"fact_id": "fact-A", "version": 1}]),
    (1, "preview_selected_memory", []),
    (1, "worker_selected_memory", []),
    (1, "preview_selected_memory", [{"fact_id": "fact-A", "version": 2}]),
    (2, "worker_selected_memory", [{"fact_id": "fact-B", "version": 2}]),
    (2, "preview_selected_memory", [
        {"fact_id": "fact-A", "version": 2}, {"fact_id": "hidden-other", "version": 1},
    ]),
    (2, "worker_selected_memory", [{"fact_id": "fact-A", "version": True}]),
    (0, "worker_selected_memory", None),
])
def test_day5_rejects_preview_or_worker_pins_that_differ_from_explicit_selection(
    arm_index, field, pins
):
    args = evidence()
    args[3]["arms"][arm_index][field] = pins
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize("field", ["preview_receipt_ref", "worker_context_receipt_ref"])
def test_day5_requires_preview_and_worker_context_receipts_per_arm(field):
    args = evidence()
    args[3]["arms"][1][field] = ""
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize(("field", "value"), [
    ("selected_category", "other-category"),
    ("unselected_category", "unrelated-category"),
    ("unselected_category", ""),
])
def test_day5_same_category_unselected_fact_must_be_witnessed(field, value):
    args = evidence()
    args[3]["unselected_memory"][field] = value
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


def test_day5_cannot_claim_two_owner_memory_isolation_without_both_probes():
    args = evidence()
    del args[3]["owner_access"]
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize(("owner", "field", "invalid"), [
    ("owner_a", "owner_ref", "synthetic-B"),
    ("owner_b", "owner_ref", "synthetic-A"),
    ("owner_b", "own_fact_id", "fact-A"),
    ("owner_a", "own_fact_http_status", 403),
    ("owner_b", "own_fact_http_status", 404),
    ("owner_a", "foreign_fact_http_status", 200),
    ("owner_b", "foreign_context_http_status", 200),
    ("owner_a", "foreign_output_http_status", 200),
    ("owner_a", "own_read_receipt_ref", ""),
    ("owner_b", "foreign_fact_denial_ref", ""),
    ("owner_b", "foreign_context_denial_ref", ""),
    ("owner_a", "foreign_output_denial_ref", ""),
])
def test_day5_rejects_foreign_memory_fact_context_or_private_output_access(owner, field, invalid):
    args = evidence()
    args[3]["owner_access"][owner][field] = invalid
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize(("field", "invalid"), [
    ("manifest_sha256", D4),
    ("object_store_sha256", D4),
    ("owner_download_sha256", D4),
    ("manifest_sha256", "not-sha256"),
    ("object_store_byte_size", 513),
    ("owner_download_byte_size", 0),
    ("owner_download_byte_size", 513),
    ("owner_a_http_status", 403),
    ("storage_object_ref", ""),
    ("manifest_receipt_ref", ""),
    ("object_store_receipt_ref", ""),
])
def test_day6_rejects_native_file_that_is_not_byte_identical_across_readbacks(field, invalid):
    args = evidence()
    args[4]["cases"][0]["native_files"][0][field] = invalid
    with pytest.raises(gate.Days36EvidenceError, match="day6"):
        validate(args)


@pytest.mark.parametrize("field", [
    "manifest_sha256", "object_store_sha256", "owner_download_sha256",
    "object_store_byte_size", "owner_download_byte_size",
    "owner_a_http_status", "storage_object_ref",
    "manifest_receipt_ref", "object_store_receipt_ref",
])
def test_day6_rejects_missing_native_storage_manifest_or_owner_readback(field):
    args = evidence()
    del args[4]["cases"][1]["native_files"][1][field]
    with pytest.raises(gate.Days36EvidenceError, match="day6"):
        validate(args)


def test_day6_rejects_reused_private_object_key_across_language_cases():
    args = evidence()
    files = [row["native_files"] for row in args[4]["cases"]]
    files[2][1]["storage_object_ref"] = files[0][0]["storage_object_ref"]
    with pytest.raises(gate.Days36EvidenceError, match="day6"):
        validate(args)


@pytest.mark.parametrize(("field", "invalid"), [
    ("artifacts_after", []),
    ("artifacts_after", [
        {"artifact_id": "research-bn-docx", "sha256": D5},
        {"artifact_id": "research-bn-docx", "sha256": D5},
    ]),
    ("artifacts_after", [
        {"artifact_id": "research-bn-docx", "sha256": D5},
        {"artifact_id": "research-bn-pdf", "sha256": D4},
    ]),
    ("artifacts_after", [
        {"artifact_id": "research-bn-docx", "sha256": D5},
        {"artifact_id": "report_email-bn-pdf", "sha256": D5},
    ]),
    ("artifacts_before", [
        {"artifact_id": "report_email-bn-docx", "sha256": D5},
    ]),
    ("artifacts_before", [
        {"artifact_id": "research-bn-docx", "sha256": D4},
    ]),
    ("run_agent_effects_before", 0),
    ("run_agent_effects_after", 2),
    ("run_outbox_effects_before", 2),
    ("run_outbox_effects_after", 0),
    ("before_snapshot_at", "2026-11-18T05:50:00Z"),
    ("after_snapshot_at", "2026-11-18T06:15:00Z"),
    ("before_snapshot_receipt_ref", ""),
    ("after_snapshot_receipt_ref", ""),
])
def test_day6_rejects_recovery_that_loses_or_mutates_artifacts_or_effect_identity(field, invalid):
    args = evidence()
    args[4]["reconnect"][field] = invalid
    with pytest.raises(gate.Days36EvidenceError, match="day6"):
        validate(args)


@pytest.mark.parametrize("field", [
    "artifacts_before", "artifacts_after",
    "run_agent_effects_before", "run_agent_effects_after",
    "run_outbox_effects_before", "run_outbox_effects_after",
    "before_snapshot_at", "after_snapshot_at",
    "before_snapshot_receipt_ref", "after_snapshot_receipt_ref",
])
def test_day6_requires_operated_pre_post_recovery_readback(field):
    args = evidence()
    del args[4]["reconnect"][field]
    with pytest.raises(gate.Days36EvidenceError, match="day6"):
        validate(args)


def test_day6_can_have_no_artifacts_before_worker_restart_but_exact_expected_set_after():
    args = evidence()
    args[4]["reconnect"]["artifacts_before"] = []
    assert validate(args)["status"] == "evidence_internally_consistent_not_live_attested"


@pytest.mark.parametrize(("arm_index", "field", "bad_value"), [
    (1, "admitted_preview_digest_sha256", D3),
    (2, "preview_digest_sha256", D3),
    (0, "preview_digest_sha256", "invalid-sha"),
    (1, "admitted_preview_digest_sha256", ""),
    (1, "provider_started_at", "2026-11-18T03:39:00Z"),
    (1, "provider_finished_at", "2026-11-18T03:41:00Z"),
    (2, "provider_started_at", "2026-11-18T03:39:00Z"),
    (2, "provider_finished_at", "2026-11-18T03:47:00Z"),
])
def test_day5_rejects_stale_memory_preview_and_nonchronological_model_runs(
    arm_index, field, bad_value
):
    args = evidence()
    args[3]["arms"][arm_index][field] = bad_value
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


def test_day5_requires_distinct_canonical_preview_digests_across_all_three_arms():
    args = evidence()
    args[3]["arms"][2]["preview_digest_sha256"] = args[3]["arms"][1]["preview_digest_sha256"]
    args[3]["arms"][2]["admitted_preview_digest_sha256"] = args[3]["arms"][1]["preview_digest_sha256"]
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize(("owner", "field", "bad_value"), [
    ("owner_a", "own_context_id", "run-owner-B"),
    ("owner_b", "own_context_id", "run-v1"),
    ("owner_a", "own_output_id", "private-output-B"),
    ("owner_b", "own_output_sha256", ""),
    ("owner_a", "own_output_sha256", D5),
    ("owner_b", "own_context_http_status", 404),
    ("owner_a", "own_output_http_status", 403),
    ("owner_a", "own_context_read_receipt_ref", ""),
    ("owner_b", "own_output_read_receipt_ref", ""),
    ("owner_a", "foreign_fact_target_id", "fact-A"),
    ("owner_a", "foreign_fact_target_id", "unrelated-fact"),
    ("owner_b", "foreign_fact_target_id", "fact-B"),
    ("owner_a", "foreign_context_target_id", "run-v1"),
    ("owner_b", "foreign_context_target_id", "nonexistent-run"),
    ("owner_a", "foreign_output_target_id", "private-output-A"),
    ("owner_b", "foreign_output_target_id", "nonexistent-output"),
    ("owner_a", "foreign_fact_owner_ref", "synthetic-A"),
    ("owner_b", "foreign_context_owner_ref", "synthetic-B"),
    ("owner_a", "foreign_output_owner_ref", "synthetic-A"),
])
def test_day5_denied_target_must_really_belong_to_the_other_positive_owner(
    owner, field, bad_value
):
    args = evidence()
    args[3]["owner_access"][owner][field] = bad_value
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize(("owner", "field"), [
    ("owner_a", "own_context_id"),
    ("owner_b", "own_output_id"),
    ("owner_a", "own_context_http_status"),
    ("owner_b", "own_output_http_status"),
    ("owner_a", "own_context_read_receipt_ref"),
    ("owner_b", "own_output_read_receipt_ref"),
    ("owner_a", "foreign_fact_target_id"),
    ("owner_b", "foreign_context_target_id"),
    ("owner_a", "foreign_output_target_id"),
    ("owner_b", "foreign_fact_owner_ref"),
    ("owner_a", "foreign_context_owner_ref"),
    ("owner_b", "foreign_output_owner_ref"),
])
def test_day5_missing_owned_positive_or_cross_owner_denial_target_fails(owner, field):
    args = evidence()
    del args[3]["owner_access"][owner][field]
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize(("field", "bad_value"), [
    ("owner_ref", "synthetic-B"),
    ("fact_id", "unselected-same-category"),
    ("original_version", 2),
    ("original_version", True),
    ("corrected_version", 3),
    ("corrected_version", False),
    ("run_id", "run-v1"),
    ("provider_request_id", "model-request-v2"),
    ("provider_started_at", "2026-11-18T03:41:00Z"),
    ("corrected_at", "2026-11-18T03:36:00Z"),
    ("provider_finished_at", "2026-11-18T03:39:00Z"),
    ("commit_attempted_at", "2026-11-18T03:39:00Z"),
    ("rejection_verified_at", "2026-11-18T04:30:00Z"),
    ("commit_error_code", "timeout"),
    ("new_decisions_committed", 1),
    ("new_tool_invocations", 1),
    ("new_outbox_effects", 1),
    ("provider_receipt_ref", ""),
    ("memory_update_receipt_ref", ""),
    ("decision_commit_denial_ref", ""),
    ("decision_store_readback_ref", ""),
])
def test_day5_rejects_unbound_or_unproven_inflight_stale_decision_commit(field, bad_value):
    args = evidence()
    args[3]["inflight_correction"][field] = bad_value
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize("field", [
    "owner_ref", "fact_id", "original_version", "corrected_version",
    "run_id", "provider_request_id", "provider_started_at", "corrected_at",
    "provider_finished_at", "commit_attempted_at", "rejection_verified_at",
    "commit_error_code", "new_decisions_committed", "new_tool_invocations",
    "new_outbox_effects", "provider_receipt_ref", "memory_update_receipt_ref",
    "decision_commit_denial_ref", "decision_store_readback_ref",
])
def test_day5_missing_inflight_mutation_or_commit_receipt_fails(field):
    args = evidence()
    del args[3]["inflight_correction"][field]
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


def test_day5_must_observe_a_real_inflight_update_and_rejection():
    args = evidence()
    del args[3]["inflight_correction"]
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize(("field", "bad_value"), [
    ("replayed_at", "2026-11-18T03:39:00Z"),
    ("replayed_at", "2026-11-18T04:30:00Z"),
    ("new_decisions_committed", 1),
    ("decision_receipt_ref", ""),
])
def test_day5_historical_v1_replay_must_follow_correction_without_new_decision(field, bad_value):
    args = evidence()
    args[3]["historical_replay"][field] = bad_value
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


def test_day5_valid_reciprocal_targets_and_stale_decision_receipt_stay_structural_only():
    args = evidence()
    assert args[3]["owner_access"]["owner_a"]["foreign_fact_target_id"] == "fact-B"
    assert args[3]["owner_access"]["owner_b"]["foreign_fact_target_id"] == "fact-A"
    assert validate(args)["status"] == "evidence_internally_consistent_not_live_attested"


def test_day5_owner_a_context_cannot_claim_isolation_from_an_empty_memory_arm():
    args = evidence()
    owner_a = args[3]["owner_access"]["owner_a"]
    owner_a["own_context_id"] = "run-none"
    owner_a["own_output_sha256"] = D3
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize("bad_pins", [
    [],
    [{"fact_id": "fact-A", "version": 2}],
    [{"fact_id": "fact-B", "version": 1}],
    [{"fact_id": "fact-A", "version": True}],
    [{"fact_id": "fact-A", "version": 1}, {"fact_id": "fact-B", "version": 1}],
    [{"fact_id": "fact-A", "version": 1, "owner_ref": "synthetic-B"}],
    None,
])
def test_day5_inflight_provider_must_have_exact_old_selected_memory_in_its_context(bad_pins):
    args = evidence()
    args[3]["inflight_correction"]["worker_selected_memory"] = bad_pins
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


@pytest.mark.parametrize("field", ["worker_selected_memory", "worker_context_receipt_ref"])
def test_day5_missing_old_worker_memory_pin_witness_denies_inflight_acceptance(field):
    args = evidence()
    del args[3]["inflight_correction"][field]
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)


def test_day5_inflight_old_worker_context_requires_private_receipt():
    args = evidence()
    args[3]["inflight_correction"]["worker_context_receipt_ref"] = ""
    with pytest.raises(gate.Days36EvidenceError, match="day5"):
        validate(args)
