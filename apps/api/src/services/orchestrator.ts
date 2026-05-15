import type { CheckRequest, CheckResponse, Suggestion } from '@shuddho/shared';
import { LocalRuleProvider, MockLLMProvider, type SuggestionProvider } from '@shuddho/nlp';
import { measure } from '@shuddho/observability';
import { applyDlpPlaceholder } from './privacy.js';

export class SuggestionOrchestrator {
  constructor(private providers: SuggestionProvider[] = [new LocalRuleProvider(), new MockLLMProvider()]) {}

  async check(input: CheckRequest, requestId: string): Promise<CheckResponse> {
    const { safeText } = applyDlpPlaceholder(input.text);
    const timings: Record<string, number> = {};
    const batches = await Promise.all(this.providers.map(async (provider) => {
      const result = await measure(provider.name, () => provider.check(safeText, {
        requestId,
        locale: input.locale,
        goals: input.goals,
      }));
      timings[`provider.${result.name}`] = result.durationMs;
      return result.value;
    }));
    const suggestions = this.dedupe(batches.flat());
    timings.totalSuggestions = suggestions.length;
    return { requestId, documentId: input.documentId, revision: input.revision, suggestions, timings };
  }

  private dedupe(suggestions: Suggestion[]): Suggestion[] {
    const seen = new Set<string>();
    return suggestions.filter((suggestion) => {
      const key = `${suggestion.type}:${suggestion.startIndex}:${suggestion.endIndex}:${suggestion.suggestedText}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
}
