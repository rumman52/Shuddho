import { LocalRuleProvider } from '@shuddho/nlp';
import type { CheckRequest, CheckResponse } from '@shuddho/shared';
import type { BanglaSuggestionProvider } from './BanglaProvider.js';
export class LocalFallbackBanglaProvider implements BanglaSuggestionProvider {
  readonly name = 'local-bangla-fallback';
  private inner = new LocalRuleProvider();
  async check(request: CheckRequest, requestId: string): Promise<CheckResponse> { return this.inner.check(request, requestId); }
  async rewrite(text: string): Promise<unknown> { return { originalText: text, rewrittenText: text, warnings: ['local_fallback_rewrite_not_available'] }; }
  async tone(text: string): Promise<unknown> { return { primaryTone: 'neutral', confidence: 0.5, textLength: text.length, warnings: ['local_fallback_tone_limited'] }; }
  async ready(): Promise<boolean> { return true; }
}
