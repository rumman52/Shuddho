import { legacyAnalyzeToCheckResponse, type CheckRequest, type CheckResponse } from '@shuddho/shared';
import type { BanglaSuggestionProvider } from './BanglaProvider.js';

export class PythonBanglaProvider implements BanglaSuggestionProvider {
  readonly name = 'python-bangla';
  constructor(private baseUrl = process.env.SHUDDHO_PYTHON_API_URL ?? 'http://127.0.0.1:8000') {}

  async ready(): Promise<boolean> {
    try { const res = await fetch(`${this.baseUrl}/health`); return res.ok; } catch { return false; }
  }

  async healthDeep(): Promise<unknown> {
    const res = await fetch(`${this.baseUrl}/health/deep`, { headers: { accept: 'application/json' } });
    if (!res.ok) throw new Error(`python_health_deep_${res.status}`);
    return res.json();
  }

  async check(request: CheckRequest, requestId: string): Promise<CheckResponse> {
    const started = Date.now();
    const res = await fetch(`${this.baseUrl}/analyze`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ text: request.text, mode: 'standard', user_id: request.userId }),
    });
    if (!res.ok) throw new Error(`python_analyze_${res.status}`);
    const json = await res.json();
    const response = legacyAnalyzeToCheckResponse(json, { requestId, text: request.text, documentId: request.documentId, revision: request.revision, provider: this.name });
    response.timings = { ...(response.timings ?? {}), 'provider.python-bangla': Date.now() - started };
    return response;
  }

  async rewrite(text: string, options?: any): Promise<unknown> {
    const res = await fetch(`${this.baseUrl}/rewrite`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, selection_start: options?.selectionStart, selection_end: options?.selectionEnd, intent: options?.intent ?? 'clarity' }) });
    if (!res.ok) throw new Error(`python_rewrite_${res.status}`);
    return res.json();
  }
  async tone(text: string, options?: unknown): Promise<unknown> {
    const res = await fetch(`${this.baseUrl}/tone/analyze`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, ...(options && typeof options === 'object' ? options : {}) }) });
    if (!res.ok) throw new Error(`python_tone_${res.status}`);
    return res.json();
  }
}
