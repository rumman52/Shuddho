from __future__ import annotations

import hashlib
from typing import Any

from shared.schemas.python_models import AnalyzeResponse, CanonicalCheckResponse, CanonicalSuggestion, TextSpan


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]


def analyze_to_check_response(response: AnalyzeResponse, *, request_id: str, text: str, document_id: str | None = None, revision: int | None = None) -> CanonicalCheckResponse:
    suggestions: list[CanonicalSuggestion] = []
    for item in response.suggestions:
        replacement = item.replacement_options[0] if item.replacement_options else item.original_text
        suggestion_type = 'style' if item.category.value in {'register', 'clarity'} else 'rewrite' if item.category.value == 'rewrite_only' else item.category.value
        provider = 'python-bangla'
        stable = _hash(f"{document_id or 'global'}:{item.rule_id}:{suggestion_type}:{item.span_start}:{item.span_end}:{item.original_text}:{replacement}:{provider}")
        suppression = item.suppression_key or 'sk_' + _hash(f"{item.rule_id}:{item.original_text}:{replacement}:{suggestion_type}")
        suggestions.append(CanonicalSuggestion(
            id='sg_' + stable,
            suppressionKey=suppression,
            ruleId=item.rule_id,
            type=suggestion_type,
            severity=item.severity.value,
            originalText=item.original_text,
            suggestedText=replacement,
            replacementOptions=item.replacement_options,
            explanationBn=item.explanation_bn,
            explanationEn=item.explanation_en,
            span=TextSpan(startIndex=item.span_start, endIndex=item.span_end, codePointStartIndex=item.span_start, codePointEndIndex=item.span_end),
            confidence=item.confidence,
            source='spell' if item.source.value == 'spell' else 'rule' if item.source.value == 'rule' else 'ml' if item.source.value == 'model' else item.source.value,
            provider=provider,
            metadata={'legacyId': item.id, 'subtype': item.subtype},
        ))
    return CanonicalCheckResponse(requestId=request_id, documentId=document_id, revision=revision, language='bn', normalizedText=getattr(response, 'normalized_text', None), suggestions=suggestions, warnings=getattr(response, 'warnings', []))
