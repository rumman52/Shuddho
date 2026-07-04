import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";

import App, {
  deriveBackendModeAfterSuccessfulCheck,
  deriveBackendModeFromHealth,
  describeAnalyzeTextError,
  normalizeShallowHealthAfterSuccessfulCheck,
} from "./App";

test("App renders editor shell when analysis runtime_warnings are missing from backend responses", () => {
  const html = renderToString(<App />);

  assert.match(html, /Bangla writing assistant/);
  assert.match(html, /Review queue/);
});

test("App renders editor shell without waiting for preferences", () => {
  const html = renderToString(<App />);

  assert.match(html, /Preferences/);
  assert.match(html, /Personal dictionary/);
});

test("App source keeps auto AI review enabled by default and deep review AI-enabled", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /const \[autoAiReview, setAutoAiReview\] = useState\(true\)/);
  assert.match(source, /void runAnalysis\(nextText, autoAiReview\)/);
  assert.match(source, /void runAnalysis\(text, true\)/);
  assert.match(source, /includeLLM,\n\s*asyncLLM: false,/);
  assert.match(source, /llmMode: includeLLM \? "review_candidates" : "none"/);
  assert.match(source, /mode: includeLLM \? "smart" : "fast"/);
});

test("App source exposes precise AI status messages and auto AI toggle", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /Auto AI review/);
  assert.match(source, /AI on every check/);
  assert.match(source, /friendlyLlmWarning/);
});


test("App source gates diagnostics and retests backend without user text", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /getLlmDebug/);
  assert.match(source, /Retest Backend/);
  assert.match(source, /Diagnostics/);
  assert.match(source, /debugMode \? \(/);
  assert.match(source, /await refreshBackendHealth\(\)/);
});


test("backend mode treats /health as reachability source of truth", () => {
  assert.equal(deriveBackendModeFromHealth(null, null), "unavailable");
  assert.equal(deriveBackendModeFromHealth({ ok: false }, null), "unavailable");
  assert.equal(
    deriveBackendModeFromHealth(
      { ok: true },
      { ok: true, corrector_loaded: false },
    ),
    "degraded",
  );
  assert.equal(
    deriveBackendModeFromHealth(
      { ok: true },
      { ok: true, corrector_loaded: true, detector_loaded: true },
    ),
    "ready",
  );
});


test("successful /api/check upgrades stale unavailable health to connected", () => {
  assert.deepEqual(normalizeShallowHealthAfterSuccessfulCheck(null), {
    ok: true,
    status: "ok",
  });
  assert.equal(deriveBackendModeAfterSuccessfulCheck(null, null), "connected");
  assert.equal(deriveBackendModeAfterSuccessfulCheck({ ok: false }, null), "connected");
});

test("successful /api/check still respects available deep health readiness", () => {
  assert.equal(
    deriveBackendModeAfterSuccessfulCheck(null, { ok: true, corrector_loaded: true, detector_loaded: true }),
    "ready",
  );
  assert.equal(
    deriveBackendModeAfterSuccessfulCheck(null, { ok: true, corrector_loaded: false, detector_loaded: true }),
    "degraded",
  );
});

test("App source clears stale unavailable banner after successful /api/check", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /apiCheckReachableRef\.current = true/);
  assert.match(source, /normalizeShallowHealthAfterSuccessfulCheck\(\s*shallowHealth,\s*\)/);
  assert.match(source, /setBackendHealthDiagnostic\(null\)/);
  assert.match(source, /deriveBackendModeAfterSuccessfulCheck\(\s*checkReachableHealth,\s*backendHealth,\s*\)/);
  assert.match(source, /setBackendMode\("connected"\)/);
});

test("App source checks /health before /health/deep and keeps deep failure degraded", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /health = await getHealth\(\)/);
  assert.match(source, /const deepHealth = await getHealthDeep\(\)/);
  assert.doesNotMatch(source, /Promise\.allSettled\(\[\s*getHealth\(\),\s*getHealthDeep\(\)/);
  assert.match(source, /setBackendMode\("degraded"\)/);
  assert.match(source, /Backend connected, but deep health check is degraded or still warming up\./);
});

test("App source exposes production backend debug strip outside debug mode", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /production-debug-line/);
  assert.match(source, /API base URL:/);
  assert.match(source, /API config source:/);
  assert.match(source, /backendMode:/);
  assert.match(source, /last health error:/);
  assert.match(source, /last \/api\/check:/);
});

test("timeout errors map to friendly user-facing messages", () => {
  assert.equal(
    describeAnalyzeTextError(
      "Backend timeout for https://api.example.test/api/check after 30000ms",
      false,
    ),
    "Request timed out. Please try again or check backend deployment.",
  );
  assert.equal(
    describeAnalyzeTextError(
      "Backend timeout for https://api.example.test/api/check after 60000ms",
      true,
    ),
    "AI review timed out. Showing local suggestions.",
  );
});

test("App source exposes precise /api/check error messages and reset override button", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /Browser could not reach backend\. Check CORS and VITE_API_BASE_URL\./);
  assert.match(source, /Backend route \/api\/check was not found\./);
  assert.match(source, /Backend validation failed\. Request payload does not match \/api\/check schema\./);
  assert.match(source, /Backend crashed during analysis\. Check Render logs\./);
  assert.match(source, /AI review timed out\. Showing local suggestions\./);
  assert.match(source, /Reset API URL override/);
});
