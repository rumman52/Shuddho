import type { CheckResponse } from '../index.js';
export function checkResponseToLegacyAnalyze(response: CheckResponse): Record<string, unknown> {
  return {
    request_id: response.requestId,
    normalized_text: response.normalizedText,
    suggestions: response.suggestions.map((s) => ({
      id: s.id, rule_id: s.ruleId, category: s.type === 'rewrite' ? 'rewrite_only' : s.type, subtype: String(s.metadata?.subtype ?? s.ruleId),
      span_start: s.span.codePointStartIndex ?? s.span.startIndex, span_end: s.span.codePointEndIndex ?? s.span.endIndex,
      original_text: s.originalText, replacement_options: s.replacementOptions, confidence: s.confidence,
      explanation_bn: s.explanationBn, explanation_en: s.explanationEn ?? '', source: s.source === 'ml' ? 'model' : s.source,
      severity: s.severity, suppression_key: s.suppressionKey,
    })),
    warnings: response.warnings ?? [],
  };
}
