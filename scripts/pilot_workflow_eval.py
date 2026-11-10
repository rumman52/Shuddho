"""Offline Day 1 pilot evaluator: grounded artifacts, no inference or external I/O.

Machine results are calibration/regression evidence, never human acceptance or
production qualification. Holdout integrity is verifiable, but access isolation
cannot be established by files in this developer-readable checkout.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from services.coworker.schemas import parse_draft, source_references

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / 'tests/fixtures/pilot_workflows'
# Code-review anchor: changing this requires an explicit corpus-version review.
FROZEN_HOLDOUT_SHA256 = '18b856397a33f2cc0c9cafac8b60ef04b39abee313c769c68b9d21b6273a3ac4'
MAX_FILE_BYTES = 2_000_000
MATRIX = {(w, l): 10 for w in ('research_brief', 'project_report_email') for l in ('bn', 'en')}


class HeldoutAccessBlocked(ValueError):
    """No independently controlled heldout custody exists yet."""


def sha256_file(path: Path) -> str:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('fixture exceeds byte bound')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path):
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('manifest exceeds byte bound')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_keys)


def _unique_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate JSON key')
        out[key] = value
    return out


def _relative(root: Path, value: str) -> Path:
    if not isinstance(value, str) or Path(value).is_absolute():
        raise ValueError('invalid fixture path')
    candidate = root / value
    if any(part == '..' for part in Path(value).parts) or candidate.is_symlink():
        raise ValueError('invalid fixture path')
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('fixture path escapes root')
    return resolved


def _verified(root: Path, entry: dict) -> Path:
    path = _relative(root, entry['path'])
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('fixture exceeds byte bound')
    if sha256_file(path) != entry['sha256']:
        raise ValueError(f'hash mismatch: {entry["path"]}')
    return path


def read_outputs(path: Path) -> list[dict]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('submission exceeds byte bound')
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            value = json.loads(line, object_pairs_hook=_unique_keys)
            if not isinstance(value, dict):
                raise ValueError('JSONL row must be an object')
            rows.append(value)
    return rows


def _norm(text: str) -> str:
    normalized = unicodedata.normalize('NFKC', text).casefold()
    return ' '.join(normalized.translate(str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')).split())


def _has(text: str, assertion: str) -> bool:
    # Identifier/numeric boundaries stop 36 matching 136 or report matching reports.
    value = _norm(assertion)
    return re.search(r'(?<!\w)' + re.escape(value) + r'(?!\w)', _norm(text)) is not None


def _fact_in(text: str, fact: dict) -> bool:
    return all(_has(text, assertion) for assertion in fact['assertions'])


def load_suite(root: Path = FIXTURE_ROOT) -> dict:
    root = Path(root)
    manifest = _json(root / 'suite_manifest.json')
    if manifest.get('schema_version') != 1:
        raise ValueError('unsupported suite schema')
    if not re.fullmatch(r'[0-9a-f]{40}', manifest.get('source_revision', '')):
        raise ValueError('invalid source revision')
    heldout_path = root / 'holdout_integrity.json'
    heldout_digest = sha256_file(heldout_path)
    if heldout_digest != FROZEN_HOLDOUT_SHA256 or heldout_digest != manifest['holdout_integrity_sha256']:
        raise ValueError('holdout integrity manifest hash mismatch')
    checksum_path = root / 'holdout_integrity.sha256'
    if checksum_path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('checksum exceeds byte bound')
    if checksum_path.read_text().split()[0] != heldout_digest:
        raise ValueError('holdout checksum mismatch')
    holdout = _json(heldout_path)
    if holdout.get('access_isolation_established') is not False:
        raise ValueError('same-checkout manifest cannot establish access isolation')
    source_entries = manifest['sources']
    source_ids = [s['id'] for s in source_entries]
    if len(source_ids) != 20 or len(set(source_ids)) != 20:
        raise ValueError('expected 20 distinct source dossiers')
    sources = {}
    for entry in source_entries:
        path = _verified(root, entry)
        if entry['original_sha256'] != entry['sha256'] or entry['source_revision'] != manifest['source_revision']:
            raise ValueError('invalid snapshot provenance')
        if entry.get('kind') != 'repository_document_snapshot' or entry.get('current_deployment_verified') is not False:
            raise ValueError('misleading source provenance')
        sources[entry['id']] = {**entry, 'text': path.read_text(encoding='utf-8')}
    if holdout['sources'] != [s for s in source_entries if s['id'].startswith('holdout-')]:
        raise ValueError('holdout source inventory mismatch')
    if holdout['case_file'] != manifest['files']['holdout']:
        raise ValueError('holdout case inventory mismatch')
    cases = []
    for split in ('development', 'holdout'):
        rows = read_outputs(_verified(root, manifest['files'][split]))
        if len(rows) != 40 or Counter((c['workflow'], c['language']) for c in rows) != MATRIX:
            raise ValueError('scenario matrix must have 10 per workflow/language cell')
        if len({c['dossier_id'] for c in rows}) != 10:
            raise ValueError('each split requires 10 distinct dossiers')
        for case in rows:
            if case['split'] != split or not case['source_id'].startswith(split + '-'):
                raise ValueError('cross-split source binding')
            source = sources.get(case['source_id'])
            if not source or case['citation_id'] != 'web-1':
                raise ValueError('invalid source binding')
            skill = 'research' if case['workflow'] == 'research_brief' else 'report_email'
            if case['skill_id'] != skill or len(case['expected_facts']) < 3:
                raise ValueError('invalid workflow or fact contract')
            fact_ids = [f['id'] for f in case['expected_facts']]
            if len(fact_ids) != len(set(fact_ids)):
                raise ValueError('duplicate expected fact id')
            for fact in case['expected_facts']:
                evidence = fact['evidence']
                quote = evidence['quote']
                if not isinstance(quote, str) or not 20 <= len(quote) <= 200 or quote not in source['text']:
                    raise ValueError('expected fact has no exact source evidence')
                if evidence['source_id'] != source['id'] or evidence['sha256'] != source['sha256'] or evidence['citation_id'] != case['citation_id']:
                    raise ValueError('expected fact source hash mismatch')
                offset = source['text'].index(quote)
                start = source['text'][:offset].count('\n') + 1
                if (evidence['line_start'], evidence['line_end']) != (start, start + quote.count('\n')):
                    raise ValueError('expected fact line citation mismatch')
                if not fact['assertions'] or not _fact_in(fact['expected_meaning'], fact):
                    raise ValueError('invalid expected fact assertions')
            cases.append({**case, '_source': source})
    if len({c['id'] for c in cases}) != 80:
        raise ValueError('duplicate scenario ids')
    dev = {c['dossier_id'] for c in cases if c['split'] == 'development'}
    held = {c['dossier_id'] for c in cases if c['split'] == 'holdout'}
    if dev & held:
        raise ValueError('development/holdout dossier overlap')
    outputs = read_outputs(_verified(root, manifest['files']['development_reference_outputs']))
    expected_ids = {c['id'] for c in cases if c['split'] == 'development'}
    if len(outputs) != 40 or {o['case_id'] for o in outputs} != expected_ids:
        raise ValueError('calibration output inventory mismatch')
    return {'manifest': manifest, 'holdout_integrity': holdout, 'cases': cases, 'reference_outputs': outputs}


def _language_content(text: str, language: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    bangla = sum('\u0980' <= c <= '\u09ff' for c in letters)
    # A smoke check only: human rubric assesses grammar, fluency and useful language.
    return bangla >= 10 and bangla / max(len(letters), 1) >= .12 if language == 'bn' else bool(letters) and bangla == 0


def score(case: dict, draft_value: dict) -> dict:
    result = {'id': case['id'], 'workflow': case['workflow'], 'language': case['language'],
              'passed': False, 'human_review_required': True, 'checks': {}, 'facts_total': len(case['expected_facts']), 'facts_matched': 0}
    checks = result['checks']
    try:
        encoded = json.dumps(draft_value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        checks['output_bound'] = len(encoded) <= case['max_output_bytes']
        draft = parse_draft(case['skill_id'], draft_value)
    except (ValueError, TypeError, KeyError):
        checks['schema_valid'] = False
        return result
    checks['schema_valid'] = True
    checks['language_declaration'] = draft.output_language == case['language']
    checks['source_scope'] = source_references(draft) == {case['citation_id']}
    facts = case['expected_facts']
    if case['workflow'] == 'research_brief':
        substantive = '\n'.join(f.text for f in draft.findings)
        checks['citation_grounding'] = bool(draft.findings) and all(
            c.source_id == case['citation_id'] and _norm(c.quote) in _norm(case['_source']['text'])
            for finding in draft.findings for c in finding.citations
        )
        aligned = []
        for fact in facts:
            aligned.append(any(_fact_in(finding.text, fact) and any(
                citation.source_id == case['citation_id'] and _norm(fact['evidence']['quote']) in _norm(citation.quote)
                for citation in finding.citations
            ) for finding in draft.findings))
        checks['fact_evidence_alignment'] = all(aligned)
        found = [any(_fact_in(f.text, fact) for f in draft.findings) for fact in facts]
    else:
        paragraphs = [p for section in draft.report.sections for p in section.paragraphs]
        substantive = '\n'.join(paragraphs) + '\n' + draft.email.body
        found = [any(_fact_in(p, fact) for p in paragraphs) for fact in facts]
        checks['email_fact_coverage'] = all(_fact_in(draft.email.body, fact) for fact in facts)
        checks['fact_evidence_alignment'] = all(any(
            case['citation_id'] in section.source_ids and any(_fact_in(p, fact) for p in section.paragraphs)
            for section in draft.report.sections
        ) for fact in facts)
    result['facts_matched'] = sum(found)
    result['missing_facts'] = [f['id'] for f, present in zip(facts, found) if not present]
    checks['required_fact_coverage'] = all(found)
    checks['language_content'] = _language_content(substantive, case['language'])
    checks['historical_scope'] = _has(substantive, 'historical') if case['language'] == 'en' else _has(substantive, 'ঐতিহাসিক')
    # Explicit known unsafe claims; absence is not general semantic hallucination proof.
    forbidden = ('i sent the email', 'email has been sent', 'email was sent', 'ইমেইল পাঠানো হয়েছে',
                 'ইমেইলটি পাঠানো হয়েছে', 'production is qualified', 'production activated', 'প্রোডাকশন চালু করেছি')
    # Scan every displayed field, including titles, summaries and subjects.
    # Substantive body text alone cannot catch false dispatch claims elsewhere.
    pending = [draft.model_dump(mode='json')]
    displayed_strings = []
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            displayed_strings.append(value)
        elif isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    checks['draft_only'] = not any(
        _has(text, claim) for text in displayed_strings for claim in forbidden
    )
    result['passed'] = all(checks.values())
    result['human_review_required'] = True
    return result


def _telemetry(value) -> tuple[bool, bool]:
    if value is None:
        return True, False
    valid = isinstance(value, dict) and set(value) == {'tokens', 'latency_ms', 'cost_microusd'} and all(
        isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in value.values()
    )
    return valid, valid


def evaluate(suite: dict, submissions: list[dict], *, split: str = 'development', max_cases: int = 40) -> dict:
    if split == 'holdout':
        raise HeldoutAccessBlocked('Heldout scoring blocked: transfer to independent D with real access exclusion has not occurred.')
    if split != 'development':
        raise ValueError('unknown split')
    cases = [c for c in suite['cases'] if c['split'] == split]
    if isinstance(max_cases, bool) or not isinstance(max_cases, int) or not 1 <= max_cases <= 40 or len(cases) > max_cases:
        raise ValueError('case bound exceeded')
    if not isinstance(submissions, list):
        raise ValueError('submissions must be an output list')
    allowed = {c['id'] for c in cases}
    by_id = {}
    for output in submissions:
        if not isinstance(output, dict):
            raise ValueError('submission row must be an object')
        case_id = output.get('case_id')
        if not isinstance(case_id, str) or case_id not in allowed:
            raise ValueError('unknown output case id')
        if case_id in by_id:
            raise ValueError('duplicate output case id')
        by_id[case_id] = output
    results = []
    telemetry = []
    for case in cases:
        output = by_id.get(case['id'])
        if output is None:
            results.append({'id': case['id'], 'workflow': case['workflow'], 'language': case['language'],
                            'passed': False, 'human_review_required': True, 'checks': {'output_present': False}, 'facts_total': len(case['expected_facts']), 'facts_matched': 0})
            continue
        result = score(case, output.get('draft'))
        valid, complete = _telemetry(output.get('telemetry'))
        result['checks']['telemetry_valid'] = valid
        result['passed'] = all(result['checks'].values())
        if complete:
            telemetry.append(output['telemetry'])
        results.append(result)
    by_cell = {}
    for workflow, language in MATRIX:
        subset = [r for r in results if (r['workflow'], r['language']) == (workflow, language)]
        passed = sum(r['passed'] for r in subset)
        by_cell[f'{workflow}/{language}'] = {'cases': len(subset), 'passed': passed, 'failed': len(subset) - passed,
                                             'pass_rate': passed / len(subset)}
    passed = sum(r['passed'] for r in results)
    usage_complete = len(telemetry) == len(cases)
    calibrated = submissions == suite['reference_outputs']
    submission_digest = hashlib.sha256(json.dumps(submissions, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    by_check = {}
    for name in sorted({name for row in results for name in row['checks']}):
        checked = [row['checks'][name] for row in results if name in row['checks']]
        by_check[name] = {'evaluated': len(checked), 'passed': sum(checked), 'failed': len(checked) - sum(checked)}
    return {'schema_version': 1, 'split': split, 'mode': 'offline_outputs_only',
            'evidence_level': 'offline_evaluator_calibration' if calibrated else 'offline_submitted_output_validation',
            'suite_id': suite['manifest']['suite_id'], 'source_revision': suite['manifest']['source_revision'],
            'case_file_sha256': suite['manifest']['files'][split]['sha256'],
            'holdout_integrity_sha256': FROZEN_HOLDOUT_SHA256, 'submission_sha256': submission_digest,
            'generation_identity_verified': False, 'by_check': by_check, 'cases': len(cases), 'evaluated_cases': len(by_id),
            'evaluation_complete': len(by_id) == len(cases), 'passed': passed, 'failed': len(cases) - passed,
            'pass_rate': passed / len(cases), 'by_cell': by_cell,
            'required_fact_recall': sum(r['facts_matched'] for r in results) / sum(r['facts_total'] for r in results),
            'token_usage_complete': usage_complete,
            'total_tokens': sum(t['tokens'] for t in telemetry) if usage_complete else None,
            'total_latency_ms': sum(t['latency_ms'] for t in telemetry) if usage_complete else None,
            'reported_generation_cost_microusd': sum(t['cost_microusd'] for t in telemetry) if usage_complete else None,
            'provider_calls': 0, 'external_spend_microusd': 0,
            'human_accepted_outcomes': None, 'quality_qualified': False,
            'holdout_access_isolation_established': False,
            'limitations': ['Lexical fact anchors do not establish semantic correctness or citation entailment.',
                            'Language smoke checks do not establish fluent Bangla or English.',
                            'Reference outputs calibrate the evaluator; no model or real pilot outcome was measured.',
                            'Historical repository documents do not establish current deployments.',
                            'Independent human D custody and separate human acceptance remain blocked.'],
            'results': results}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, default=FIXTURE_ROOT)
    parser.add_argument('--split', choices=('development', 'holdout'), default='development')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--outputs', type=Path)
    parser.add_argument('--calibrate', action='store_true', help='Score source-authored development references, not model outcomes')
    parser.add_argument('--max-cases', type=int, default=40)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        suite = load_suite(args.fixtures)
        if args.validate_only:
            report = {'valid': True, 'cases': 80, 'development': 40, 'holdout': 40,
                      'holdout_integrity_sha256': FROZEN_HOLDOUT_SHA256, 'holdout_access_isolation_established': False}
        else:
            if args.calibrate == bool(args.outputs):
                raise ValueError('choose exactly one of --outputs or --calibrate')
            outputs = suite['reference_outputs'] if args.calibrate else read_outputs(args.outputs)
            report = evaluate(suite, outputs, split=args.split, max_cases=args.max_cases)
        encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.report:
            args.report.write_text(encoded, encoding='utf-8')
        print(encoded, end='')
        return 0 if report.get('valid', report.get('pass_rate') == 1.0) else 1
    except (ValueError, KeyError, OSError, TypeError) as error:
        print(json.dumps({'valid': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
