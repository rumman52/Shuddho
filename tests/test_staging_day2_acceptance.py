from __future__ import annotations

import copy

import pytest

from scripts import staging_day2_acceptance as gate

SHA = 'a' * 40
SHA_OTHER = 'b' * 40
DIGEST = 'c' * 64


def proofs():
    freeze = {
        'status': 'frozen', 'runtime_manifest_sha256': DIGEST,
        'prepared_at': '2026-11-12T10:45:00+00:00',
        'release': {'release_id': 'day2-001', 'source_revision': SHA,
                    'environment': 'staging', 'rollout_manifest_sha256': '3' * 64,
                    'provider_policy_sha256': 'e' * 64,
                    'build_reference': 'sha256:immutable-staging-api-worker-build',
                    'deployment_reference': 'render-staging-change-ticket-123'},
    }
    run = {
        'status': 'passed', 'release_id': 'day2-001', 'source_revision': SHA,
        'runtime_manifest_sha256': DIGEST,
        'document_id': 'doc-a', 'document_version_id': 'ver-a', 'document_sha256': '1' * 64,
        'task_id': 'task-a', 'workflow_id': 'shuddho-task-task-a',
        'artifact_id': 'artifact-a', 'artifact_sha256': '2' * 64, 'artifact_bytes': 220,
        'model_attempts': 1, 'accounted_tokens': 62,
        'owner_isolation': {
            'schema_version': 1,
            'status': 'passed',
            'identities_distinct': True,
            'identity_claims': {
                'owner_a': {
                    'issuer_verified': True, 'audience_verified': True,
                    'expiry_verified': True, 'subject_verified': True,
                    'api_subject_binding_verified': True,
                },
                'owner_b': {
                    'issuer_verified': True, 'audience_verified': True,
                    'expiry_verified': True, 'subject_verified': True,
                    'api_subject_binding_verified': True,
                },
                'subjects_distinct': True,
            },
            'owners': {
                'a': {
                    'document_id': 'doc-a', 'document_sha256': '1' * 64, 'document_bytes': 180,
                    'document_read': 'passed',
                    'own_document_list': 'included', 'foreign_document_read': 'denied_404',
                    'foreign_document_write': 'denied_404', 'foreign_document_list': 'excluded',
                    'artifact_id': 'artifact-a', 'artifact_sha256': '2' * 64, 'artifact_bytes': 220,
                    'artifact_content_read': 'passed',
                    'artifact_download': 'passed', 'own_artifact_list': 'included',
                    'foreign_artifact_content': 'denied_404',
                    'foreign_artifact_download': 'denied_404', 'foreign_artifact_list': 'excluded',
                },
                'b': {
                    'document_id': 'doc-b', 'document_sha256': '4' * 64, 'document_bytes': 128,
                    'document_read': 'passed',
                    'own_document_list': 'included', 'foreign_document_read': 'denied_404',
                    'foreign_document_write': 'denied_404', 'foreign_document_list': 'excluded',
                    'artifact_id': 'artifact-b', 'artifact_sha256': '5' * 64, 'artifact_bytes': 96,
                    'artifact_content_read': 'passed',
                    'artifact_download': 'passed', 'own_artifact_list': 'included',
                    'foreign_artifact_content': 'denied_404',
                    'foreign_artifact_download': 'denied_404', 'foreign_artifact_list': 'excluded',
                },
            },
        }, 'artifact_retrieval': 'passed',
        'content_anchor_verification': 'passed',
        'document_outbox': {'task_id': 'task-a', 'effect_count': 1,
                            'delivered': True, 'dispatch_attempts': 1},
        'worker': {'id': 'worker-a', 'task_queue': 'staging-temporal', 'source_revision': SHA,
                   'heartbeat_before': '2026-11-12T11:00:00+00:00',
                   'heartbeat_after': '2026-11-12T11:01:00+00:00'},
    }
    recovery = copy.deepcopy(run)
    restore = copy.deepcopy(run)
    for label in ('temporal', 'parallel_restart', 'fan_in'):
        recovery[label] = {'status': 'passed', 'release_id': 'day2-001', 'source_revision': SHA,
                           'rollout_manifest_sha256': '3' * 64,
                           'exercise_started_at': '2026-11-12T11:01:01+00:00',
                           'verified_at': '2026-11-12T11:05:00+00:00',
                           'evidence': 'real-worker-event-ref'}
        restore[label] = copy.deepcopy(recovery[label])
    recovery['recovery_outbox'] = {
        'agent_run_id': 'agent-run-1', 'workflow_id': 'shuddho-agent-agent-run-1',
        'source_revision': SHA,
        'agent_outbox_effect_count': 1, 'agent_outbox_delivered': True,
        'child_task_outbox_count': 0, 'child_task_outbox_expected_absent': True,
        'completed_children': [
            {'ordinal': 1, 'task_id': 'child-1', 'state': 'completed',
             'idempotency_key': 'agent:agent-run-1:1',
             'started_at': '2026-11-12T11:02:00+00:00',
             'finished_at': '2026-11-12T11:03:20+00:00'},
            {'ordinal': 2, 'task_id': 'child-2', 'state': 'completed',
             'idempotency_key': 'agent:agent-run-1:2',
             'started_at': '2026-11-12T11:02:10+00:00',
             'finished_at': '2026-11-12T11:03:25+00:00'},
            {'ordinal': 3, 'task_id': 'child-3', 'state': 'completed',
             'idempotency_key': 'agent:agent-run-1:3',
             'started_at': '2026-11-12T11:03:30+00:00',
             'finished_at': '2026-11-12T11:04:00+00:00'},
        ],
        'worker_before_id': 'before-restart', 'worker_after_id': 'after-restart',
        'worker_before_heartbeat_at': '2026-11-12T11:02:55+00:00',
        'worker_after_heartbeat_at': '2026-11-12T11:03:06+00:00',
        'worker_after_started_at': '2026-11-12T11:03:05+00:00',
        'run_started_at': '2026-11-12T11:02:00+00:00',
        'run_finished_at': '2026-11-12T11:04:00+00:00',
        'restart_at': '2026-11-12T11:03:00+00:00',
        'restart_reference': 'actual-platform-event-123',
    }
    restore['recovery_outbox'] = copy.deepcopy(recovery['recovery_outbox'])
    restore['archive_integrity'] = {
        'status': 'verified', 'source_schema_revision': '0070',
        'postgres_archive_sha256': '6' * 64, 'postgres_schema_sha256': 'd' * 64,
        'postgres_table_count': 84,
        'postgres_row_count': 1,
        'source_database_fingerprint': '7' * 64,
        'target_database_fingerprint': '8' * 64,
        'object_manifest_sha256': '9' * 64, 'object_count': 2,
        'object_total_bytes': 1024,
        'source_storage_fingerprint': 'a' * 64,
        'target_storage_fingerprint': 'b' * 64,
        'probe_object_verified': True,
        'probe_object_sha256': 'c' * 64,
        'probe_object_bytes': 42,
        'restored_api_access': {
            'status': 'verified',
            'runtime_source_revision': SHA,
            'source_api_origin_sha256': '1' * 64,
            'restored_api_origin_sha256': '2' * 64,
            'owner_a_document_sha256': 'c' * 64,
            'owner_a_document_bytes': 42,
            'owner_a_document_retrievable': True,
            'owner_b_document_denied': True,
            'owner_b_document_unlisted': True,
            'owner_a_cancelled_task_verified': True,
            'owner_b_task_denied': True,
            'owner_a_identity_verified': True,
            'owner_b_identity_verified': True,
        },
        'preseed_baseline': {
            'status': 'preseed_verified',
            'attested_at': '2026-11-12T10:00:00+00:00',
            'source_schema_revision': '0070',
            'postgres_schema_sha256': 'd' * 64,
            'postgres_archive_sha256': 'e' * 64,
            'object_manifest_sha256': 'f' * 64,
            'source_database_fingerprint': '7' * 64,
            'source_storage_fingerprint': 'a' * 64,
            'postgres_table_count': 84,
            'postgres_row_count': 1,
            'object_count': 0,
            'object_total_bytes': 0,
        },
    }
    restore['backup_restore'] = {'status': 'passed', 'release_id': 'day2-001', 'source_revision': SHA,
                                 'rollout_manifest_sha256': '3' * 64,
                                 'exercise_started_at': '2026-11-12T11:06:00+00:00',
                                 'verified_at': '2026-11-12T11:10:00+00:00',
                                 'evidence': 'isolated-backup-and-restore-event-refs'}
    return freeze, run, recovery, restore


def check(*proof_set):
    return gate.validate_evidence(
        *proof_set, expected_revision=SHA, authorization=authorization_receipt(),
    )


def test_valid_proofs_are_consistent_without_claiming_platform_verification():
    proof_set = proofs()
    result = check(*proof_set)
    assert result['status'] == 'evidence_consistent'
    assert result['source_revision'] == SHA
    assert proof_set[3]['archive_integrity']['postgres_schema_sha256'] == 'd' * 64
    assert result['rollout_manifest_sha256'] == proof_set[0]['release']['rollout_manifest_sha256']
    assert result['task_id'] == 'task-a'
    assert result['artifact_sha256'] == '2' * 64
    assert result['owner_isolation']['owners']['b']['artifact_id'] == 'artifact-b'
    assert result['logical_agent_outbox_effect_count'] == 1
    assert result['parent_agent_outbox_delivered'] is True
    assert result['completed_child_task_count'] == 3
    assert result['logical_document_outbox_effect_count'] == 1
    assert result['recovered_agent_workflow_id'] == 'shuddho-agent-agent-run-1'
    assert result['required_live_checks'] == ['model', 'owner_isolation', 'artifact_retrieval', 'temporal', 'document_outbox', 'worker_heartbeat', 'parallel_restart', 'fan_in', 'outbox_once', 'worker_replaced', 'backup_restore', 'pdf_content_fidelity', 'founder_c_authorization']


@pytest.mark.parametrize('target, field, value', [
    (0, 'status', 'prepared'),
    (0, 'runtime_manifest_sha256', '0' * 64),
    (1, 'source_revision', SHA_OTHER),
    (1, 'owner_isolation', 'failed'),
    (1, 'artifact_retrieval', 'failed'),
    (1, 'model_attempts', 0),
    (1, 'document_outbox', None),
    (1, 'document_version_id', ''),
    (1, 'workflow_id', 'unrelated-agent-task'),
    (2, 'task_id', 'other-task'),
    (2, 'artifact_sha256', '8' * 64),
    (3, 'document_id', 'other-doc'),
    (3, 'artifact_id', 'other-artifact'),
])
def test_mismatched_or_missing_source_chain_is_rejected(target, field, value):
    proof_set = list(proofs())
    proof_set[target][field] = value
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)


@pytest.mark.parametrize('target, field, value', [
    (2, 'parallel_restart', None),
    (3, 'backup_restore', None),
])
def test_required_live_proofs_are_not_optional(target, field, value):
    proof_set = list(proofs())
    proof_set[target][field] = value
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)


def test_recovery_and_restore_must_share_same_release_and_evidence():
    proof_set = list(proofs())
    proof_set[3]['parallel_restart']['source_revision'] = SHA_OTHER
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)
    proof_set = list(proofs())
    proof_set[3]['backup_restore']['release_id'] = 'unrelated-release'
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)


def test_rejects_swapped_rollout_and_time_reversal():
    proof_set = list(proofs())
    proof_set[3]['backup_restore']['rollout_manifest_sha256'] = '4' * 64
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)
    proof_set = list(proofs())
    proof_set[3]['backup_restore']['verified_at'] = '2026-11-12T11:00:00+00:00'
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)
    proof_set = list(proofs())
    proof_set[1]['worker']['heartbeat_after'] = '2026-11-12T10:59:00+00:00'
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)


@pytest.mark.parametrize('change', ['missing', 'invalid', 'different'])
def test_rejects_recovery_and_restore_that_only_match_each_other(change):
    proof_set = proofs()
    release = proof_set[0]['release']
    if change == 'missing':
        del release['rollout_manifest_sha256']
    else:
        release['rollout_manifest_sha256'] = 'not-a-digest' if change == 'invalid' else '4' * 64
    with pytest.raises(gate.Day2AcceptanceFailure, match='rollout'):
        check(*proof_set)


def test_rejects_forged_worker_or_source_digest():
    proof_set = list(proofs())
    proof_set[1]['worker']['source_revision'] = SHA_OTHER
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)
    proof_set = list(proofs())
    proof_set[1]['document_sha256'] = 'not-a-digest'
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)
    proof_set = list(proofs())
    with pytest.raises(gate.Day2AcceptanceFailure):
        gate.validate_evidence(*proof_set, expected_revision=SHA_OTHER)


@pytest.mark.parametrize('field, invalid', [
    ('agent_run_id', ''),
    ('workflow_id', 'other-workflow'),
    ('source_revision', SHA_OTHER),
    ('agent_outbox_effect_count', 0),
    ('agent_outbox_effect_count', True),
    ('agent_outbox_effect_count', 2),
    ('child_task_outbox_count', 1),
    ('child_task_outbox_expected_absent', False),
    ('worker_after_id', 'before-restart'),
    ('worker_after_started_at', '2026-11-12T11:01:00+00:00'),
    ('worker_after_started_at', '2026-11-12T11:02:59+00:00'),
    ('worker_after_started_at', '2026-11-12T11:04:01+00:00'),
    ('restart_at', '2026-11-12T11:04:01+00:00'),
    ('restart_reference', ''),
])
def test_rejects_fake_outbox_or_missing_active_replacement(field, invalid):
    proof_set = list(proofs())
    proof_set[2]['recovery_outbox'][field] = invalid
    proof_set[3]['recovery_outbox'][field] = invalid
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)


def test_rejects_replaced_restore_receipt_or_absent_recovery_proof():
    proof_set = list(proofs())
    proof_set[3]['recovery_outbox']['worker_after_id'] = 'forged'
    with pytest.raises(gate.Day2AcceptanceFailure, match='carry forward'):
        check(*proof_set)
    proof_set = list(proofs())
    del proof_set[2]['recovery_outbox']
    del proof_set[3]['recovery_outbox']
    with pytest.raises(gate.Day2AcceptanceFailure, match='recovery_outbox'):
        check(*proof_set)


@pytest.mark.parametrize('field, invalid', [
    ('task_id', 'other-task'),
    ('effect_count', 0),
    ('effect_count', 2),
    ('effect_count', True),
    ('delivered', False),
    ('dispatch_attempts', 0),
])
def test_pdf_task_requires_exactly_one_delivered_persisted_outbox(field, invalid):
    proof_set = list(proofs())
    proof_set[1]['document_outbox'][field] = invalid
    proof_set[2]['document_outbox'][field] = invalid
    proof_set[3]['document_outbox'][field] = invalid
    with pytest.raises(gate.Day2AcceptanceFailure, match='outbox'):
        check(*proof_set)



@pytest.mark.parametrize('owner, field, invalid', [
    ('a', 'foreign_document_read', 'passed'),
    ('b', 'foreign_document_read', 'passed'),
    ('a', 'foreign_document_write', 'passed'),
    ('b', 'foreign_document_write', 'passed'),
    ('a', 'foreign_document_list', 'included'),
    ('b', 'foreign_document_list', 'included'),
    ('a', 'foreign_artifact_content', 'passed'),
    ('b', 'foreign_artifact_content', 'passed'),
    ('a', 'foreign_artifact_download', 'passed'),
    ('b', 'foreign_artifact_download', 'passed'),
    ('a', 'foreign_artifact_list', 'included'),
    ('b', 'foreign_artifact_list', 'included'),
    ('a', 'document_read', 'denied_404'),
    ('b', 'document_read', 'denied_404'),
    ('a', 'artifact_content_read', 'denied_404'),
    ('b', 'artifact_download', 'denied_404'),
])
def test_acceptance_rejects_missing_or_leaky_bidirectional_owner_proof(owner, field, invalid):
    proof_set = list(proofs())
    proof_set[1]['owner_isolation']['owners'][owner][field] = invalid
    with pytest.raises(gate.Day2AcceptanceFailure, match='owner|isolation'):
        check(*proof_set)


@pytest.mark.parametrize('owner, field, invalid', [
    ('b', 'document_id', 'doc-a'),
    ('b', 'artifact_id', 'artifact-a'),
    ('a', 'document_id', 'wrong-primary-document'),
    ('a', 'artifact_id', 'wrong-primary-artifact'),
])
def test_acceptance_rejects_duplicate_or_mismatched_owner_resource_ids(owner, field, invalid):
    proof_set = list(proofs())
    proof_set[1]['owner_isolation']['owners'][owner][field] = invalid
    with pytest.raises(gate.Day2AcceptanceFailure, match='owner|isolation'):
        check(*proof_set)


def test_acceptance_rejects_missing_owner_direction_or_identity():
    proof_set = list(proofs())
    del proof_set[1]['owner_isolation']['owners']['b']
    with pytest.raises(gate.Day2AcceptanceFailure, match='owner|isolation'):
        check(*proof_set)
    proof_set = list(proofs())
    proof_set[1]['owner_isolation']['identities_distinct'] = False
    with pytest.raises(gate.Day2AcceptanceFailure, match='owner|isolation'):
        check(*proof_set)


@pytest.mark.parametrize('owner, field, invalid', [
    ('a', 'document_sha256', 'not-a-digest'),
    ('b', 'artifact_sha256', 'not-a-digest'),
    ('a', 'document_bytes', 0),
    ('b', 'artifact_bytes', 0),
])
def test_acceptance_rejects_invalid_owner_resource_manifest(owner, field, invalid):
    proof_set = list(proofs())
    proof_set[1]['owner_isolation']['owners'][owner][field] = invalid
    with pytest.raises(gate.Day2AcceptanceFailure, match='owner|isolation'):
        check(*proof_set)


@pytest.mark.parametrize('owner, field', [
    ('owner_a', 'issuer_verified'),
    ('owner_a', 'audience_verified'),
    ('owner_a', 'expiry_verified'),
    ('owner_a', 'subject_verified'),
    ('owner_b', 'issuer_verified'),
    ('owner_b', 'audience_verified'),
    ('owner_b', 'expiry_verified'),
    ('owner_b', 'subject_verified'),
    ('owner_b', 'api_subject_binding_verified'),
])
def test_acceptance_rejects_unverified_owner_jwt_claim(owner, field):
    proof_set = list(proofs())
    proof_set[1]['owner_isolation']['identity_claims'][owner][field] = False
    with pytest.raises(gate.Day2AcceptanceFailure, match='identity|Managed'):
        check(*proof_set)


def test_acceptance_rejects_non_distinct_jwt_subjects():
    proof_set = list(proofs())
    proof_set[1]['owner_isolation']['identity_claims']['subjects_distinct'] = False
    with pytest.raises(gate.Day2AcceptanceFailure, match='subject'):
        check(*proof_set)


@pytest.mark.parametrize("value", [None, "unverified", "missing", False, True])
def test_day2_acceptance_rejects_missing_or_unverified_pdf_content_fidelity(value):
    proof_set = list(proofs())
    # Even internally consistent receipts cannot substitute for the actual
    # synthetic source marker observed in the model summary and report PDF.
    for evidence in proof_set[1:]:
        evidence["content_anchor_verification"] = value
    with pytest.raises(gate.Day2AcceptanceFailure, match="content fidelity"):
        check(*proof_set)


def test_day2_acceptance_rejects_report_fidelity_field_swapped_after_execution():
    proof_set = list(proofs())
    proof_set[2]["content_anchor_verification"] = "unverified"
    with pytest.raises(gate.Day2AcceptanceFailure, match="content_anchor_verification"):
        check(*proof_set)


@pytest.mark.parametrize("field, invalid", [
    ("agent_outbox_delivered", False),
    ("agent_outbox_delivered", None),
    ("worker_before_heartbeat_at", "2026-11-12T11:03:01+00:00"),
    ("worker_after_heartbeat_at", "2026-11-12T11:03:05+00:00"),
    ("completed_children", []),
    ("completed_children", None),
])
def test_recovery_requires_parent_delivery_child_receipts_and_worker_heartbeats(field, invalid):
    proof_set = list(proofs())
    proof_set[2]["recovery_outbox"][field] = invalid
    proof_set[3]["recovery_outbox"][field] = invalid
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)


@pytest.mark.parametrize("ordinal, field, invalid", [
    (0, "task_id", "child-2"),
    (0, "state", "failed"),
    (0, "ordinal", True),
    (1, "ordinal", 1),
    (1, "idempotency_key", "agent:unrelated:2"),
    (0, "started_at", "2026-11-12T11:01:59+00:00"),
    (2, "finished_at", "2026-11-12T11:04:01+00:00"),
    (2, "started_at", "2026-11-12T11:03:19+00:00"),
])
def test_recovery_rejects_forged_or_non_completed_child_receipt(ordinal, field, invalid):
    proof_set = list(proofs())
    for receipt in proof_set[2:]:
        receipt["recovery_outbox"]["completed_children"][ordinal][field] = invalid
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)


def test_recovery_rejects_restart_while_no_child_was_active():
    proof_set = list(proofs())
    for receipt in proof_set[2:]:
        children = receipt["recovery_outbox"]["completed_children"]
        children[0]["finished_at"] = "2026-11-12T11:02:59+00:00"
        children[1]["finished_at"] = "2026-11-12T11:02:59+00:00"
    with pytest.raises(gate.Day2AcceptanceFailure, match="active child task"):
        check(*proof_set)


@pytest.mark.parametrize("field, bad_value", [
    ("status", "unverified"),
    ("probe_object_verified", False),
    ("postgres_archive_sha256", "unsigned"),
    ("postgres_table_count", 83),
    ("postgres_row_count", 0),
    ("object_manifest_sha256", ""),
    ("object_count", 0),
    ("object_total_bytes", 0),
    ("source_database_fingerprint", "8" * 64),
    ("target_storage_fingerprint", "a" * 64),
    ("source_schema_revision", ""),
])
def test_backup_gate_rejects_missing_or_inconsistent_full_archive_evidence(field, bad_value):
    proof_set = list(proofs())
    proof_set[3]["archive_integrity"][field] = bad_value
    with pytest.raises(gate.Day2AcceptanceFailure):
        check(*proof_set)


def test_backup_gate_rejects_legacy_reference_only_restore_receipt():
    proof_set = list(proofs())
    proof_set[3].pop("archive_integrity")
    with pytest.raises(gate.Day2AcceptanceFailure, match="archive_integrity"):
        check(*proof_set)


@pytest.mark.parametrize("invalid_digest", [None, "", "INVALID", 123])
def test_day2_gate_requires_structural_schema_digest(invalid_digest):
    proof_set = list(proofs())
    if invalid_digest is None:
        del proof_set[3]["archive_integrity"]["postgres_schema_sha256"]
    else:
        proof_set[3]["archive_integrity"]["postgres_schema_sha256"] = invalid_digest
    with pytest.raises(gate.Day2AcceptanceFailure, match="postgres_schema_sha256"):
        check(*proof_set)


@pytest.mark.parametrize("field,invalid", [
    ("status", "verified"),
    ("source_database_fingerprint", "8" * 64),
    ("source_storage_fingerprint", "b" * 64),
    ("object_count", 1),
    ("object_total_bytes", 1),
    ("source_schema_revision", "0072_merge_0071_heads"),
    ("postgres_archive_sha256", ""),
    ("postgres_table_count", 83),
    ("attested_at", "2099-01-01T00:00:00+00:00"),
    ("attested_at", "unqualified"),
])
def test_day2_original_state_baseline_is_mandatory_and_separate_from_task_restore(field, invalid):
    proof_set = list(proofs())
    proof_set[3]["archive_integrity"]["preseed_baseline"][field] = invalid
    with pytest.raises(gate.Day2AcceptanceFailure, match="preseed_baseline"):
        check(*proof_set)


def test_day2_rejects_legacy_restore_without_original_state_baseline():
    proof_set = list(proofs())
    del proof_set[3]["archive_integrity"]["preseed_baseline"]
    with pytest.raises(gate.Day2AcceptanceFailure, match="preseed_baseline"):
        check(*proof_set)


@pytest.mark.parametrize("field,invalid", [
    ("status", "unverified"),
    ("runtime_source_revision", "f" * 40),
    ("owner_a_document_sha256", "f" * 64),
    ("owner_a_document_bytes", 43),
    ("owner_a_document_retrievable", False),
    ("owner_b_document_denied", False),
    ("owner_b_document_unlisted", False),
    ("owner_a_cancelled_task_verified", False),
    ("owner_b_task_denied", False),
    ("owner_a_identity_verified", False),
    ("owner_b_identity_verified", False),
    ("restored_api_origin_sha256", "1" * 64),
])
def test_restored_api_access_is_mandatory_after_database_object_restore(field, invalid):
    proof_set = list(proofs())
    proof_set[3]["archive_integrity"]["restored_api_access"][field] = invalid
    with pytest.raises(gate.Day2AcceptanceFailure, match="restored_api_access"):
        check(*proof_set)


def test_restored_api_access_cannot_be_omitted_from_final_day2_acceptance():
    proof_set = list(proofs())
    del proof_set[3]["archive_integrity"]["restored_api_access"]
    with pytest.raises(gate.Day2AcceptanceFailure, match="restored_api_access"):
        check(*proof_set)


def authorization_receipt():
    """Synthetic operator decisions; NOT independent authorization evidence."""
    return {
        'schema_version': 1, 'status': 'operator_recorded',
        'environment': 'staging', 'release_id': 'day2-001',
        'source_revision': SHA, 'rollout_manifest_sha256': '3' * 64,
        'provider_policy_sha256': 'e' * 64,
        'build_reference': 'sha256:immutable-staging-api-worker-build',
        'deployment_reference': 'render-staging-change-ticket-123',
        'hosting': {
            'provider': 'Render', 'workspace_reference': 'rumman-staging-team',
            'api_service_reference': 'srv-staging-api',
            'worker_service_reference': 'srv-staging-worker',
            'worker_region': 'oregon',
            'worker_plan': '0.5c-512mb',
        },
        'budget': {
            'currency': 'USD', 'max_spend_minor_units': 2500,
            'maximum_duration_minutes': 180, 'max_provider_attempts': 3,
        },
        'isolated_restore': {
            'database_fingerprint': '8' * 64,
            'storage_fingerprint': 'b' * 64,
            'api_origin_sha256': '2' * 64,
        },
        'rollback': {
            'owner_reference': 'approved-operator-c-rollback',
            'procedure_reference': 'controlled-staging-rollback-12',
        },
        'approvals': {
            'founder': {
                'decision': 'approved',
                'approved_at': '2026-11-12T09:00:00+00:00',
                'reference': 'dated-founder-decision-record-A',
            },
            'operator_c': {
                'decision': 'approved',
                'approved_at': '2026-11-12T09:05:00+00:00',
                'reference': 'dated-operator-c-decision-record-B',
            },
        },
        'valid_from': '2026-11-12T09:30:00+00:00',
        'valid_until': '2026-11-12T12:00:00+00:00',
    }


def test_day2_acceptance_rejects_missing_founder_c_approval():
    """Original Part 02 D02.T05/G05: no authorization means no consistency receipt."""
    with pytest.raises(gate.Day2AcceptanceFailure, match='authorization|Founder|approval'):
        gate.validate_evidence(*proofs(), expected_revision=SHA)


def test_day2_acceptance_reconciles_protected_operator_approval_without_claiming_live_authority():
    freeze, run, recovery, restored = proofs()
    freeze['prepared_at'] = '2026-11-12T10:45:00+00:00'
    freeze['release']['build_reference'] = authorization_receipt()['build_reference']
    freeze['release']['deployment_reference'] = authorization_receipt()['deployment_reference']
    freeze['release']['provider_policy_sha256'] = authorization_receipt()['provider_policy_sha256']
    result = gate.validate_evidence(
        freeze, run, recovery, restored, expected_revision=SHA,
        authorization=authorization_receipt(),
    )
    assert result['status'] == 'evidence_consistent'
    assert result['authorization_evidence']['status'] == 'operator_recorded_requires_independent_review'
    assert len(result['authorization_evidence']['receipt_sha256']) == 64
    assert 'founder_c_authorization' in result['required_live_checks']
    assert 'dated-founder-decision-record-A' not in repr(result)
    assert 'dated-operator-c-decision-record-B' not in repr(result)


@pytest.mark.parametrize('path, bad', [
    (('schema_version',), True),
    (('status',), 'passed'),
    (('environment',), 'production'),
    (('release_id',), 'another-release'),
    (('source_revision',), SHA_OTHER),
    (('rollout_manifest_sha256',), 'f' * 64),
    (('provider_policy_sha256',), 'f' * 64),
    (('build_reference',), 'unrelated-image'),
    (('deployment_reference',), 'unrelated-deployment'),
    (('hosting', 'worker_service_reference'), 'srv-staging-api'),
    (('hosting', 'worker_service_reference'), ''),
    (('hosting', 'worker_region'), ''),
    (('hosting', 'worker_plan'), ''),
    (('budget', 'currency'), 'US'),
    (('budget', 'max_spend_minor_units'), 0),
    (('budget', 'max_spend_minor_units'), True),
    (('budget', 'max_provider_attempts'), 0),
    (('budget', 'maximum_duration_minutes'), 100),
    (('isolated_restore', 'database_fingerprint'), '7' * 64),
    (('isolated_restore', 'storage_fingerprint'), 'a' * 64),
    (('isolated_restore', 'api_origin_sha256'), '1' * 64),
    (('rollback', 'owner_reference'), ''),
    (('approvals', 'founder', 'decision'), 'pending'),
    (('approvals', 'founder', 'approved_at'), '2026-11-12T10:01:00+00:00'),
    (('approvals', 'founder', 'reference'), ''),
    (('approvals', 'founder', 'reference'), 'dated-operator-c-decision-record-B'),
    (('approvals', 'operator_c', 'approved_at'), '2026-11-12T12:30:00+00:00'),
    (('valid_from',), '2026-11-12T08:00:00+00:00'),
    (('valid_until',), '2026-11-12T11:09:59+00:00'),
])
def test_day2_acceptance_rejects_invalid_or_mixed_founder_c_authorization(path, bad):
    freeze, run, recovery, restored = proofs()
    freeze['prepared_at'] = '2026-11-12T10:45:00+00:00'
    freeze['release']['build_reference'] = authorization_receipt()['build_reference']
    freeze['release']['deployment_reference'] = authorization_receipt()['deployment_reference']
    freeze['release']['provider_policy_sha256'] = authorization_receipt()['provider_policy_sha256']
    receipt = authorization_receipt()
    entry = receipt
    for key in path[:-1]:
        entry = entry[key]
    entry[path[-1]] = bad
    with pytest.raises(gate.Day2AcceptanceFailure, match='authorization|Founder|approval'):
        gate.validate_evidence(freeze, run, recovery, restored,
                               expected_revision=SHA, authorization=receipt)


def test_day2_acceptance_rejects_provider_attempts_exceeding_approved_cap():
    freeze, run, recovery, restored = proofs()
    freeze['prepared_at'] = '2026-11-12T10:45:00+00:00'
    freeze['release'].update(
        build_reference=authorization_receipt()['build_reference'],
        deployment_reference=authorization_receipt()['deployment_reference'],
        provider_policy_sha256=authorization_receipt()['provider_policy_sha256'],
    )
    receipt = authorization_receipt()
    receipt['budget']['max_provider_attempts'] = 1
    run['model_attempts'] = 2
    recovery['model_attempts'] = 2
    restored['model_attempts'] = 2
    with pytest.raises(gate.Day2AcceptanceFailure, match='authorization|provider'):
        gate.validate_evidence(freeze, run, recovery, restored,
                               expected_revision=SHA, authorization=receipt)


def test_private_founder_c_authorization_file_must_be_mode_0600_and_not_a_symlink(tmp_path):
    import json
    import os

    from scripts.staging_day2_authorization import (
        AuthorizationEvidenceFailure, read_private_authorization,
    )

    source = tmp_path / 'founder-c-decision.json'
    source.write_text(json.dumps(authorization_receipt()))
    os.chmod(source, 0o600)
    assert read_private_authorization(source)['status'] == 'operator_recorded'
    os.chmod(source, 0o644)
    with pytest.raises(AuthorizationEvidenceFailure, match='0600'):
        read_private_authorization(source)
    os.chmod(source, 0o600)
    symlink = tmp_path / 'public-symlink.json'
    symlink.symlink_to(source)
    with pytest.raises(AuthorizationEvidenceFailure, match='symlink'):
        read_private_authorization(symlink)


def test_private_founder_c_authorization_file_rejects_duplicate_json_fields(tmp_path):
    import os

    from scripts.staging_day2_authorization import (
        AuthorizationEvidenceFailure, read_private_authorization,
    )

    source = tmp_path / 'duplicate-approval.json'
    source.write_text('{"status":"operator_recorded","status":"passed"}')
    os.chmod(source, 0o600)
    with pytest.raises(AuthorizationEvidenceFailure, match='duplicate'):
        read_private_authorization(source)


def test_private_approval_receipt_rejects_path_swapped_to_symlink_during_open(tmp_path, monkeypatch):
    """Protect against a credential/approval file swap after initial path checks."""
    import json
    import os

    from scripts.staging_day2_authorization import (
        AuthorizationEvidenceFailure, read_private_authorization,
    )

    current = tmp_path / 'approved-decision.json'
    foreign = tmp_path / 'untrusted-content.json'
    current.write_text(json.dumps(authorization_receipt()))
    foreign.write_text(json.dumps(authorization_receipt()))
    os.chmod(current, 0o600)
    os.chmod(foreign, 0o600)
    actual_open = os.open

    def swap_before_open(path, flags, *args, **kwargs):
        if str(path) == str(current):
            current.unlink()
            current.symlink_to(foreign)
        return actual_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', swap_before_open)
    with pytest.raises(AuthorizationEvidenceFailure, match='authorization'):
        read_private_authorization(current)


@pytest.mark.parametrize("field", ["worker_region", "worker_plan"])
def test_day2_final_authorization_rejects_missing_host_plan_or_region(field):
    freeze, run, recovery, restored = proofs()
    receipt = authorization_receipt()
    receipt["hosting"].pop(field)
    with pytest.raises(gate.Day2AcceptanceFailure, match="authorization"):
        gate.validate_evidence(
            freeze, run, recovery, restored,
            expected_revision=SHA, authorization=receipt,
        )
