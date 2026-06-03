import assert from "node:assert/strict";
import test from "node:test";

import type { AnalyzeResponse } from "@shared/schemas/contracts";

import { describeRuntimeState, getRuntimeLabel } from "./runtimeStatus";

function buildAnalysis(overrides: Partial<AnalyzeResponse> = {}): AnalyzeResponse {
  return {
    text: "আমি বাংলা লিখি।",
    normalized_text: "আমি বাংলা লিখি।",
    corrected_text: "আমি বাংলা লিখি।",
    suggestions: [],
    analysis_profile: "full_local",
    runtime_source: "full_local",
    runtime_warnings: [],
    used_detector: true,
    used_corrector: true,
    lexicon_source: "words_clean.csv",
    lexicon_version: "abc123",
    backend_version: "0.1.0",
    sentence_count: 1,
    request_mode_applied: "standard",
    ...overrides,
  };
}

test("getRuntimeLabel returns explicit backend status copy", () => {
  assert.equal(getRuntimeLabel("full_local"), "Online contextual backend");
  assert.equal(getRuntimeLabel("backend_rules_and_spell_only"), "Backend online rules/spell only");
  assert.equal(getRuntimeLabel("backend_without_detector"), "Backend online but detector missing");
  assert.equal(getRuntimeLabel("backend_without_corrector"), "Backend online but corrector missing");
  assert.equal(getRuntimeLabel("frontend_local_fallback"), "Dev-only browser fallback");
});

test("describeRuntimeState marks offline backend with suggestions disabled by default", () => {
  const descriptor = describeRuntimeState({
    analysis: buildAnalysis({
      analysis_profile: "frontend_local_fallback",
      runtime_source: "frontend_local_fallback",
      runtime_warnings: ["backend_offline_contextual_disabled"],
      used_detector: false,
      used_corrector: false,
    }),
    transport: "offline",
    health: null,
  });

  assert.equal(descriptor.label, "Backend offline, suggestions disabled");
  assert.equal(descriptor.localOnly, false);
  assert.equal(descriptor.degraded, true);
  assert.deepEqual(descriptor.warnings, ["backend_offline_contextual_disabled"]);
});

test("describeRuntimeState distinguishes dev-only local fallback from disabled backend mode", () => {
  const descriptor = describeRuntimeState({
    analysis: buildAnalysis({
      analysis_profile: "frontend_local_fallback",
      runtime_source: "frontend_local_fallback",
      runtime_warnings: ["frontend_local_fallback_enabled"],
      used_detector: false,
      used_corrector: false,
    }),
    transport: "offline",
    health: null,
  });

  assert.equal(descriptor.label, "Dev-only browser fallback");
  assert.equal(descriptor.localOnly, true);
  assert.equal(descriptor.degraded, true);
});

test("describeRuntimeState marks deployed localhost backends as misconfigured", () => {
  const descriptor = describeRuntimeState({
    analysis: buildAnalysis({
      analysis_profile: "frontend_local_fallback",
      runtime_source: "frontend_local_fallback",
      runtime_warnings: ["backend_misconfigured_contextual_disabled"],
      used_detector: false,
      used_corrector: false,
    }),
    transport: "misconfigured",
    health: null,
    hardWarning:
      "This deployed editor is still pointing to localhost. Use a public HTTPS backend URL.",
  });

  assert.equal(descriptor.label, "Backend misconfigured - contextual correction disabled");
  assert.equal(descriptor.localOnly, false);
  assert.equal(descriptor.degraded, true);
  assert.equal(descriptor.warnings[0]?.includes("VITE_API_BASE_URL"), true);
});


test("health ok with missing corrector is degraded rather than unavailable", () => {
  const descriptor = describeRuntimeState({
    analysis: buildAnalysis({
      analysis_profile: "backend_without_corrector",
      runtime_source: "backend_without_corrector",
      runtime_warnings: ["corrector_missing_checkpoint"],
      used_corrector: false,
    }),
    transport: "online",
    health: {
      ok: true,
      service: "shuddho-api",
      status: "ok",
      backend_reachable: true,
      detector_loaded: true,
      corrector_loaded: false,
      allowed_origins: [],
      detector: {
        enabled: true,
        loaded: true,
        status: "ready",
        reason: null,
        checkpoint: null,
        checkpoint_exists: true,
        backend_name: "stub_detector",
        threshold: 0.92,
      },
      corrector: {
        enabled: true,
        loaded: false,
        status: "missing_checkpoint",
        reason: "missing best_model.pt",
        checkpoint: "artifacts/corrector/corrector-base",
        checkpoint_exists: false,
        backend_name: "disabled",
        threshold: 0.86,
      },
      analysis_profile: "backend_without_corrector",
      degraded_reasons: ["corrector_missing_checkpoint"],
      mode_capabilities: { standard: ["rules", "spelling"] },
      backend_warning: "Sentence-level corrector is not loaded. Shuddho is running rules + spelling only.",
      backend_version: "test",
      env_file_loaded: false,
      last_startup_timestamp: new Date().toISOString(),
      llm: {
        enabled: true,
        configured: true,
        provider: "openrouter",
        model: "openai/gpt-oss-120b:free",
      },
      lexicon: {
        runtime_source_of_truth: "csv_runtime",
        runtime_source: "words_clean.csv",
        runtime_exists: true,
        accepted_word_count: 0,
        candidate_word_count: 0,
        correction_map_count: 0,
        import_database_exists: false,
        reload_supported: true,
        restart_required: true,
      },
    },
  });

  assert.equal(descriptor.label, "Backend connected, but sentence-level corrector is degraded.");
  assert.equal(descriptor.degraded, true);
  assert.equal(descriptor.diagnostics.backendReachable, true);
  assert.equal(descriptor.diagnostics.correctorLoaded, false);
  assert.equal(descriptor.diagnostics.llmEnabled, true);
  assert.equal(descriptor.diagnostics.llmConfigured, true);
  assert.equal(descriptor.diagnostics.llmProvider, "openrouter");
  assert.notEqual(descriptor.label, "Backend offline, suggestions disabled");
});
