import type { CheckRequest, CheckResponse } from '@shuddho/shared';
import { logger, measure } from '@shuddho/observability';
import { applyDlpPlaceholder } from './privacy.js';
import type { BanglaSuggestionProvider } from '../providers/BanglaProvider.js';
import { PythonBanglaProvider } from '../providers/PythonBanglaProvider.js';
import { LocalFallbackBanglaProvider } from '../providers/LocalFallbackBanglaProvider.js';

export class SuggestionOrchestrator {
  constructor(
    private primary: BanglaSuggestionProvider = process.env.SHUDDHO_NLP_PROVIDER === 'local' ? new LocalFallbackBanglaProvider() : new PythonBanglaProvider(),
    private fallback: BanglaSuggestionProvider | null = process.env.SHUDDHO_ENABLE_LOCAL_FALLBACK === 'false' ? null : new LocalFallbackBanglaProvider(),
  ) {}

  providerName(): string { return this.primary.name; }
  async ready(): Promise<boolean> { return this.primary.ready ? this.primary.ready() : true; }

  async check(input: CheckRequest, requestId: string): Promise<CheckResponse> {
    const { safeText } = applyDlpPlaceholder(input.text);
    const safeRequest = { ...input, text: safeText };
    try {
      const result = await measure(this.primary.name, () => this.primary.check(safeRequest, requestId));
      result.value.timings = { ...(result.value.timings ?? {}), [`provider.${this.primary.name}`]: result.durationMs };
      return result.value;
    } catch (error) {
      logger.warn({ requestId, provider: this.primary.name, textLength: input.text.length, error: error instanceof Error ? error.message : 'unknown' }, 'primary bangla provider failed');
      if (!this.fallback) throw error;
      const result = await measure(this.fallback.name, () => this.fallback!.check(input, requestId));
      result.value.warnings = [...(result.value.warnings ?? []), `primary_provider_failed:${this.primary.name}`];
      result.value.timings = { ...(result.value.timings ?? {}), [`provider.${this.fallback.name}`]: result.durationMs };
      return result.value;
    }
  }
  async rewrite(text: string, options?: unknown): Promise<unknown> { return (this.primary.rewrite ?? this.fallback?.rewrite)?.call(this.primary, text, options) ?? { originalText: text, rewrittenText: text }; }
  async tone(text: string, options?: unknown): Promise<unknown> { return (this.primary.tone ?? this.fallback?.tone)?.call(this.primary, text, options) ?? { primaryTone: 'neutral' }; }
}
