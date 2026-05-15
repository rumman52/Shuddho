import type { BanglaSuggestionProvider } from './types.js';
import type { CheckRequest, CheckResponse } from '@shuddho/shared';
export class MockLLMProvider implements BanglaSuggestionProvider {
  readonly name = 'mock-llm-disabled';
  async check(request: CheckRequest, requestId = `local-${Date.now()}`): Promise<CheckResponse> {
    return { requestId, documentId: request.documentId, revision: request.revision, language: 'bn', suggestions: [], timings: {}, warnings: ['mock_llm_not_used_for_bangla_product_path'] };
  }
  async rewrite(text: string): Promise<unknown> { return { originalText: text, rewrittenText: text, warnings: ['mock_llm_disabled'] }; }
}
