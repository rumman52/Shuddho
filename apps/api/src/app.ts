import { IncomingMessage, ServerResponse } from 'node:http';
import { randomUUID } from 'node:crypto';
import { parseCheckRequest, parseEventRequest, parseRewriteRequest, parseToneRequest } from '@shuddho/shared';
import { logger } from '@shuddho/observability';
import { SuggestionOrchestrator } from './services/orchestrator.js';
import { InMemoryEventSink } from './services/events.js';
import { DocumentStore } from './services/documents.js';

export interface AppDeps { orchestrator: SuggestionOrchestrator; events: InMemoryEventSink; documents: DocumentStore; }
export interface ShuddhoHandler { (req: IncomingMessage, res: ServerResponse): void; locals: { documents: DocumentStore }; }

async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: unknown[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  const raw = Buffer.concat(chunks).toString('utf8') || '{}';
  if (raw.length > 262_144) throw new Error('payload_too_large');
  return JSON.parse(raw);
}

function send(res: ServerResponse, status: number, body: unknown, requestId: string) {
  res.statusCode = status;
  res.setHeader('content-type', 'application/json');
  res.setHeader('x-request-id', requestId);
  res.setHeader('access-control-allow-origin', process.env.CORS_ORIGIN ?? 'http://localhost:3000');
  res.setHeader('access-control-allow-headers', 'content-type, authorization, x-request-id, x-user-id, x-tenant-id');
  res.end(JSON.stringify(body));
}

export function createApp(deps: AppDeps = { orchestrator: new SuggestionOrchestrator(), events: new InMemoryEventSink(), documents: new DocumentStore() }): ShuddhoHandler {
  const handler = (async (req: IncomingMessage, res: ServerResponse) => {
    const requestId = req.headers['x-request-id']?.toString() ?? randomUUID();
    const start = performance.now();
    try {
      if (req.method === 'OPTIONS') return send(res, 204, {}, requestId);
      const url = new URL(req.url ?? '/', 'http://localhost');
      const path = url.pathname;
      if (req.method === 'GET' && path === '/health') return send(res, 200, { ok: true, service: 'shuddho-api' }, requestId);
      if (req.method === 'GET' && path === '/ready') return send(res, (await deps.orchestrator.ready()) ? 200 : 503, { ok: await deps.orchestrator.ready(), provider: deps.orchestrator.providerName() }, requestId);
      if (req.method === 'GET' && path === '/metrics') { res.statusCode = 200; res.setHeader('content-type', 'text/plain'); return res.end('# metrics placeholder\nshuddho_api_up 1\n'); }

      if (req.method === 'POST' && path === '/api/check') {
        const input = parseCheckRequest(await readJson(req));
        const response = await deps.orchestrator.check(input, requestId);
        await deps.events.record([{ type: 'suggestion_generated', language: 'bn', documentId: input.documentId, metadata: { count: response.suggestions.length, textLength: input.text.length, provider: deps.orchestrator.providerName() } }], { requestId, userId: 'demo-user' });
        return send(res, 200, response, requestId);
      }
      if (req.method === 'POST' && path === '/api/rewrite') {
        const input = parseRewriteRequest(await readJson(req));
        const result = await deps.orchestrator.rewrite(input.text, input);
        await deps.events.record([{ type: 'rewrite_requested', language: 'bn', metadata: { textLength: input.text.length } }], { requestId, userId: 'demo-user' });
        return send(res, 200, { requestId, result }, requestId);
      }
      if (req.method === 'POST' && path === '/api/tone') {
        const input = parseToneRequest(await readJson(req));
        const result = await deps.orchestrator.tone(input.text);
        await deps.events.record([{ type: 'tone_requested', language: 'bn', metadata: { textLength: input.text.length } }], { requestId, userId: 'demo-user' });
        return send(res, 200, { requestId, result }, requestId);
      }
      if (req.method === 'GET' && path === '/api/preferences') return send(res, 200, { userId: 'demo-user', language: 'bn', dialect: 'standard', enabledSuggestionTypes: ['grammar', 'spelling', 'spacing', 'punctuation', 'style', 'tone'], productImprovementConsent: false }, requestId);
      if (req.method === 'PUT' && path === '/api/preferences') { const body = await readJson(req) as Record<string, unknown>; return send(res, 200, { ...body, language: 'bn', saved: true }, requestId); }
      if (req.method === 'POST' && path === '/api/events') {
        const input = parseEventRequest(await readJson(req));
        await deps.events.record(input.events, { requestId, userId: 'demo-user' });
        return send(res, 202, { requestId, accepted: input.events.length }, requestId);
      }
      const docMatch = path.match(/^\/api\/documents\/([^/]+)$/);
      if (docMatch && req.method === 'GET') {
        const document = deps.documents.get(decodeURIComponent(docMatch[1]));
        return document ? send(res, 200, { requestId, document }, requestId) : send(res, 404, { error: 'not_found', requestId }, requestId);
      }
      if (docMatch && req.method === 'PUT') {
        const body = await readJson(req) as Record<string, unknown>;
        const document = deps.documents.save({ id: decodeURIComponent(docMatch[1]), ownerId: 'demo-user', title: String(body.title ?? 'Untitled draft').slice(0, 120), text: String(body.text ?? body.plainText ?? '').slice(0, 50000), plainText: String(body.text ?? body.plainText ?? '').slice(0, 50000), revision: Number(body.revision ?? 0) + 1, updatedAt: new Date().toISOString() });
        return send(res, 200, { requestId, document }, requestId);
      }
      return send(res, 404, { error: 'not_found', requestId }, requestId);
    } catch (error) {
      logger.error({ err: String(error), requestId }, 'request failed');
      return send(res, 400, { error: 'bad_request', requestId }, requestId);
    } finally {
      logger.info({ requestId, method: req.method, path: req.url, latencyMs: Math.round(performance.now() - start) }, 'request complete');
    }
  }) as unknown as ShuddhoHandler;
  handler.locals = { documents: deps.documents };
  return handler;
}
