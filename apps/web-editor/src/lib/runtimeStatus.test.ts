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
    analysis_profile: "full_backend",
    runtime_source: "full_backend",
    runtime_warnings: [],
    used_detector: true,
    used_openrouter: true,
    lexicon_source: "words_clean.csv",
    lexicon_version: "abc123",
    backend_version: "0.1.0",
    sentence_count: 1,
    request_mode_applied: "standard",
    ...overrides,
  };
}

test("getRuntimeLabel returns the fixed runtime copy", () => {
  assert.equal(getRuntimeLabel("full_backend"), "Full backend contextual analysis active");
  assert.equal(getRuntimeLabel("backend_rules_and_spell_only"), "Backend live — rules/spell only");
  assert.equal(getRuntimeLabel("backend_without_detector"), "Backend live — detector unavailable");
  assert.equal(getRuntimeLabel("backend_without_openrouter"), "Backend live — OpenRouter unavailable");
  assert.equal(getRuntimeLabel("frontend_local_fallback"), "Backend unreachable — local fallback only");
});

test("describeRuntimeState marks local fallback and exposes warnings", () => {
  const descriptor = describeRuntimeState({
    analysis: buildAnalysis({
      analysis_profile: "frontend_local_fallback",
      runtime_source: "frontend_local_fallback",
      runtime_warnings: ["backend_unreachable_local_fallback"],
      used_detector: false,
      used_openrouter: false,
    }),
    transport: "offline",
    health: null,
  });

  assert.equal(descriptor.label, "Backend unreachable — local fallback only");
  assert.equal(descriptor.localOnly, true);
  assert.equal(descriptor.degraded, true);
  assert.deepEqual(descriptor.warnings, ["backend_unreachable_local_fallback"]);
});

test("describeRuntimeState marks deployed localhost backends as misconfigured", () => {
  const descriptor = describeRuntimeState({
    analysis: buildAnalysis({
      analysis_profile: "frontend_local_fallback",
      runtime_source: "frontend_local_fallback",
      runtime_warnings: ["frontend_local_fallback"],
      used_detector: false,
      used_openrouter: false,
    }),
    transport: "misconfigured",
    health: null,
    hardWarning:
      "This deployed editor is still pointing to http://127.0.0.1:8000. Set VITE_API_BASE_URL to a public backend URL; localhost is only valid from local browser sessions.",
  });

  assert.equal(descriptor.label, "Backend misconfigured — localhost API blocked");
  assert.equal(descriptor.localOnly, true);
  assert.equal(descriptor.degraded, true);
  assert.equal(descriptor.warnings[0]?.includes("VITE_API_BASE_URL"), true);
});
