import type { Suggestion } from '@shuddho/shared';
import type { RewriteProvider, SuggestionContext, SuggestionProvider } from './types.js';

export class MockLLMProvider implements SuggestionProvider, RewriteProvider {
  readonly name = 'MockLLMProvider';

  async check(text: string, context: SuggestionContext): Promise<Suggestion[]> {
    if (!context.goals.includes('rewrite') || text.trim().length < 24) return [];
    const cleaner = this.clean(text);
    if (cleaner === text) return [];
    return [{
      id: `${context.requestId}:rewrite:0:mock`,
      type: 'rewrite',
      severity: 'info',
      originalText: text.slice(0, 160),
      suggestedText: cleaner,
      explanation: 'Mock rewrite provider created a clearer, more concise version.',
      startIndex: 0,
      endIndex: text.length,
      confidence: 0.7,
      sourceProvider: this.name,
    }];
  }

  async rewrite(text: string, instruction = 'improve clarity'): Promise<Suggestion[]> {
    return [{
      id: `rewrite:${Date.now()}`,
      type: 'rewrite',
      severity: 'info',
      originalText: text,
      suggestedText: this.clean(text),
      explanation: `Mock rewrite generated for: ${instruction}`,
      startIndex: 0,
      endIndex: text.length,
      confidence: 0.72,
      sourceProvider: this.name,
    }];
  }

  private clean(text: string): string {
    return text
      .replace(/\bteh\b/gi, 'the')
      .replace(/\brecieve\b/gi, 'receive')
      .replace(/\bI has\b/g, 'I have')
      .replace(/\bin order to\b/gi, 'to')
      .replace(/\bdue to the fact that\b/gi, 'because')
      .replace(/ {2,}/g, ' ')
      .trim();
  }
}

export class FutureOpenAIProvider implements SuggestionProvider {
  readonly name = 'FutureOpenAIProvider';
  async check(): Promise<Suggestion[]> { return []; }
}

export class FutureOnDeviceProvider implements SuggestionProvider {
  readonly name = 'FutureOnDeviceProvider';
  async check(): Promise<Suggestion[]> { return []; }
}
