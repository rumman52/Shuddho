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

  async healthDeep(): Promise<unknown> {
    if (this.primary.healthDeep) {
      try {
        return await this.primary.healthDeep();
      } catch (error) {
        logger.warn({ provider: this.primary.name, error: error instanceof Error ? error.message : 'unknown' }, 'primary bangla provider deep health failed');
      }
    }

    return {
      status: this.fallback ? 'degraded' : 'unavailable',
      backend_reachable: false,
      provider: this.primary.name,
      fallback_provider: this.fallback?.name ?? null,
      detector_loaded: false,
      detector_checkpoint: null,
      corrector_loaded: false,
      corrector_checkpoint: null,
      detector: { enabled: false, loaded: false, status: 'unavailable', reason: `Primary provider ${this.primary.name} is not reachable from the gateway.`, checkpoint: null, checkpoint_exists: false, backend_name: 'unavailable', threshold: 0 },
      corrector: { enabled: false, loaded: false, status: 'unavailable', reason: `Primary provider ${this.primary.name} is not reachable from the gateway.`, checkpoint: null, checkpoint_exists: false, backend_name: 'unavailable', threshold: 0 },
      analysis_profile: this.fallback ? 'frontend_local_fallback' : 'backend_rules_and_spell_only',
      degraded_reasons: [`primary_provider_unreachable:${this.primary.name}`],
      backend_warning: this.fallback
        ? `Python backend is not reachable at the gateway; using ${this.fallback.name} rules-only fallback.`
        : 'Python backend is not reachable and local fallback is disabled.',
      mode_capabilities: { standard: ['gateway_online', this.fallback ? 'local_fallback_rules' : 'provider_unavailable'] },
    };
  }

  async check(input: CheckRequest, requestId: string): Promise<CheckResponse> {
    const { safeText } = applyDlpPlaceholder(input.text);
    const safeRequest = { ...input, text: safeText };
    try {
      const result = await measure(this.primary.name, () => this.primary.check(safeRequest, requestId));
      result.value.timings = { ...(result.value.timings ?? {}), [`provider.${this.primary.name}`]: result.durationMs };
      return result.value;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'unknown';
      logger.warn({ requestId, provider: this.primary.name, textLength: input.text.length, error: errorMessage }, 'primary bangla provider failed');
      if (!this.fallback) {
        return {
          requestId,
          documentId: input.documentId,
          revision: input.revision,
          language: 'bn',
          normalizedText: input.text,
          correctedText: input.text,
          documentAssessment: {},
          suggestions: [],
          timings: { [`provider.${this.primary.name}`]: 0 },
          warnings: [`primary_provider_failed:${this.primary.name}`, errorMessage === 'python_timeout' ? 'python_provider_timeout' : 'python_provider_unavailable'],
          llm_requested: Boolean(input.options?.includeLLM),
          llm_attempted: false,
          llm_used: false,
          llm_status: 'skipped',
          llm_provider: null,
          llm_model: null,
          llm_response_mode: null,
          llm: { status: 'skipped', warnings: [errorMessage], attempted: false },
          local_suggestion_count: 0,
          ai_suggestion_count: 0,
          rejected_ai_suggestion_count: 0,
          diagnostics: { provider: { status: 'degraded', error: errorMessage } },
        };
      }
      const result = await measure(this.fallback.name, () => this.fallback!.check(input, requestId));
      result.value.warnings = [...(result.value.warnings ?? []), `primary_provider_failed:${this.primary.name}`];
      result.value.timings = { ...(result.value.timings ?? {}), [`provider.${this.fallback.name}`]: result.durationMs };
      return result.value;
    }
  }
  async rewrite(text: string, options?: unknown): Promise<unknown> { return (this.primary.rewrite ?? this.fallback?.rewrite)?.call(this.primary, text, options) ?? { originalText: text, rewrittenText: text }; }
  async tone(text: string, options?: unknown): Promise<unknown> { return (this.primary.tone ?? this.fallback?.tone)?.call(this.primary, text, options) ?? { primaryTone: 'neutral' }; }
}
