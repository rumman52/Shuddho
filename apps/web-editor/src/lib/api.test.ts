import assert from "node:assert/strict";
import test from "node:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import {
  analyzeText,
  buildCheckRequestBody,
  checkBackendHealth,
  describeRequestFailure,
  deriveApiConfiguration,
  sendFeedback,
  fetchPreferences,
  fetchWithTimeout,
  gatewayCheckToAnalyzeResponse,
  friendlyLlmWarning,
  readStoredApiBaseUrl,
  setApiBaseUrlOverride,
} from "./api";
import { DEFAULT_PREFERENCES } from "./preferences";

test("deriveApiConfiguration defaults local development to the TypeScript gateway", () => {
  const localConfig = deriveApiConfiguration({
    browserHostname: "localhost",
    configuredBaseUrl: null,
    storedBaseUrl: null,
  });

  assert.equal(localConfig.backendAllowed, true);
  assert.equal(localConfig.apiBaseUrl, "http://127.0.0.1:4000");
  assert.equal(localConfig.localFallbackEnabled, false);
});

test("deriveApiConfiguration uses VITE_API_BASE_URL and normalizes trailing slashes", () => {
  const config = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: "https://api.shuddho.example/",
    storedBaseUrl: null,
    isProductionBuild: true,
  });

  assert.equal(config.backendAllowed, true);
  assert.equal(config.apiBaseUrl, "https://api.shuddho.example");
  assert.equal(config.hardWarning, null);
});

test("production VITE_API_BASE_URL takes priority over stale localStorage override", () => {
  const config = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: "https://shuddho-api.onrender.com",
    storedBaseUrl: "https://old-backend.example.test",
    isProductionBuild: true,
  });

  assert.equal(config.apiBaseUrl, "https://shuddho-api.onrender.com");
  assert.equal(config.apiBaseUrlSource, "environment");
  assert.equal(config.envApiBaseUrlPresent, true);
  assert.equal(config.localStorageOverridePresent, true);
  assert.equal(config.localStorageOverrideIgnored, true);
  assert.equal(config.backendAllowed, true);
  assert.equal(config.hardWarning, null);
});

test("production ignores localStorage override even with explicit debug override", () => {
  const config = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: "https://shuddho-api.onrender.com",
    storedBaseUrl: "https://debug-backend.example.test",
    isProductionBuild: true,
    allowLocalStorageOverride: true,
  });

  assert.equal(config.apiBaseUrl, "https://shuddho-api.onrender.com");
  assert.equal(config.apiBaseUrlSource, "environment");
  assert.equal(config.localStorageOverrideIgnored, true);
});

test("deriveApiConfiguration disables backend when production VITE_API_BASE_URL is missing", () => {
  const config = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: null,
    storedBaseUrl: null,
    isProductionBuild: true,
  });

  assert.equal(config.backendAllowed, false);
  assert.equal(config.apiBaseUrl, "");
  assert.equal(config.hardWarning, "API URL is not configured. Set VITE_API_BASE_URL in Vercel to your backend URL.");
});

test("deriveApiConfiguration rejects localhost for deployed browser origins", () => {
  const deployedConfig = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: "http://127.0.0.1:4000",
    storedBaseUrl: null,
  });

  assert.equal(deployedConfig.backendAllowed, false);
  assert.equal(deployedConfig.hardWarning, "This deployed editor is still pointing to localhost. Use a public HTTPS backend URL.");
  assert.equal(deployedConfig.localFallbackEnabled, false);
});

test("analyzeText calls /api/check on configured gateway base URL", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; body: any }> = [];
  setApiBaseUrlOverride("https://abc123.ngrok-free.app/");
  globalThis.fetch = (async (url, init) => {
    calls.push({
      url: String(url),
      body: JSON.parse(String(init?.body ?? "{}")),
    });
    return new Response(
      JSON.stringify({
        requestId: "req-1",
        language: "bn",
        normalizedText: "আমি ভাত খাই।",
        suggestions: [],
        warnings: [],
      }),
      {
        status: 200,
        headers: { "content-type": "application/json" },
      },
    );
  }) as typeof fetch;

  try {
    await analyzeText({
      text: "আমি ভাত খাই।",
      mode: "standard",
      personal_dictionary: [],
      user_id: "u1",
    });
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }

  assert.equal(calls[0]?.url, "https://abc123.ngrok-free.app/api/check");
  assert.equal(calls[0]?.body.language, "bn");
  assert.deepEqual(calls[0]?.body.options, {
    includeLLM: false,
    asyncLLM: false,
    llmMode: "none",
    mode: "fast",
  });
});

test("analyzeText sends Deep AI Review candidate options", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; body: any }> = [];
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async (url, init) => {
    calls.push({
      url: String(url),
      body: JSON.parse(String(init?.body ?? "{}")),
    });
    return new Response(
      JSON.stringify({
        requestId: "req-ai",
        language: "bn",
        normalizedText: "আমি ভাত খাই।",
        suggestions: [],
        warnings: [],
        llm_requested: true,
        llm_attempted: true,
        llm_status: "completed_empty",
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }) as typeof fetch;

  try {
    await analyzeText(
      { text: "আমি ভাত খাই।", mode: "standard", personal_dictionary: [], user_id: "u1" },
      { includeLLM: true, asyncLLM: false, llmMode: "review_candidates", mode: "smart" },
    );
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }

  assert.equal(calls[0]?.url, "https://api.example.test/api/check");
  assert.deepEqual(calls[0]?.body.options, {
    includeLLM: true,
    asyncLLM: false,
    llmMode: "review_candidates",
    mode: "smart",
  });
});


test("fetchWithTimeout rejects with friendly timeout error", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_url, init) =>
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), {
        once: true,
      });
    })) as typeof fetch;

  try {
    await assert.rejects(
      () => fetchWithTimeout("https://api.example.test/health", {}, 1),
      /Request timed out. Please try again or check backend deployment./,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("request diagnostics classify timeout and CORS/network failures", () => {
  assert.match(
    describeRequestFailure(
      Object.assign(new Error("Request timed out"), {
        name: "FetchTimeoutError",
        timeoutMs: 20000,
      }),
      "https://api.example.test/health",
    ),
    /Backend timeout/,
  );
  assert.match(
    describeRequestFailure(
      new TypeError("Failed to fetch"),
      "https://api.example.test/health",
    ),
    /CORS\/network failure/,
  );
});

test("frontend source does not reference private LLM API key variable names", () => {
  const files = [
    "src/App.tsx",
    "src/main.tsx",
    "src/lib/api.ts",
    "vite.config.ts",
  ];

  for (const file of files) {
    const path = existsSync(join(process.cwd(), file))
      ? join(process.cwd(), file)
      : join(process.cwd(), "apps/web-editor", file);
    const contents = readFileSync(path, "utf8");
    const privateKeyPattern = new RegExp(`${"OPENAI"}_API_KEY|${"OPENROUTER"}_API_KEY`);
    assert.doesNotMatch(contents, privateKeyPattern);
  }
});

test("buildCheckRequestBody returns clean JSON payload", () => {
  const quick = buildCheckRequestBody("আমি ভাত খাই।", {
    includeLLM: false,
    asyncLLM: false,
    mode: "fast",
    llmMode: "none",
  });
  assert.deepEqual(quick, {
    text: "আমি ভাত খাই।",
    language: "bn",
    options: {
      includeLLM: false,
      asyncLLM: false,
      llmMode: "none",
      mode: "fast",
    },
  });

  const deep = buildCheckRequestBody("আমি ভাত খাই।", {
    includeLLM: true,
    asyncLLM: true,
    mode: "smart",
    llmMode: "review_candidates",
  });
  assert.equal(deep.options.mode, "smart");
  assert.equal(deep.options.llmMode, "review_candidates");
});

test("analyzeText surfaces backend 422/500 detail payloads", async () => {
  const originalFetch = globalThis.fetch;
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({
        error: "canonical_payload_validation_error",
      }),
      {
        status: 422,
        headers: { "content-type": "application/json" },
      },
    )) as typeof fetch;
  try {
    await assert.rejects(
      () =>
        analyzeText({
          text: "আমি ভাত খাই।",
          mode: "standard",
          personal_dictionary: [],
          user_id: "u1",
        }),
      /Backend failed: HTTP 422/,
    );
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
});


test("analyzeText surfaces invalid backend JSON diagnostics", async () => {
  const originalFetch = globalThis.fetch;
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async () =>
    new Response("not-json", {
      status: 200,
      headers: { "content-type": "application/json" },
    })) as typeof fetch;

  try {
    await assert.rejects(
      () =>
        analyzeText({
          text: "আমি ভাত খাই।",
          mode: "standard",
          personal_dictionary: [],
          user_id: "u1",
        }),
      /Backend JSON invalid/,
    );
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
});

test("sendFeedback posts full payload to /api/feedback (not /api/events)", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; body: unknown }> = [];
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async (url, init) => {
    calls.push({
      url: String(url),
      body: JSON.parse(String(init?.body ?? "{}")),
    });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  const payload = {
    suggestion_id: "SUGG_42",
    action: "accepted",
    text: "আমি ভাত খাই",
    replacement: "খাই।",
    feedback_key: "fbk-1",
    rule_id: "bn.rule",
    subtype: "grammar_error",
    source: "rule" as const,
    original_text: "খাই",
    user_id: "u-1",
  };
  try {
    await sendFeedback(payload);
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.url, "https://api.example.test/api/feedback");
  assert.deepEqual(calls[0]?.body, payload);
});

test("deriveApiConfiguration keeps local fallback behind an explicit dev flag", () => {
  const config = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: "https://api.shuddho.example",
    storedBaseUrl: null,
    enableLocalFallback: true,
  });

  assert.equal(config.backendAllowed, true);
  assert.equal(config.localFallbackEnabled, true);
});

test("fetchPreferences returns DEFAULT_PREFERENCES when /api/preferences returns 404", async () => {
  const originalFetch = globalThis.fetch;
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ detail: "Not found" }), {
      status: 404,
      headers: { "content-type": "application/json" },
    })) as typeof fetch;

  try {
    const preferences = await fetchPreferences();
    assert.deepEqual(preferences, DEFAULT_PREFERENCES);
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
});

test("gatewayCheckToAnalyzeResponse fills runtime_warnings from backend warnings", () => {
  const response = gatewayCheckToAnalyzeResponse(
    {
      requestId: "req-1",
      language: "bn",
      normalizedText: "আমি ভাত খাই।",
      warnings: ["corrector_missing"],
    } as never,
    {
      text: "আমি ভাত খাই।",
      mode: "standard",
      personal_dictionary: [],
      user_id: "u1",
    },
  );

  assert.deepEqual(response.runtime_warnings, ["corrector_missing"]);
  assert.equal(response.sentence_count, 1);
});

test("gatewayCheckToAnalyzeResponse uses empty arrays when warnings and suggestions are missing", () => {
  const response = gatewayCheckToAnalyzeResponse(
    {
      requestId: "req-1",
      language: "bn",
      normalizedText: "আমি ভাত খাই।",
    } as never,
    {
      text: "আমি ভাত খাই।",
      mode: "standard",
      personal_dictionary: [],
      user_id: "u1",
    },
  );

  assert.deepEqual(response.runtime_warnings, []);
  assert.deepEqual(response.suggestions, []);
});

test("readStoredApiBaseUrl ignores localhost override on deployed host", () => {
  const originalWindow = globalThis.window;
  const store = new Map<string, string>([
    ["shuddho-api-base-url", "http://127.0.0.1:4000"],
  ]);
  Object.defineProperty(globalThis, "window", {
    value: {
      location: { hostname: "shuddho-web-editor.vercel.app" },
      localStorage: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => store.set(key, value),
        removeItem: (key: string) => store.delete(key),
      },
    },
    configurable: true,
  });

  try {
    assert.equal(readStoredApiBaseUrl(), null);
    assert.equal(store.has("shuddho-api-base-url"), false);
  } finally {
    Object.defineProperty(globalThis, "window", {
      value: originalWindow,
      configurable: true,
    });
  }
});

test("buildCheckRequestBody includeLLM flags preserve deep review mode", () => {
  const quick = buildCheckRequestBody("আমি ভাত খাই।", { includeLLM: false });
  assert.equal(quick.options.includeLLM, false);
  assert.equal(quick.options.llmMode, "none");
  assert.equal(quick.options.mode, "fast");

  const deep = buildCheckRequestBody("আমি ভাত খাই।", { includeLLM: true });
  assert.equal(deep.options.includeLLM, true);
  assert.equal(deep.options.asyncLLM, false);
  assert.equal(deep.options.llmMode, "review_candidates");
  assert.equal(deep.options.mode, "smart");
});

test("gatewayCheckToAnalyzeResponse preserves llm diagnostics", () => {
  const response = gatewayCheckToAnalyzeResponse(
    {
      normalizedText: "আমি ভাত খাই।",
      warnings: ["gemma_timeout"],
      llm_requested: true,
      llm_attempted: true,
      llm_used: false,
      llm_status: "timeout",
      llm_provider: "gemma",
      llm_model: "gemma-4-26b-a4b-it",
      llm_response_mode: "json_schema",
      local_suggestion_count: 1,
      ai_suggestion_count: 0,
      rejected_ai_suggestion_count: 2,
      llm: { status: "timeout", error: "gemma_timeout" },
      diagnostics: { local: { suggestion_count: 1 } },
    },
    { text: "আমি ভাত খাই।", mode: "standard", personal_dictionary: [], user_id: "u1" },
  );
  assert.equal(response.llm_status, "timeout");
  assert.equal(response.llm_provider, "gemma");
  assert.equal(response.rejected_ai_suggestion_count, 2);
  assert.deepEqual(response.diagnostics?.llm, { status: "timeout", error: "gemma_timeout" });
});

test("friendlyLlmWarning maps precise provider-aware LLM statuses", () => {
  assert.equal(friendlyLlmWarning({ llm_status: "missing_key", llm_provider: "gemma" }), "Gemma is not configured: missing backend GOOGLE_API_KEY.");
  assert.equal(friendlyLlmWarning({ llm_status: "missing_key", llm_provider: "gemma" }), "Gemma is not configured: missing backend GOOGLE_API_KEY.");
  assert.equal(friendlyLlmWarning({ llm_status: "timeout", llm_provider: "gemma" }), "AI review timed out; showing local suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "unsupported_provider", llm_provider: "gemma", llm_model: "gemma-4-26b-a4b-it", warnings: ["gemma_model_id_suspicious_use_gemma_provider"] }), "Invalid configuration: Shuddho supports only the Gemma provider and Gemma models.");
  assert.equal(friendlyLlmWarning({ llm_status: "rate_limited", llm_provider: "gemma" }), "AI provider rate limit/quota hit; showing local suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "completed_empty", llm_provider: "gemma" }), "AI reviewed the text but found no extra high-confidence suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "completed_rejected", llm_provider: "gemma", rejected_ai_suggestion_count: 1 }), "AI reviewed the text, but its suggestions were rejected by validation. Showing local suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "completed_empty", llm_provider: "gemma", rejected_ai_suggestion_count: 1 }), "AI reviewed the text, but its suggestions were rejected by validation. Showing local suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "invalid_json", llm_provider: "gemma" }), "AI returned invalid JSON; showing local suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "invalid_schema", llm_provider: "gemma" }), "AI review unavailable; showing local suggestions.");
});

test("friendlyLlmWarning explains local-only skipped LLM without treating it as provider failure", () => {
  assert.equal(
    friendlyLlmWarning({
      llm_requested: false,
      llm_status: "skipped",
      llm_provider: "gemma",
      llm: { skip_reason: "include_llm_false" },
    }),
    "AI review was not requested. Showing local suggestions.",
  );
  assert.equal(
    friendlyLlmWarning({
      llm_requested: false,
      llm_status: "skipped",
      llm_provider: "gemma",
    }),
    "AI review was not requested. Showing local suggestions.",
  );
});


test("checkBackendHealth treats HTTP 200 plus ok true as connected", async () => {
  const originalFetch = globalThis.fetch;
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ ok: true, status: "ok" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    })) as typeof fetch;

  try {
    const health = await checkBackendHealth();
    assert.equal(health.ok, true);
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
});

test("checkBackendHealth rejects HTTP 200 without ok true", async () => {
  const originalFetch = globalThis.fetch;
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ ok: false, status: "degraded" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    })) as typeof fetch;

  try {
    const health = await checkBackendHealth();
    assert.equal(health.ok, false);
    assert.match(health.message ?? "", /ok:true/);
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
});

test("GET /health request does not send Content-Type", async () => {
  const { getHealth } = await import("./api");
  const originalFetch = globalThis.fetch;
  const seenHeaders: Headers[] = [];
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async (_url, init) => {
    seenHeaders.push(new Headers(init?.headers));
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    await getHealth();
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
  assert.equal(seenHeaders[0].has("Content-Type"), false);
  assert.equal(seenHeaders[0].get("Accept"), "application/json");
});

test("POST /api/check sends JSON Content-Type", async () => {
  const originalFetch = globalThis.fetch;
  const seenHeaders: Headers[] = [];
  setApiBaseUrlOverride("https://api.example.test");
  globalThis.fetch = (async (_url, init) => {
    seenHeaders.push(new Headers(init?.headers));
    return new Response(JSON.stringify({ suggestions: [], local_suggestion_count: 0 }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    await analyzeText({ text: "আমি ভাত খাই।", mode: "standard", personal_dictionary: [], user_id: "u1" });
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
  assert.equal(seenHeaders[0].get("Content-Type"), "application/json");
  assert.equal(seenHeaders[0].get("Accept"), "application/json");
});

test("analyzeText renders five local suggestions from HTTP 200 /api/check response", async () => {
  const originalFetch = globalThis.fetch;
  setApiBaseUrlOverride("https://api.example.test");
  const sample = "আমি বাংলা লিখি  ।। বাংলা বাংলা ভাষা খুব সুন্দর !!";
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({
        requestId: "req-local-five",
        language: "bn",
        normalizedText: sample,
        correctedText: "আমি বাংলা লিখি। বাংলা ভাষা খুব সুন্দর!",
        local_suggestion_count: 5,
        ai_suggestion_count: 0,
        llm_requested: false,
        llm_attempted: false,
        llm_status: "skipped",
        suggestions: [
          { id: "s1", rule_id: "spacing-before-dari", category: "punctuation", span_start: 13, span_end: 16, original_text: "  ।", replacement_options: ["।"], explanation_bn: "Remove the extra space before `।`", source: "rule", severity: "low" },
          { id: "s2", rule_id: "double-dari", category: "punctuation", span_start: 15, span_end: 17, original_text: "।।", replacement_options: ["।"], explanation_bn: "Replace `।।` with `।`", source: "rule", severity: "low" },
          { id: "s3", rule_id: "repeated-word", category: "grammar", span_start: 18, span_end: 29, original_text: "বাংলা বাংলা", replacement_options: ["বাংলা"], explanation_bn: "Replace repeated `বাংলা বাংলা` with `বাংলা`", source: "rule", severity: "medium" },
          { id: "s4", rule_id: "space-before-bang", category: "punctuation", span_start: 47, span_end: 49, original_text: " !", replacement_options: ["!"], explanation_bn: "Remove the space before `!`", source: "rule", severity: "low" },
          { id: "s5", rule_id: "double-bang", category: "punctuation", span_start: 48, span_end: 50, original_text: "!!", replacement_options: ["!"], explanation_bn: "Replace `!!` with `!`", source: "rule", severity: "low" },
        ],
        warnings: [],
        diagnostics: { http_status: 200 },
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    )) as typeof fetch;

  try {
    const result = await analyzeText({ text: sample, mode: "standard", personal_dictionary: [], user_id: "u1" }, { includeLLM: false, asyncLLM: false, llmMode: "none", mode: "fast" });
    assert.equal(result.suggestions.length, 5);
    assert.match(result.suggestions.map((s) => s.explanation_bn).join("\n"), /বাংলা বাংলা/);
  } finally {
    globalThis.fetch = originalFetch;
    setApiBaseUrlOverride("");
  }
});
