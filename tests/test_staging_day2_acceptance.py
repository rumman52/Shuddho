from __future__ import annotations

import copy

import pytest

from scripts import staging_day2_acceptance as gate

SHA = 'a' * 40
SHA_OTHER = 'b' * 40
DIGEST = 'c' * 64


def proofs():
    freeze = {'status': 'frozen', 'release': {'release_id': 'day2-001', 'source_revision': SHA, 'environment': 'staging'}, 'runtime_manifest_sha256': DIGEST}
    run = {
        'status': 'passed', 'release_id': 'day2-001', 'source_revision': SHA,
        'runtime_manifest_sha256': DIGEST,
        'document_id': 'doc-a', 'document_version_id': 'ver-a', 'document_sha256': '1' * 64,
        'task_id': 'task-a', 'workflow_id': 'shuddho-task-task-a',
        'artifact_id': 'artifact-a', 'artifact_sha256': '2' * 64, 'artifact_bytes': 220,
        'model_attempts': 1, 'accounted_tokens': 62,
        'owner_isolation': 'passed', 'artifact_retrieval': 'passed',
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
    restore['backup_restore'] = {'status': 'passed', 'release_id': 'day2-001', 'source_revision': SHA,
                                 'rollout_manifest_sha256': '3' * 64,
                                 'exercise_started_at': '2026-11-12T11:06:00+00:00',
                                 'verified_at': '2026-11-12T11:10:00+00:00',
                                 'evidence': 'isolated-backup-and-restore-event-refs'}
    return freeze, run, recovery, restore


def check(*proof_set):
    return gate.validate_evidence(*proof_set, expected_revision=SHA)


def test_valid_proofs_are_consistent_without_claiming_platform_verification():
    proof_set = proofs()
    result = check(*proof_set)
    assert result['status'] == 'evidence_consistent'
    assert result['source_revision'] == SHA
    assert result['task_id'] == 'task-a'
    assert result['artifact_sha256'] == '2' * 64
    assert result['required_live_checks'] == ['model', 'owner_isolation', 'artifact_retrieval', 'temporal', 'worker_heartbeat', 'parallel_restart', 'fan_in', 'backup_restore']


@pytest.mark.parametrize('target, field, value', [
    (0, 'status', 'prepared'),
    (0, 'runtime_manifest_sha256', '0' * 64),
    (1, 'source_revision', SHA_OTHER),
    (1, 'owner_isolation', 'failed'),
    (1, 'artifact_retrieval', 'failed'),
    (1, 'model_attempts', 0),
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
