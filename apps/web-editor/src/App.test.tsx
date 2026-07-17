import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToString } from "react-dom/server.browser";

import App, {
  applySafeSuggestionBatch,
  deriveBackendModeAfterSuccessfulCheck,
  deriveBackendModeFromHealth,
  describeAnalyzeTextError,
  normalizeShallowHealthAfterSuccessfulCheck,
} from "./App";
import type { Suggestion } from "@shared/schemas/contracts";
import { analyzeText, setApiBaseUrlOverride } from "./lib/api";

function suggestion(
  id: string,
  start: number,
  end: number,
  original: string,
  replacement: string,
): Suggestion {
  return {
    id,
    rule_id: id,
    category: "spelling",
    subtype: "test",
    span_start: start,
    span_end: end,
    original_text: original,
    replacement_options: [replacement],
    confidence: 0.9,
    explanation_bn: "পরীক্ষা",
    explanation_en: "test",
    source: "rule",
    severity: "low",
  };
}

test("App renders the professional writing workspace without waiting for backend data", () => {
  const html = renderToString(<App />);

  assert.match(html, /Shuddho/);
  assert.match(html, /Bangla Writing Assistant/);
  assert.match(html, /Write in Bangla with context-aware review/);
  assert.match(html, /Review suggestions/);
  assert.match(html, /Apply safe suggestions/);
});

test("App keeps advanced settings and diagnostics outside the normal workspace", () => {
  const html = renderToString(<App />);

  assert.match(html, /Settings/);
  assert.match(html, /Writing goal/);
  assert.doesNotMatch(html, /Developer diagnostics/);
});

test("App source keeps auto AI review off by default and deep review AI-enabled", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(
    source,
    /const \[autoAiReview, setAutoAiReview\] = useState\(false\)/,
  );
  assert.match(source, /enqueueAnalysis\(nextText, includeLLM, false\)/);
  assert.match(source, /enqueueAnalysis\(text, true, true\)/);
  assert.match(source, /includeLLM,\n\s*asyncLLM: false,/);
  assert.match(source, /llmMode: includeLLM \? "review_candidates" : "none"/);
  assert.match(source, /mode: includeLLM \? "smart" : "fast"/);
});

test("App source exposes friendly AI status messages and auto AI toggle", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /Auto AI review/);
  assert.match(source, /AI review ready/);
  assert.match(source, /friendlyLlmWarning/);
});

test("App source gates diagnostics and retests backend without user text", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /getLlmDebug/);
  assert.match(source, /Retry backend/);
  assert.match(source, /Developer diagnostics/);
  assert.match(source, /debugMode \|\|/);
  assert.match(source, /await refreshBackendHealth\(\)/);
});

test("safe suggestion application skips stale and overlapping edits", () => {
  const result = applySafeSuggestionBatch("কিন্ত বাংলা বাংলা", [
    suggestion("one", 0, 5, "কিন্ত", "কিন্তু"),
    suggestion("overlap", 0, 8, "কিন্ত বা", "x"),
    suggestion("stale", 6, 11, "বংলা", "বাংলা"),
    suggestion("two", 12, 17, "বাংলা", "ভাষা"),
  ]);

  assert.equal(result.text, "কিন্তু বাংলা ভাষা");
  assert.equal(result.applied, 2);
  assert.equal(result.skipped, 2);
  assert.deepEqual(result.appliedIds.sort(), ["one", "two"]);
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
  assert.equal(
    deriveBackendModeAfterSuccessfulCheck({ ok: false }, null),
    "connected",
  );
});

test("successful /api/check still respects available deep health readiness", () => {
  assert.equal(
    deriveBackendModeAfterSuccessfulCheck(null, {
      ok: true,
      corrector_loaded: true,
      detector_loaded: true,
    }),
    "ready",
  );
  assert.equal(
    deriveBackendModeAfterSuccessfulCheck(null, {
      ok: true,
      corrector_loaded: false,
      detector_loaded: true,
    }),
    "degraded",
  );
});

test("App source clears stale unavailable banner after successful /api/check", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /apiCheckReachableRef\.current = true/);
  assert.match(
    source,
    /normalizeShallowHealthAfterSuccessfulCheck\(\s*shallowHealth/,
  );
  assert.match(source, /setBackendHealthDiagnostic\(null\)/);
  assert.match(
    source,
    /deriveBackendModeAfterSuccessfulCheck\(\s*checkReachableHealth,\s*backendHealth/,
  );
});

test("App source checks /health before /health/deep and keeps deep failure degraded", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /health = await getHealth\(\)/);
  assert.match(source, /const deepHealth = await getHealthDeep\(\)/);
  assert.doesNotMatch(
    source,
    /Promise\.allSettled\(\[\s*getHealth\(\),\s*getHealthDeep\(\)/,
  );
  assert.match(source, /setBackendMode\("degraded"\)/);
  assert.match(
    source,
    /Backend connected, but deep health check is degraded or still warming up\./,
  );
});

test("App source exposes production backend debug strip outside debug mode without raw secrets", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /production-debug-line/);
  assert.match(source, /API base URL:/);
  assert.match(source, /API config source:/);
  assert.match(source, /backendMode:/);
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
  assert.match(
    source,
    /Browser could not reach backend\. Check CORS and VITE_API_BASE_URL\./,
  );
  assert.match(source, /Backend route \/api\/check was not found\./);
  assert.match(
    source,
    /Backend validation failed\. Request payload does not match \/api\/check schema\./,
  );
  assert.match(source, /Backend crashed during analysis\. Check Render logs\./);
  assert.match(source, /AI review timed out\. Showing local suggestions\./);
  assert.match(source, /Reset API URL override/);
});

test("latest analysis coordinator runs queued final edit after active request", async () => {
  const { createLatestAnalysisCoordinator } = await import("./App");
  const completed: number[] = [];
  let releaseA!: () => void;
  const coordinator = createLatestAnalysisCoordinator<{ requestId: number }>(
    async (snapshot) => {
      if (snapshot.requestId === 1) {
        await new Promise<void>((resolve) => {
          releaseA = resolve;
        });
      }
      completed.push(snapshot.requestId);
    },
  );

  coordinator.enqueue({ requestId: 1 });
  coordinator.enqueue({ requestId: 2 });
  coordinator.enqueue({ requestId: 3 });
  releaseA();
  await new Promise((resolve) => setTimeout(resolve, 20));

  assert.deepEqual(completed, [1, 3]);
});

test("analyzeText accepts HTTP 200 suggestions and preserves empty result count", async () => {
  const originalFetch = globalThis.fetch;
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({
        suggestions: [
          {
            id: "s1",
            category: "grammar",
            span_start: 0,
            span_end: 3,
            original_text: "আমি",
            suggested_text: "আমরা",
            confidence: 0.8,
            explanation_bn: "ব্যাকরণ",
          },
        ],
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    )) as typeof fetch;

  try {
    const response = await analyzeText({ text: "আমি", mode: "standard" });
    assert.equal(response.suggestions.length, 1);
    assert.equal(response.suggestions[0]?.replacement_options[0], "আমরা");
    assert.equal(response.diagnostics?.http_status, 200);
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
});

test("analyzeText accepts HTTP 200 empty suggestions as valid empty analysis", async () => {
  const originalFetch = globalThis.fetch;
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ suggestions: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    })) as typeof fetch;

  try {
    const response = await analyzeText({ text: "আমি", mode: "standard" });
    assert.equal(response.suggestions.length, 0);
    assert.equal(response.diagnostics?.http_status, 200);
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
});

test("App source preserves local suggestions while queued AI polling runs", () => {
  const source = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(source, /setAnalysisState\("waiting_for_ai"\)/);
  assert.match(source, /Local suggestions ready\. Gemini review is running/);
  assert.match(source, /void pollLlmJob\(snapshot, queuedJobId, controller\.signal\);\n\s*return;/);
  assert.match(source, /setAnalysis\(\(current\) =>/);
  assert.match(source, /rawStatus === "succeeded" \? "completed"/);
  assert.match(source, /AI reviewed the text and found no additional high-confidence issues/);
  assert.match(source, /This Vercel preview domain is not allowed by the backend/);
});
