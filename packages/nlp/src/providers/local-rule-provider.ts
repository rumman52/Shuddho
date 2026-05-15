import { makeStableSuggestionId, makeSuppressionKey, snapSpanToGraphemeBoundary, type CheckRequest, type CheckResponse, type Suggestion, type SuggestionType } from '@shuddho/shared';
import type { BanglaSuggestionProvider } from './types.js';

function createSuggestion(request: CheckRequest, provider: string, ruleId: string, type: SuggestionType, start: number, end: number, suggestedText: string, explanationBn: string, confidence = 0.86): Suggestion {
  const span = snapSpanToGraphemeBoundary(request.text, start, end);
  const originalText = request.text.slice(span.startIndex, span.endIndex);
  return {
    id: makeStableSuggestionId({ documentId: request.documentId, ruleId, type, startIndex: span.startIndex, endIndex: span.endIndex, originalText, suggestedText, provider }),
    suppressionKey: makeSuppressionKey({ ruleId, originalText, suggestedText, type }),
    ruleId, type,
    severity: type === 'spelling' ? 'high' : 'medium',
    originalText, suggestedText, replacementOptions: [suggestedText], explanationBn,
    explanationEn: 'Deterministic Bangla fallback suggestion.', span, confidence,
    source: type === 'spelling' ? 'spell' : 'rule', provider,
  };
}

export class LocalRuleProvider implements BanglaSuggestionProvider {
  readonly name = 'local-bangla-fallback';
  async check(request: CheckRequest, requestId = `local-${Date.now()}`): Promise<CheckResponse> {
    const suggestions: Suggestion[] = [];
    const text = request.text;
    for (const match of text.matchAll(/ {2,}/g)) {
      suggestions.push(createSuggestion(request, this.name, 'bn.spacing.repeated_spaces', 'spacing', match.index ?? 0, (match.index ?? 0) + match[0].length, ' ', 'একাধিক স্পেসের বদলে একটি স্পেস ব্যবহার করুন।', 0.98));
    }
    for (const match of text.matchAll(/(^|[\s।!?])([\u0980-\u09FF]+)\s+\2(?=$|[\s।!?])/gu)) {
      const start = (match.index ?? 0) + match[1].length;
      suggestions.push(createSuggestion(request, this.name, 'bn.grammar.duplicate_word', 'grammar', start, start + match[2].length * 2 + 1, match[2], 'একই শব্দ পরপর এসেছে; একটি শব্দ রাখাই যথেষ্ট হতে পারে।', 0.82));
    }
    for (const match of text.matchAll(/\s+।/g)) {
      suggestions.push(createSuggestion(request, this.name, 'bn.punctuation.space_before_dari', 'punctuation', match.index ?? 0, (match.index ?? 0) + match[0].length, '।', 'দাঁড়ির আগে স্পেস নয়।', 0.95));
    }
    for (const match of text.matchAll(/।(?=[\u0980-\u09FF])/gu)) {
      suggestions.push(createSuggestion(request, this.name, 'bn.punctuation.space_after_dari', 'punctuation', (match.index ?? 0), (match.index ?? 0) + 1, '। ', 'দাঁড়ির পরে সাধারণত একটি স্পেস দিন।', 0.88));
    }
    if (/^[\u0980-\u09FF\s,;:]+$/u.test(text.trim()) && !/[।!?]$/u.test(text.trim()) && text.trim().length > 12) {
      suggestions.push(createSuggestion(request, this.name, 'bn.punctuation.missing_sentence_end', 'punctuation', text.length, text.length, '।', 'বাংলা বাক্যের শেষে দাঁড়ি ব্যবহার করা যায়।', 0.66));
    }
    return { requestId, documentId: request.documentId, revision: request.revision, language: 'bn', normalizedText: text.normalize('NFC'), suggestions: suggestions.sort((a, b) => a.span.startIndex - b.span.startIndex), timings: { 'provider.local-bangla-fallback': 0 }, warnings: ['python_provider_unavailable_using_local_fallback'] };
  }
}
