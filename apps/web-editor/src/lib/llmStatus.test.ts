import { test } from "node:test";
import assert from "node:assert/strict";
import { createEmptyAnalysis } from "./analysis";
import {
  isAiUnavailableStatus,
  llmReviewStatusMessage,
  mergeLlmJobIntoAnalysis,
} from "./llmStatus";

test("completed statuses are not AI unavailable", () => {
  assert.equal(isAiUnavailableStatus("completed", true), false);
  assert.equal(isAiUnavailableStatus("completed_empty", true), false);
  assert.equal(isAiUnavailableStatus("completed_rejected", true), false);
  assert.equal(isAiUnavailableStatus("queued", true), false);
  assert.equal(isAiUnavailableStatus("running", true), false);
});

test("explicit provider failure statuses are AI unavailable", () => {
  for (const status of ["missing_key", "timeout", "rate_limited", "network_error", "invalid_json", "failed", "expired"]) {
    assert.equal(isAiUnavailableStatus(status, true), true, status);
  }
});

test("terminal job replaces stale queued llm fields", () => {
  const current = createEmptyAnalysis("আমি বাংলা লিখি", "standard");
  current.llm_requested = true;
  current.llm_attempted = true;
  current.llm_used = false;
  current.llm_status = "queued";
  const merged = mergeLlmJobIntoAnalysis(current, {
    job_id: "llm_1",
    status: "completed",
    llm_status: "completed",
    llm_requested: true,
    llm_attempted: true,
    llm_used: true,
    llm_provider: "gemini",
    llm_model: "gemini-3.5-flash",
    suggestions: [],
  });
  assert.equal(merged.llm_used, true);
  assert.equal(merged.llm_status, "completed");
});

test("local suggestions survive AI provider failure with empty job suggestions", () => {
  const current = createEmptyAnalysis("আমি বাংলা লিখি", "standard");
  current.suggestions = [{ id: "local-1", rule_id: "r", category: "grammar", subtype: "x", span_start: 0, span_end: 1, original: "আমি", replacement_options: ["আমি"], explanation: "x", confidence: 0.8, source: "rule" }];
  const merged = mergeLlmJobIntoAnalysis(current, {
    job_id: "llm_2",
    status: "timeout",
    llm_status: "timeout",
    llm_requested: true,
    llm_attempted: true,
    llm_used: false,
    suggestions: [],
  });
  assert.equal(merged.suggestions?.length, 1);
});

test("fallback success displays OpenRouter completion message", () => {
  assert.equal(
    llmReviewStatusMessage({ llm_status: "completed", llm_provider: "openrouter", warnings: ["fallback_provider_used:openrouter"], provider_attempts: [{ provider: "gemini" }, { provider: "openrouter" }] }),
    "Gemini was unavailable, so OpenRouter completed the review.",
  );
});
