"""A merged PR with failed/late checks or no review must never look qualified."""
import pytest

from scripts.v01_merge_evidence import EvidenceError, inspect_premerge_evidence

HEAD = 'a' * 40
MERGE = '2026-10-20T18:42:34Z'


def evidence(*, run_conclusion='success', gate='success', gate_end='2026-10-20T18:30:38Z', reviews=None):
    pr = {'number': 519, 'merged_at': MERGE, 'head': {'sha': HEAD, 'ref': 'feature-safe', 'repo': {'id': 17}}, 'base': {'repo': {'id': 34}}, 'user': {'login': 'proposing-author'}}
    run = {'head_sha': HEAD, 'head_branch': 'feature-safe', 'head_repository': {'id': 17}, 'repository': {'id': 34}, 'status': 'completed', 'conclusion': run_conclusion, 'event': 'pull_request'}
    jobs = [
        {'name': 'test-and-build', 'status': 'completed', 'conclusion': 'success', 'completed_at': '2026-10-20T18:05:33Z'},
        {'name': 'coworker', 'status': 'completed', 'conclusion': 'success', 'completed_at': '2026-10-20T18:30:27Z'},
        {'name': 'ci-merge-gate', 'status': 'completed', 'conclusion': gate, 'completed_at': gate_end},
    ]
    if reviews is None:
        reviews = [{'id': 1, 'state': 'APPROVED', 'commit_id': HEAD, 'submitted_at': '2026-10-20T18:20:00Z', 'author_association': 'COLLABORATOR', 'user': {'login': 'independent-person', 'type': 'User'}}]
    return pr, run, jobs, reviews


def test_reports_observed_519_incident_even_when_both_code_jobs_pass():
    pr, run, jobs, reviews = evidence(run_conclusion='failure', gate='failure', reviews=[])
    result = inspect_premerge_evidence(pr, run, jobs, reviews)
    assert result['classification'] == 'observed_governance_incident'
    assert 'ci-merge-gate:failure' in result['findings']
    assert 'no_independent_current_head_approval' in result['findings']
    assert 'native_policy_not_verified' in result['limitations']


def test_green_code_jobs_completed_after_merge_are_not_premerge_proof():
    pr, run, jobs, reviews = evidence(gate_end='2026-10-20T18:45:00Z')
    result = inspect_premerge_evidence(pr, run, jobs, reviews)
    assert 'ci-merge-gate:completed_after_merge' in result['findings']


def test_successful_premerge_checks_and_review_are_still_not_branch_protection_proof():
    result = inspect_premerge_evidence(*evidence())
    assert result['findings'] == []
    assert result['classification'] == 'no_incident_in_supplied_evidence'
    assert 'native_policy_not_verified' in result['limitations']


@pytest.mark.parametrize('mutation', [
    lambda p,r,j,v: r.update(head_sha='b'*40),
    lambda p,r,j,v: p.update(head={'sha': 'bad'}),
    lambda p,r,j,v: r.update(status='in_progress'),
    lambda p,r,j,v: j.pop(),
    lambda p,r,j,v: j[0].update(completed_at='garbage'),
    lambda p,r,j,v: j.append(dict(j[0])),
    lambda p,r,j,v: v.append({'state':'APPROVED'}),
])
def test_unusable_evidence_is_not_silently_accepted(mutation):
    parts = evidence()
    mutation(*parts)
    with pytest.raises(EvidenceError):
        inspect_premerge_evidence(*parts)


def test_author_approval_does_not_count():
    pr, run, jobs, reviews = evidence()
    pr['user'] = {'login': 'proposing-author'}
    reviews[0]['user']['login'] = 'proposing-author'
    result = inspect_premerge_evidence(pr, run, jobs, reviews)
    assert 'no_independent_current_head_approval' in result['findings']


def test_old_head_review_does_not_count():
    pr, run, jobs, reviews = evidence()
    reviews[0]['commit_id'] = 'b' * 40
    assert 'no_independent_current_head_approval' in inspect_premerge_evidence(pr, run, jobs, reviews)['findings']


def test_latest_review_dismissal_revokes_approval():
    pr, run, jobs, reviews = evidence()
    reviews.append({**reviews[0], 'id': 2, 'state': 'DISMISSED', 'submitted_at': '2026-10-20T18:25:00Z'})
    assert 'no_independent_current_head_approval' in inspect_premerge_evidence(pr, run, jobs, reviews)['findings']


def test_review_without_submitted_at_cannot_prove_premerge_approval():
    pr, run, jobs, reviews = evidence()
    reviews[0].pop('submitted_at')
    with pytest.raises(EvidenceError):
        inspect_premerge_evidence(pr, run, jobs, reviews)


def test_unrelated_workflow_event_is_not_premerge_evidence():
    pr, run, jobs, reviews = evidence()
    run['event'] = 'push'
    with pytest.raises(EvidenceError):
        inspect_premerge_evidence(pr, run, jobs, reviews)


@pytest.mark.parametrize('mutation', [
    lambda p,r,j,v: r.update(head_branch='unrelated-feature'),
    lambda p,r,j,v: r.update(head_repository={'id': 99}),
    lambda p,r,j,v: r.update(repository={'id': 99}),
    lambda p,r,j,v: r.pop('head_branch'),
    lambda p,r,j,v: r.pop('head_repository'),
    lambda p,r,j,v: r.pop('repository'),
    lambda p,r,j,v: p['head'].pop('ref'),
    lambda p,r,j,v: p['head'].pop('repo'),
    lambda p,r,j,v: p['base'].pop('repo'),
])
def test_rejects_workflow_evidence_from_a_different_pr_provenance(mutation):
    # A shared head SHA is insufficient proof of the branch or repository that ran CI.
    parts = evidence()
    mutation(*parts)
    with pytest.raises(EvidenceError):
        inspect_premerge_evidence(*parts)


def test_approval_submitted_after_ci_merge_gate_finished_is_not_gate_proof():
    pr, run, jobs, reviews = evidence()
    reviews[0]['submitted_at'] = '2026-10-20T18:35:00Z'
    result = inspect_premerge_evidence(pr, run, jobs, reviews)
    assert result['classification'] == 'observed_governance_incident'
    assert 'ci-merge-gate:completed_before_independent_approval' in result['findings']


def test_multiple_late_approvals_are_not_premature_gate_proof():
    pr, run, jobs, reviews = evidence()
    reviews[0]['submitted_at'] = '2026-10-20T18:35:00Z'
    reviews.append({**reviews[0], 'id': 2, 'user': {
        'login': 'different-maintainer', 'type': 'User'
    }, 'submitted_at': '2026-10-20T18:38:00Z'})
    assert 'ci-merge-gate:completed_before_independent_approval' in (
        inspect_premerge_evidence(pr, run, jobs, reviews)['findings']
    )


def test_pre_gate_approval_remains_valid_with_another_late_approval():
    pr, run, jobs, reviews = evidence()
    reviews.append({**reviews[0], 'id': 2, 'user': {
        'login': 'different-maintainer', 'type': 'User'
    }, 'submitted_at': '2026-10-20T18:35:00Z'})
    result = inspect_premerge_evidence(pr, run, jobs, reviews)
    assert result['classification'] == 'no_incident_in_supplied_evidence'
    assert 'ci-merge-gate:completed_before_independent_approval' not in result['findings']


def test_late_reapproval_does_not_retroactively_qualify_old_gate():
    pr, run, jobs, reviews = evidence()
    reviews.append({**reviews[0], 'id': 2, 'state': 'DISMISSED',
                    'submitted_at': '2026-10-20T18:25:00Z'})
    reviews.append({**reviews[0], 'id': 3,
                    'submitted_at': '2026-10-20T18:35:00Z'})
    result = inspect_premerge_evidence(pr, run, jobs, reviews)
    assert 'ci-merge-gate:completed_before_independent_approval' in result['findings']


def test_later_submitted_change_request_with_lower_id_revokes_approval():
    # Pending reviews may be created early (low ID) but submitted later.
    pr, run, jobs, reviews = evidence()
    reviews[0]['id'] = 50
    reviews.append({**reviews[0], 'id': 40, 'state': 'CHANGES_REQUESTED',
                    'submitted_at': '2026-10-20T18:25:00Z'})
    findings = inspect_premerge_evidence(pr, run, jobs, reviews)['findings']
    assert 'outstanding_independent_changes_requested' in findings
    assert 'no_independent_current_head_approval' in findings


def test_later_submitted_reapproval_with_lower_id_restores_pre_gate_approval():
    pr, run, jobs, reviews = evidence()
    reviews[0].update(id=50, state='CHANGES_REQUESTED',
                      submitted_at='2026-10-20T18:15:00Z')
    reviews.append({**reviews[0], 'id': 40, 'state': 'APPROVED',
                    'submitted_at': '2026-10-20T18:20:00Z'})
    assert inspect_premerge_evidence(pr, run, jobs, reviews)['findings'] == []


def test_later_submitted_old_head_approval_with_lower_id_invalidates_old_decision():
    pr, run, jobs, reviews = evidence()
    reviews[0]['id'] = 50
    reviews.append({**reviews[0], 'id': 40, 'commit_id': 'b' * 40,
                    'submitted_at': '2026-10-20T18:25:00Z'})
    assert 'no_independent_current_head_approval' in (
        inspect_premerge_evidence(pr, run, jobs, reviews)['findings']
    )


def test_same_instant_opposed_actionable_review_states_are_ambiguous():
    pr, run, jobs, reviews = evidence()
    reviews[0]['id'] = 50
    reviews.append({**reviews[0], 'id': 40, 'state': 'CHANGES_REQUESTED'})
    with pytest.raises(EvidenceError, match='ambiguous'):
        inspect_premerge_evidence(pr, run, jobs, reviews)


def test_post_merge_change_request_does_not_rewrite_historical_approval():
    pr, run, jobs, reviews = evidence()
    reviews.append({**reviews[0], 'id': 40, 'state': 'CHANGES_REQUESTED',
                    'submitted_at': '2026-10-20T18:50:00Z'})
    assert inspect_premerge_evidence(pr, run, jobs, reviews)['findings'] == []
