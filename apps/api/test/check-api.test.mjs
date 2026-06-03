import assert from 'node:assert/strict';
import { createServer } from 'node:http';

const originalEnv = { ...process.env };
process.env.SHUDDHO_NLP_PROVIDER = 'python';
process.env.SHUDDHO_ENABLE_LOCAL_FALLBACK = 'true';
process.env.SHUDDHO_ALLOWED_ORIGINS = 'http://localhost:5173,http://127.0.0.1:5173,https://shuddho-web-editor.vercel.app';
process.env.SHUDDHO_ALLOW_VERCEL_PREVIEWS = 'false';
process.env.NODE_ENV = 'production';

const { createApp } = await import('../dist/app.js');

function listen(handler) {
  const server = createServer(handler).listen(0);
  return new Promise((resolve) => server.once('listening', () => resolve(server)));
}

function close(server) {
  return new Promise((resolve, reject) => server.close((err) => err ? reject(err) : resolve()));
}

const analyzeRequests = [];
const feedbackRequests = [];
const pythonServer = await listen((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
    return;
  }
  if (req.url === '/health/deep') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({
      status: 'ok',
      backend_reachable: true,
      detector_loaded: true,
      detector_checkpoint: 'artifacts/detector/detector-base',
      corrector_loaded: false,
      corrector_checkpoint: 'artifacts/corrector/corrector-base',
      detector: { loaded: true, status: 'ready' },
      corrector: { loaded: false, status: 'missing_checkpoint' },
      analysis_profile: 'backend_without_corrector',
      degraded_reasons: ['corrector_missing_checkpoint'],
    }));
    return;
  }
  if (req.url === '/analyze' && req.method === 'POST') {
    let raw = '';
    req.on('data', (chunk) => { raw += chunk; });
    req.on('end', () => {
      const body = JSON.parse(raw || '{}');
      analyzeRequests.push(body);
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({
        text: body.text,
        normalized_text: body.text,
        corrected_text: body.text,
        suggestions: [],
        warnings: [],
      }));
    });
    return;
  }
  if (req.url === '/feedback' && req.method === 'POST') {
    let raw = '';
    req.on('data', (chunk) => { raw += chunk; });
    req.on('end', () => {
      const body = JSON.parse(raw || '{}');
      feedbackRequests.push(body);
      if (body.action === 'dismissed') {
        res.writeHead(422, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: 'invalid_feedback' }));
        return;
      }
      res.writeHead(201, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ id: 42, ...body }));
    });
    return;
  }
  res.writeHead(404);
  res.end();
});
const pythonPort = pythonServer.address().port;
process.env.SHUDDHO_PYTHON_API_URL = `http://127.0.0.1:${pythonPort}`;

let server = await listen(createApp());
let port = server.address().port;

let response = await fetch(`http://127.0.0.1:${port}/health`);
assert.equal(response.status, 200);
let body = await response.json();
assert.equal(body.ok, true);
assert.equal(body.provider, 'python-bangla');

response = await fetch(`http://127.0.0.1:${port}/ready`);
assert.equal(response.status, 200);
body = await response.json();
assert.equal(body.ok, true);

response = await fetch(`http://127.0.0.1:${port}/health/deep`);
assert.equal(response.status, 200);
body = await response.json();
assert.equal(body.ok, true);
assert.equal(body.service, 'shuddho-api');
assert.equal(body.provider, 'python-bangla');
assert.equal(body.backend_reachable, true);
assert.equal(body.analysis_profile, 'backend_without_corrector');
assert.equal(body.detector.status, 'ready');
assert.equal(body.corrector.status, 'missing_checkpoint');

response = await fetch(`http://127.0.0.1:${port}/api/check`, {
  method: 'POST',
  headers: { 'content-type': 'application/json', origin: 'https://shuddho-web-editor.vercel.app' },
  body: JSON.stringify({ text: 'আমি  আমি ভাত খাই।', language: 'bn', revision: 1, client: { surface: 'api' } }),
});
assert.equal(response.status, 200);
assert.equal(response.headers.get('access-control-allow-origin'), 'https://shuddho-web-editor.vercel.app');
body = await response.json();
assert.equal(body.requestId.length > 0, true);
assert.equal(body.language, 'bn');
assert.equal(analyzeRequests.length, 1);
assert.equal(analyzeRequests[0].text, 'আমি  আমি ভাত খাই।');
assert.equal(analyzeRequests[0].mode, 'standard');

const fullFeedbackPayload = {
  suggestion_id: 'SUGG_1',
  action: 'accepted',
  text: 'আমি ভাত খাই',
  replacement: 'খাই।',
  feedback_key: 'fbk-1',
  rule_id: 'bn.rule',
  subtype: 'spelling',
  source: 'rule',
  original_text: 'খাই',
  user_id: 'u-1',
};
response = await fetch(`http://127.0.0.1:${port}/api/feedback`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify(fullFeedbackPayload),
});
assert.equal(response.status, 201);
body = await response.json();
assert.equal(body.suggestion_id, 'SUGG_1');
assert.deepEqual(feedbackRequests[0], fullFeedbackPayload);

response = await fetch(`http://127.0.0.1:${port}/api/feedback`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ ...fullFeedbackPayload, action: 'dismissed' }),
});
assert.equal(response.status, 422);
body = await response.json();
assert.equal(body.error, 'feedback_forward_failed');
assert.equal(body.upstreamStatus, 422);

response = await fetch(`http://127.0.0.1:${port}/api/check`, {
  method: 'OPTIONS',
  headers: { origin: 'https://shuddho-web-editor.vercel.app', 'access-control-request-method': 'POST' },
});
assert.equal(response.status, 204);
assert.equal(response.headers.get('access-control-allow-origin'), 'https://shuddho-web-editor.vercel.app');

response = await fetch(`http://127.0.0.1:${port}/api/check`, {
  method: 'OPTIONS',
  headers: { origin: 'https://evil.example', 'access-control-request-method': 'POST' },
});
assert.equal(response.status, 403);
body = await response.json();
assert.equal(body.error, 'cors_origin_not_allowed');

response = await fetch(`http://127.0.0.1:${port}/health`, {
  headers: { origin: 'https://evil.example' },
});
assert.equal(response.status, 403);
body = await response.json();
assert.equal(body.error, 'cors_origin_not_allowed');

await close(server);
await close(pythonServer);

process.env.SHUDDHO_PYTHON_API_URL = 'http://127.0.0.1:1';
server = await listen(createApp());
port = server.address().port;
response = await fetch(`http://127.0.0.1:${port}/ready`);
assert.equal(response.status, 503);
body = await response.json();
assert.equal(body.ok, false);

response = await fetch(`http://127.0.0.1:${port}/health/deep`);
assert.equal(response.status, 200);
body = await response.json();
assert.equal(body.ok, true);
assert.equal(body.backend_reachable, false);
assert.equal(body.analysis_profile, 'frontend_local_fallback');
assert.ok(body.degraded_reasons.some((reason) => String(reason).includes('primary_provider_unreachable:python-bangla')));

response = await fetch(`http://127.0.0.1:${port}/api/check`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ text: 'আমি  আমি ভাত খাই ।বাংলা ভাষা সুন্দর', language: 'bn', revision: 1, client: { surface: 'api' } }),
});
assert.equal(response.status, 200);
body = await response.json();
assert.ok(body.suggestions.some((s) => s.ruleId === 'bn.spacing.repeated_spaces'));
assert.ok(body.suggestions.some((s) => s.ruleId === 'bn.grammar.duplicate_word'));
assert.ok(body.warnings.some((w) => String(w).includes('primary_provider_failed:python-bangla')));

await close(server);
process.env = originalEnv;
console.log('API gateway tests passed');
