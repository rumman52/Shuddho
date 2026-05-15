import { makeStableSuggestionId, makeSuppressionKey } from '../suggestionIds.js';
import { snapSpanToGraphemeBoundary, toUtf16Offsets } from '../bangla/unicode.js';
import type { CheckResponse, Suggestion, SuggestionSource, SuggestionType } from '../index.js';

type LegacySuggestion = Record<string, any>;
const categoryMap: Record<string, SuggestionType> = { register: 'style', clarity: 'style', rewrite_only: 'rewrite', model: 'rewrite' };
const sourceMap: Record<string, SuggestionSource> = { model: 'ml' };
function asType(value: unknown): SuggestionType { const v = String(value ?? 'grammar'); return (categoryMap[v] ?? v) as SuggestionType; }
function asSource(value: unknown, type: SuggestionType): SuggestionSource { const v = String(value ?? type); return (sourceMap[v] ?? v) as SuggestionSource; }

export function legacyAnalyzeToCheckResponse(input: unknown, opts: { requestId: string; text: string; documentId?: string; revision?: number; provider?: string } ): CheckResponse {
  const body = (input ?? {}) as Record<string, any>;
  const raw = Array.isArray(body.suggestions) ? body.suggestions as LegacySuggestion[] : [];
  const suggestions: Suggestion[] = raw.map((item) => legacySuggestionToCanonical(item, opts.text, opts));
  return { requestId: opts.requestId, documentId: opts.documentId, revision: opts.revision, language: 'bn', normalizedText: body.normalized_text ?? body.normalizedText, suggestions, timings: {}, warnings: body.warnings ?? [] };
}

export function legacySuggestionToCanonical(item: LegacySuggestion, text: string, opts: { documentId?: string; provider?: string }): Suggestion {
  const type = asType(item.category ?? item.type);
  const ruleId = String(item.rule_id ?? item.ruleId ?? `${type}.legacy`);
  const cpStart = Number(item.span_start ?? item.startIndex ?? item.span?.codePointStartIndex ?? item.span?.startIndex ?? 0);
  const cpEnd = Number(item.span_end ?? item.endIndex ?? item.span?.codePointEndIndex ?? item.span?.endIndex ?? cpStart);
  const utf16 = toUtf16Offsets(text, cpStart, cpEnd);
  const snapped = snapSpanToGraphemeBoundary(text, utf16.utf16StartIndex, utf16.utf16EndIndex);
  const replacements = Array.isArray(item.replacement_options) ? item.replacement_options : Array.isArray(item.replacementOptions) ? item.replacementOptions : [item.suggestedText ?? ''];
  const originalText = String(item.original_text ?? item.originalText ?? text.slice(snapped.startIndex, snapped.endIndex));
  const suggestedText = String(item.suggestedText ?? replacements[0] ?? originalText);
  const provider = String(opts.provider ?? item.provider ?? 'python-bangla');
  const suppressionKey = String(item.suppression_key ?? item.suppressionKey ?? makeSuppressionKey({ ruleId, originalText, suggestedText, type }));
  return {
    id: String(item.id && !String(item.id).includes(':') ? item.id : makeStableSuggestionId({ documentId: opts.documentId, ruleId, type, startIndex: snapped.startIndex, endIndex: snapped.endIndex, originalText, suggestedText, provider })),
    suppressionKey,
    ruleId,
    type,
    severity: item.severity === 'high' || item.severity === 'low' ? item.severity : 'medium',
    originalText,
    suggestedText,
    replacementOptions: replacements.filter((x: unknown) => typeof x === 'string'),
    explanationBn: String(item.explanation_bn ?? item.explanation ?? item.explanationBn ?? 'শুদ্ধোর প্রস্তাবনা'),
    explanationEn: item.explanation_en ?? item.explanationEn,
    span: snapped,
    confidence: Number(item.confidence ?? 0.75),
    source: asSource(item.source, type),
    provider,
    metadata: { legacy: true, subtype: item.subtype },
  };
}
