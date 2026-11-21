"""Acceptance tests for the bounded, source-grounded Day 1 evaluator."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from scripts.pilot_workflow_eval import (
    FIXTURE_ROOT, HeldoutAccessBlocked, evaluate, load_suite, score,
)



def test_coordinated_development_fixture_rehash_cannot_redefine_the_frozen_suite(tmp_path):
    """A locally edited manifest must not be able to self-approve a new corpus."""
    import hashlib
    copied = tmp_path / 'fixtures'
    shutil.copytree(FIXTURE_ROOT, copied)
    cases = copied / 'development.jsonl'
    # A byte-level edit leaves the scenario count and semantics unchanged.
    cases.write_bytes(cases.read_bytes() + b'\n')
    manifest_path = copied / 'suite_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['files']['development']['sha256'] = hashlib.sha256(cases.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest) + '\n', encoding='utf-8')

    with pytest.raises(ValueError, match='suite manifest fingerprint mismatch'):
        load_suite(copied)


def test_validation_receipt_binds_exact_frozen_manifest_bytes(capsys):
    from scripts.pilot_workflow_eval import FROZEN_SUITE_MANIFEST_SHA256, main, sha256_file
    assert sha256_file(FIXTURE_ROOT / 'suite_manifest.json') == FROZEN_SUITE_MANIFEST_SHA256
    assert main(['--validate-only']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['suite_manifest_sha256'] == FROZEN_SUITE_MANIFEST_SHA256
    assert report['holdout_access_isolation_established'] is False


def test_frozen_suite_has_80_grounded_balanced_scenarios():
    suite = load_suite()
    assert len(suite['cases']) == 80
    assert len({c['dossier_id'] for c in suite['cases']}) == 20
    for split in ('development', 'holdout'):
        subset = [c for c in suite['cases'] if c['split'] == split]
        assert len(subset) == 40
        for workflow in ('research_brief', 'project_report_email'):
            for language in ('bn', 'en'):
                assert sum(c['workflow'] == workflow and c['language'] == language for c in subset) == 10
    dev_sources = {c['source_id'] for c in suite['cases'] if c['split'] == 'development'}
    holdout_sources = {c['source_id'] for c in suite['cases'] if c['split'] == 'holdout'}
    assert dev_sources.isdisjoint(holdout_sources)
    assert all(len(c['expected_facts']) >= 3 for c in suite['cases'])


def test_known_reference_outputs_pass_but_are_not_human_acceptance():
    suite = load_suite()
    result = evaluate(suite, suite['reference_outputs'])
    assert result['cases'] == result['evaluated_cases'] == result['passed'] == 40
    assert result['pass_rate'] == 1.0
    assert result['human_accepted_outcomes'] is None
    assert result['evidence_level'] == 'offline_evaluator_calibration'
    assert result['provider_calls'] == result['external_spend_microusd'] == 0
    assert result['quality_qualified'] is False
    assert all(row['cases'] == 10 for row in result['by_cell'].values())


def test_heldout_execution_blocks_until_real_custody_transfer():
    suite = load_suite()
    with pytest.raises(HeldoutAccessBlocked, match='independent D'):
        evaluate(suite, [], split='holdout')
    assert suite['holdout_integrity']['access_isolation_established'] is False


def pair(workflow='research_brief', language='en'):
    suite = load_suite()
    case = next(c for c in suite['cases'] if c['split'] == 'development' and c['workflow'] == workflow and c['language'] == language)
    output = deepcopy(next(o for o in suite['reference_outputs'] if o['case_id'] == case['id'])['draft'])
    return case, output


def test_facts_in_a_quote_or_title_do_not_count_as_answer_facts():
    case, draft = pair()
    for finding in draft['findings']:
        finding['text'] = 'No substantive answer.'
    assert score(case, draft)['checks']['required_fact_coverage'] is False


def test_research_rejects_forged_quote_and_unsupplied_source():
    case, draft = pair()
    draft['findings'][0]['citations'][0]['quote'] = 'This quote was invented.'
    assert score(case, draft)['checks']['citation_grounding'] is False
    case, draft = pair()
    draft['findings'][0]['citations'][0]['source_id'] = 'web-2'
    assert score(case, draft)['checks']['source_scope'] is False


def test_required_fact_must_carry_its_own_supporting_citation():
    case, draft = pair()
    draft['findings'][0]['citations'] = draft['findings'][1]['citations']
    assert score(case, draft)['checks']['fact_evidence_alignment'] is False


def test_report_requires_facts_in_both_report_and_email():
    case, draft = pair('project_report_email')
    draft['email']['body'] = 'Please see report.'
    assert score(case, draft)['checks']['email_fact_coverage'] is False


def test_report_missing_source_and_false_dispatch_claim_fail():
    case, draft = pair('project_report_email')
    draft['report']['sections'][0]['source_ids'] = ['web-2']
    draft['email']['body'] += ' I sent the email.'
    result = score(case, draft)
    assert result['checks']['source_scope'] is False
    assert result['checks']['draft_only'] is False


def test_language_declaration_does_not_replace_language_content():
    case, draft = pair(language='bn')
    for finding in draft['findings']:
        finding['text'] = 'English prose only.'
    assert score(case, draft)['checks']['language_content'] is False


def test_missing_duplicate_unknown_output_ids_fail_closed():
    suite = load_suite()
    values = suite['reference_outputs']
    result = evaluate(suite, values[:-1])
    assert result['evaluation_complete'] is False and result['failed'] == 1
    with pytest.raises(ValueError, match='duplicate'):
        evaluate(suite, values + [values[0]])
    with pytest.raises(ValueError, match='unknown'):
        evaluate(suite, values + [{'case_id': 'unknown', 'draft': {}}])


def test_source_mutation_is_rejected_before_scoring(tmp_path):
    copied = tmp_path / 'fixtures'
    shutil.copytree(FIXTURE_ROOT, copied)
    manifest = json.loads((copied / 'suite_manifest.json').read_text())
    source = copied / manifest['sources'][0]['path']
    source.write_text(source.read_text() + '\ntamper\n')
    with pytest.raises(ValueError, match='hash mismatch'):
        load_suite(copied)


def test_manifest_cannot_silently_rebalance_or_rewrite_case_file(tmp_path):
    copied = tmp_path / 'fixtures'
    shutil.copytree(FIXTURE_ROOT, copied)
    path = copied / 'development.jsonl'
    path.write_text(path.read_text().replace('research_brief', 'wrong', 1))
    with pytest.raises(ValueError, match='hash mismatch'):
        load_suite(copied)


def test_budget_and_telemetry_validation():
    suite = load_suite()
    with pytest.raises(ValueError, match='case bound'):
        evaluate(suite, suite['reference_outputs'], max_cases=39)
    values = deepcopy(suite['reference_outputs'])
    values[0]['telemetry'] = {'tokens': -1, 'latency_ms': 1, 'cost_microusd': 0}
    result = evaluate(suite, values)
    assert result['results'][0]['checks']['telemetry_valid'] is False
    assert result['token_usage_complete'] is False


def test_numeric_corruption_does_not_match_a_smaller_fact_value():
    suite = load_suite()
    case = next(c for c in suite['cases'] if c['dossier_id'] == 'cleanup-lifetime' and c['workflow'] == 'research_brief' and c['language'] == 'en')
    draft = deepcopy(next(o['draft'] for o in suite['reference_outputs'] if o['case_id'] == case['id']))
    for finding in draft['findings']:
        finding['text'] = finding['text'].replace('189 passed', '1189 passed')
    result = score(case, draft)
    assert not result['passed']
    assert 'cleanup-lifetime-fact-2' in result['missing_facts']


def test_frozen_holdout_rewrite_cannot_be_approved_by_local_manifest_update(tmp_path):
    import hashlib
    copied = tmp_path / 'fixtures'
    shutil.copytree(FIXTURE_ROOT, copied)
    holdout = copied / 'holdout_integrity.json'
    value = json.loads(holdout.read_text())
    value['custodian'] = 'Developer self-approved D custody'
    holdout.write_text(json.dumps(value))
    manifest = copied / 'suite_manifest.json'
    value = json.loads(manifest.read_text())
    value['holdout_integrity_sha256'] = hashlib.sha256(holdout.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='holdout integrity manifest hash mismatch'):
        load_suite(copied)


def test_duplicate_json_keys_rejected_before_scoring(tmp_path):
    from scripts.pilot_workflow_eval import read_outputs
    path = tmp_path / 'outputs.jsonl'
    path.write_text('{"case_id":"a","case_id":"b"}\n')
    with pytest.raises(ValueError, match='duplicate JSON key'):
        read_outputs(path)


def test_snapshot_bytes_match_the_claimed_historical_git_revision():
    import subprocess
    suite = load_suite()
    for source in suite['manifest']['sources']:
        original = subprocess.check_output(['git', 'show', source['source_revision'] + ':' + source['original_path']])
        assert original == (FIXTURE_ROOT / source['path']).read_bytes()


def test_cli_explicitly_distinguishes_validation_calibration_and_custody(capsys):
    from scripts.pilot_workflow_eval import main
    assert main(['--validate-only']) == 0
    assert json.loads(capsys.readouterr().out)['cases'] == 80
    assert main(['--calibrate']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['passed'] == 40 and result['quality_qualified'] is False
    assert main(['--calibrate', '--split', 'holdout']) == 2
    assert 'independent D' in json.loads(capsys.readouterr().out)['error']


@pytest.mark.parametrize(('workflow', 'field'), [
    ('research_brief', 'title'),
    ('project_report_email', 'summary'),
    ('project_report_email', 'subject'),
])
@pytest.mark.parametrize('claim', ['Production is qualified. I sent the email.', 'I sent\nthe email.'])
def test_false_dispatch_claims_in_artifact_headings_fail(workflow, field, claim):
    case, draft = pair(workflow)
    if field == 'title':
        draft['title'] = claim
    elif field == 'summary':
        draft['report']['summary'] = claim
    else:
        draft['email']['subject'] = claim
    result = score(case, draft)
    assert result['checks']['draft_only'] is False
    assert result['passed'] is False


@pytest.mark.parametrize('filename', ['holdout_integrity.json', 'holdout_integrity.sha256'])
def test_oversized_integrity_metadata_rejected_before_reading(tmp_path, filename):
    from scripts.pilot_workflow_eval import MAX_FILE_BYTES
    copied = tmp_path / 'fixtures'
    shutil.copytree(FIXTURE_ROOT, copied)
    target = copied / filename
    target.write_bytes(b'x' * (MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match='byte bound'):
        load_suite(copied)


def test_verified_dossier_text_is_the_exact_hashed_snapshot(tmp_path, monkeypatch):
    """Changing the content at its second read must not corrupt source provenance."""
    import hashlib

    copied = tmp_path / 'fixtures'
    shutil.copytree(FIXTURE_ROOT, copied)
    manifest = json.loads((copied / 'suite_manifest.json').read_text(encoding='utf-8'))
    source = manifest['sources'][0]
    target = (copied / source['path']).resolve()
    original_read_text = Path.read_text

    def switched_read_text(path, *args, **kwargs):
        text = original_read_text(path, *args, **kwargs)
        if path == target:
            return text + '\nUNREVIEWED_PROVENANCE_MARKER\n'
        return text

    monkeypatch.setattr(Path, 'read_text', switched_read_text)
    suite = load_suite(copied)
    actual = next(c['_source'] for c in suite['cases'] if c['source_id'] == source['id'])
    assert hashlib.sha256(actual['text'].encode('utf-8')).hexdigest() == source['sha256']
    assert 'UNREVIEWED_PROVENANCE_MARKER' not in actual['text']


def test_verified_case_rows_are_the_exact_hashed_snapshot(tmp_path, monkeypatch):
    """The evaluator cannot accept extra cases metadata after manifest hash verification."""
    copied = tmp_path / 'fixtures'
    shutil.copytree(FIXTURE_ROOT, copied)
    manifest = json.loads((copied / 'suite_manifest.json').read_text(encoding='utf-8'))
    target = (copied / manifest['files']['development']['path']).resolve()
    original_read_text = Path.read_text

    def switched_read_text(path, *args, **kwargs):
        text = original_read_text(path, *args, **kwargs)
        if path == target:
            rows = text.splitlines()
            first = json.loads(rows[0])
            first['UNREVIEWED_CASE_MARKER'] = True
            rows[0] = json.dumps(first, ensure_ascii=False)
            return '\n'.join(rows) + '\n'
        return text

    monkeypatch.setattr(Path, 'read_text', switched_read_text)
    suite = load_suite(copied)
    assert not any('UNREVIEWED_CASE_MARKER' in c for c in suite['cases'])


def test_evaluator_submission_does_not_follow_a_direct_symlink(tmp_path):
    """A small, valid JSONL outside the submitted path is still an invalid input."""
    from scripts.pilot_workflow_eval import read_outputs

    target = tmp_path / 'private-substitution.jsonl'
    target.write_text('{"case_id":"case-a","draft":{}}\n', encoding='utf-8')
    submitted = tmp_path / 'submitted.jsonl'
    submitted.symlink_to(target)
    with pytest.raises(ValueError, match='symlink|regular|no-follow'):
        read_outputs(submitted)


@pytest.mark.parametrize('language', ('en', 'bn'))
@pytest.mark.parametrize('separator', (' ' * 20, '\n' * 20), ids=('spaces', 'newlines'))
def test_research_rejects_whitespace_padded_short_evidence(language, separator):
    """Schema length is not evidence length after normalization of internal whitespace."""
    case, draft = pair(language=language)
    # The actual source has "Keep the". The padded quote satisfies the
    # production schema's 20 raw characters but normalizes to just 8.
    quote = 'Keep' + separator + 'the'
    assert len(quote) >= 20
    assert 'keep the' in case['_source']['text'].casefold()
    draft['findings'].append({
        'heading': 'Unverified additional finding' if language == 'en' else 'অযাচাইকৃত অতিরিক্ত তথ্য',
        'text': 'A new unsupported claim is asserted.' if language == 'en'
                else 'অযাচাইকৃত নতুন দাবি যোগ করা হয়েছে।',
        'citations': [{'source_id': case['citation_id'], 'quote': quote}],
    })
    result = score(case, draft)
    assert result['checks']['schema_valid'] is True
    assert result['checks']['citation_grounding'] is False
    assert result['passed'] is False
