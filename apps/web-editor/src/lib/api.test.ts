import assert from "node:assert/strict";
import test from "node:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import {
  analyzeText,
  buildCheckRequestBody,
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
      warnings: ["openai_timeout"],
      llm_requested: true,
      llm_attempted: true,
      llm_used: false,
      llm_status: "timeout",
      llm_provider: "openai",
      llm_model: "gpt-4o-mini",
      llm_response_mode: "json_schema",
      local_suggestion_count: 1,
      ai_suggestion_count: 0,
      rejected_ai_suggestion_count: 2,
      llm: { status: "timeout", error: "openai_timeout" },
      diagnostics: { local: { suggestion_count: 1 } },
    },
    { text: "আমি ভাত খাই।", mode: "standard", personal_dictionary: [], user_id: "u1" },
  );
  assert.equal(response.llm_status, "timeout");
  assert.equal(response.llm_provider, "openai");
  assert.equal(response.rejected_ai_suggestion_count, 2);
  assert.deepEqual(response.diagnostics?.llm, { status: "timeout", error: "openai_timeout" });
});

test("friendlyLlmWarning maps precise provider-aware LLM statuses", () => {
  assert.equal(friendlyLlmWarning({ llm_status: "missing_key", llm_provider: "openrouter" }), "OpenRouter is not configured: missing backend OpenRouter API key.");
  assert.equal(friendlyLlmWarning({ llm_status: "missing_key", llm_provider: "openai" }), "OpenAI is not configured: missing backend OpenAI API key.");
  assert.equal(friendlyLlmWarning({ llm_status: "timeout", llm_provider: "openrouter" }), "AI review timed out; showing local suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "unsupported_provider", llm_provider: "openai", llm_model: "openai/gpt-oss-120b:free", warnings: ["openai_model_id_suspicious_use_openrouter_provider"] }), "Invalid config: openai/gpt-oss-120b:free must use SHUDDHO_LLM_PROVIDER=openrouter.");
  assert.equal(friendlyLlmWarning({ llm_status: "rate_limited", llm_provider: "openrouter" }), "AI provider rate limit/quota hit; showing local suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "completed_empty", llm_provider: "openrouter" }), "OpenRouter reviewed the text but found no extra high-confidence suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "invalid_json", llm_provider: "openrouter" }), "AI returned invalid JSON; showing local suggestions.");
  assert.equal(friendlyLlmWarning({ llm_status: "invalid_schema", llm_provider: "openrouter" }), "AI response failed Shuddho validation.");
});
