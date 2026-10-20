"""V-01 native-policy diagnostic: never treats settings as proof of enforcement."""
import json
import subprocess
import sys
from pathlib import Path

from scripts.v01_native_protection_audit import assess_native_policy

JOBS = ('test-and-build', 'coworker', 'ci-merge-gate')


def protection(**changes):
    p = {
        'required_status_checks': {'strict': True, 'contexts': list(JOBS)},
        'required_pull_request_reviews': {
            'required_approving_review_count': 1,
            'dismiss_stale_reviews': True,
            'require_last_push_approval': True,
            'bypass_pull_request_allowances': {'users': [], 'teams': [], 'apps': []},
        },
        'required_conversation_resolution': {'enabled': True},
        'enforce_admins': {'enabled': True},
        'allow_force_pushes': {'enabled': False},
        'allow_deletions': {'enabled': False},
    }
    p.update(changes)
    return p


def ruleset(**changes):
    r = {
        'id': 100,
        'name': 'main-guard',
        'enforcement': 'active',
        'target': 'branch',
        'conditions': {'ref_name': {'include': ['refs/heads/main'], 'exclude': []}},
        'bypass_actors': [],
        'rules': [
            {'type': 'pull_request', 'parameters': {'required_approving_review_count': 1,
                'dismiss_stale_reviews_on_push': True, 'require_last_push_approval': True,
                'required_review_thread_resolution': True}},
            {'type': 'required_status_checks', 'parameters': {
                'strict_required_status_checks_policy': True,
                'required_status_checks': [{'context': x} for x in JOBS]}},
            {'type': 'non_fast_forward'},
            {'type': 'deletion'},
        ],
    }
    r.update(changes)
    return r


def test_no_evidence_is_blocked_not_safe():
    result = assess_native_policy()
    assert result['classification'] == 'blocked'
    assert 'no_readable_native_policy' in result['findings']


def test_strict_native_branch_protection_is_candidate_not_qualified():
    result = assess_native_policy(branch_protection=protection())
    assert result['classification'] == 'configuration_candidate'
    assert result['enforcement_verified'] is False
    assert 'independent_negative_control_required' in result['remaining_gates']


def test_each_required_job_must_be_status_context():
    weak = protection(required_status_checks={'strict': True, 'contexts': ['test-and-build', 'coworker']})
    result = assess_native_policy(branch_protection=weak)
    assert result['classification'] == 'blocked'
    assert 'missing_required_checks:ci-merge-gate' in result['findings']


def test_no_weak_or_bypassed_review_approval():
    cases = [
        protection(required_pull_request_reviews={**protection()['required_pull_request_reviews'], 'required_approving_review_count': 0}),
        protection(required_pull_request_reviews={**protection()['required_pull_request_reviews'], 'dismiss_stale_reviews': False}),
        protection(required_pull_request_reviews={**protection()['required_pull_request_reviews'], 'bypass_pull_request_allowances': {'users': ['owner']}}),
        protection(enforce_admins={'enabled': False}),
        protection(required_conversation_resolution={'enabled': False}),
        protection(allow_force_pushes={'enabled': True}),
    ]
    for case in cases:
        assert assess_native_policy(branch_protection=case)['classification'] == 'blocked'


def test_ruleset_active_applicable_strict_candidate():
    result = assess_native_policy(rulesets=[ruleset()])
    assert result['classification'] == 'configuration_candidate'
    assert result['enforcement_verified'] is False
    assert result['candidate_source'] == 'active_ruleset'


def test_ruleset_disabled_bypassed_wrong_branch_or_missing_rule_is_blocked():
    variants = [
        ruleset(enforcement='evaluate'),
        ruleset(bypass_actors=[{'actor_id': 1, 'actor_type': 'OrganizationAdmin', 'bypass_mode': 'always'}]),
        ruleset(conditions={'ref_name': {'include': ['refs/heads/dev'], 'exclude': []}}),
        ruleset(conditions={'ref_name': {'include': ['refs/heads/main'], 'exclude': ['refs/heads/main']}}),
        ruleset(rules=ruleset()['rules'][:-1]),
        ruleset(target='tag'),
    ]
    for case in variants:
        assert assess_native_policy(rulesets=[case])['classification'] == 'blocked'


def test_protection_checks_can_use_check_objects_without_contexts():
    value = protection(required_status_checks={'strict': True, 'checks': [{'context': j, 'app_id': 123} for j in JOBS]})
    assert assess_native_policy(branch_protection=value)['classification'] == 'configuration_candidate'


def test_ruleset_check_contexts_must_include_all_three():
    r = ruleset()
    r['rules'][1]['parameters']['required_status_checks'].pop()
    assert assess_native_policy(rulesets=[r])['classification'] == 'blocked'


def test_invalid_payload_never_returns_candidate():
    for value in [[], 'error', {'message': 'Resource not accessible by integration'}, {'required_status_checks': {'strict': True}}]:
        assert assess_native_policy(branch_protection=value)['classification'] == 'blocked'


def test_cli_uses_status_two_when_config_is_missing(tmp_path):
    fixture = tmp_path / 'denied.json'
    fixture.write_text(json.dumps({'message': 'Resource not accessible by integration'}))
    proc = subprocess.run([sys.executable, '-m', 'scripts.v01_native_protection_audit',
        '--branch-protection-json', str(fixture)], capture_output=True, text=True)
    assert proc.returncode == 2
    assert json.loads(proc.stdout)['classification'] == 'blocked'


def test_cli_candidate_is_nonzero_until_negative_controls(tmp_path):
    fixture = tmp_path / 'candidate.json'
    fixture.write_text(json.dumps(protection()))
    proc = subprocess.run([sys.executable, '-m', 'scripts.v01_native_protection_audit',
        '--branch-protection-json', str(fixture)], capture_output=True, text=True)
    assert proc.returncode == 3
    output = json.loads(proc.stdout)
    assert output['classification'] == 'configuration_candidate'
    assert output['enforcement_verified'] is False
