import { legacyAnalyzeToCheckResponse, type CheckRequest, type CheckResponse } from '@shuddho/shared';
import type { BanglaSuggestionProvider } from './BanglaProvider.js';

export class PythonBanglaProvider implements BanglaSuggestionProvider {
  readonly name = 'python-bangla';
  private readonly timeoutMs: number;

  constructor(private baseUrl = process.env.SHUDDHO_PYTHON_API_URL ?? 'http://127.0.0.1:8000') {
    const configuredTimeoutMs = Number(process.env.SHUDDHO_PROVIDER_TIMEOUT_MS ?? 25000);
    this.timeoutMs = Number.isFinite(configuredTimeoutMs) && configuredTimeoutMs > 0 ? configuredTimeoutMs : 25000;
  }

  private async fetchWithTimeout(url: string, init: RequestInit = {}): Promise<Response> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('python_timeout');
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  async ready(): Promise<boolean> {
    try { const res = await this.fetchWithTimeout(`${this.baseUrl}/health`); return res.ok; } catch { return false; }
  }

  async healthDeep(): Promise<unknown> {
    const res = await this.fetchWithTimeout(`${this.baseUrl}/health/deep`, { headers: { accept: 'application/json' } });
    if (!res.ok) throw new Error(`python_health_deep_${res.status}`);
    return res.json();
  }

  async check(request: CheckRequest, requestId: string): Promise<CheckResponse> {
    const started = Date.now();
    const payload = {
      text: request.text,
      language: 'bn',
      documentId: request.documentId,
      revision: request.revision,
      dialect: request.dialect,
      userId: request.userId,
      client: request.client,
      options: request.options,
      consent: request.consent,
    };

    let res = await this.fetchWithTimeout(`${this.baseUrl}/api/check`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload),
    });

    if (res.status === 404) {
      res = await this.fetchWithTimeout(`${this.baseUrl}/analyze`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ text: request.text, mode: 'standard', user_id: request.userId }),
      });
    }

    if (!res.ok) throw new Error(`python_check_${res.status}`);
    const json = await res.json();
    const response = (json && typeof json === 'object' && Array.isArray((json as CheckResponse).suggestions) && typeof (json as CheckResponse).requestId === 'string')
      ? ({ ...(json as CheckResponse), requestId } as CheckResponse)
      : legacyAnalyzeToCheckResponse(json, { requestId, text: request.text, documentId: request.documentId, revision: request.revision, provider: this.name });
    response.requestId = requestId;
    response.timings = { ...(response.timings ?? {}), 'provider.python-bangla': Date.now() - started };
    return response;
  }

  async rewrite(text: string, options?: any): Promise<unknown> {
    const res = await this.fetchWithTimeout(`${this.baseUrl}/rewrite`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, selection_start: options?.selectionStart, selection_end: options?.selectionEnd, intent: options?.intent ?? 'clarity' }) });
    if (!res.ok) throw new Error(`python_rewrite_${res.status}`);
    return res.json();
  }
  async tone(text: string, options?: unknown): Promise<unknown> {
    const res = await this.fetchWithTimeout(`${this.baseUrl}/tone/analyze`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, ...(options && typeof options === 'object' ? options : {}) }) });
    if (!res.ok) throw new Error(`python_tone_${res.status}`);
    return res.json();
  }
}
