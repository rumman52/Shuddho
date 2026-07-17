import assert from "node:assert/strict";
import test from "node:test";
import { normalizeAnalyzeResponse } from "./analysis";
import { mergeLlmJobIntoAnalysis } from "./llmStatus";
import { getPrimaryReplacement, normalizeGatewaySuggestions } from "./suggestionAdapter";
import type { AnalyzeResponse } from "@shared/schemas/contracts";

const text = "আমি বাংলা লিখি  ।। বাংলা বাংলা ভাষা খুব সুন্দর !!";
const local = {
  id: "local-1", rule_id: "local.spacing", category: "spacing", subtype: "spacing", span_start: 3, span_end: 4,
  original_text: " ", replacement_options: [""], confidence: 1, explanation_bn: "স্থানীয়", explanation_en: "local", source: "rule", severity: "low",
} as const;
const camel = {
  id: "g1", ruleId: "ai.grammar", type: "grammar", severity: "medium", originalText: "বাংলা", suggestedText: "বাংলা ভাষা",
  replacementOptions: ["বাংলা ভাষা"], explanationBn: "পরামর্শ", span: { startIndex: 4, endIndex: 9 }, confidence: 0.9, source: "model", provider: "gemini",
};
function current(): AnalyzeResponse { return normalizeAnalyzeResponse({ text, suggestions: [local] as any, llm_status: "queued", llm_used: false }, text, "standard"); }

test("camelCase completed async job normalizes replacement_options", () => {
  const merged = normalizeAnalyzeResponse(mergeLlmJobIntoAnalysis(current(), { status: "completed", llm_status: "completed", llm_requested: true, llm_attempted: true, llm_used: true, llm_provider: "gemini", suggestions: [camel] } as any), text, "standard");
  assert.deepEqual(merged.suggestions[0]?.replacement_options, ["বাংলা ভাষা"]);
  assert.doesNotThrow(() => getPrimaryReplacement(merged.suggestions[0]));
});

test("completed_empty job can carry local camelCase suggestions", () => {
  const merged = normalizeAnalyzeResponse(mergeLlmJobIntoAnalysis(current(), { status: "completed_empty", llm_status: "completed_empty", llm_used: true, suggestions: [camel] } as any), text, "standard");
  assert.equal(merged.llm_status, "completed_empty");
  assert.deepEqual(merged.suggestions[0]?.replacement_options, ["বাংলা ভাষা"]);
});

test("provider failure preserves local suggestions when job suggestions are empty or invalid", () => {
  const merged = normalizeAnalyzeResponse(mergeLlmJobIntoAnalysis(current(), { status: "failed", llm_status: "failed", llm_used: false, suggestions: [null] } as any), text, "standard");
  assert.equal(merged.suggestions[0]?.id, "local-1");
});

test("missing replacementOptions falls back safely and suggestedText is used", () => {
  assert.deepEqual(normalizeGatewaySuggestions([{ ...camel, replacementOptions: undefined }])[0]?.replacement_options, ["বাংলা ভাষা"]);
  assert.deepEqual(normalizeGatewaySuggestions([{ ...camel, replacementOptions: undefined, suggestedText: undefined }])[0]?.replacement_options, []);
});

test("invalid/null entries and invalid spans are dropped", () => {
  assert.equal(normalizeGatewaySuggestions([null, { ...camel, span: { startIndex: 9, endIndex: 4 } }, camel]).length, 1);
});

test("mixed camelCase and snake_case arrays normalize", () => {
  const snake = { id: "s1", rule_id: "x", category: "clarity", span_start: 1, span_end: 2, original_text: "আ", replacement_options: ["ই"], explanation_bn: "", explanation_en: "", source: "model" };
  const out = normalizeGatewaySuggestions([camel, snake]);
  assert.deepEqual(out.map((s) => s.replacement_options[0]), ["বাংলা ভাষা", "ই"]);
});

test("terminal result replaces stale queued llm_used=false", () => {
  const merged = normalizeAnalyzeResponse(mergeLlmJobIntoAnalysis(current(), { status: "completed", llm_status: "completed", llm_used: true, suggestions: [camel] } as any), text, "standard");
  assert.equal(merged.llm_used, true);
});
