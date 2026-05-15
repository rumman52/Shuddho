import assert from "node:assert/strict";
import test from "node:test";

import {
  analyzeText,
  deriveApiConfiguration,
  fetchPreferences,
  gatewayCheckToAnalyzeResponse,
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

test("deriveApiConfiguration falls back to Render when production VITE_API_BASE_URL is missing", () => {
  const config = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: null,
    storedBaseUrl: null,
    isProductionBuild: true,
  });

  assert.equal(config.backendAllowed, true);
  assert.equal(config.apiBaseUrl, "https://shuddho-api.onrender.com");
  assert.equal(config.hardWarning, null);
});

test("deriveApiConfiguration rejects localhost for deployed browser origins", () => {
  const deployedConfig = deriveApiConfiguration({
    browserHostname: "shuddho-web-editor.vercel.app",
    configuredBaseUrl: "http://127.0.0.1:4000",
    storedBaseUrl: null,
  });

  assert.equal(deployedConfig.backendAllowed, false);
  assert.match(deployedConfig.hardWarning ?? "", /VITE_API_BASE_URL/);
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
