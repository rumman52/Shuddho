import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { renderToString } from "react-dom/server.browser";
import React from "react";
import App from "../App";
import { analyzeTextLocally } from "./localAnalysis";
import { normalizeGatewaySuggestions, getPrimaryReplacement } from "./suggestionAdapter";
import {
  applyCompetitionSuggestions,
  compileCompetitionDemoAnnotations,
  competitionDemoFixtures,
  isCompetitionDemoModeEnabled,
  runCompetitionDemoReview,
} from "./competitionDemo";

for (const fixture of competitionDemoFixtures) {
  test(`competition fixture ${fixture.id} is valid and deterministic`, () => {
    assert.equal(fixture.incorrectText.split("\n").filter(Boolean).length, 8);
    assert.equal(fixture.expectedCorrectedText.split("\n").filter(Boolean).length, 8);
    assert.notEqual(fixture.incorrectText, fixture.expectedCorrectedText);
    for (const annotation of fixture.annotations) {
      assert.ok(fixture.incorrectText.includes(annotation.originalText), annotation.id);
      assert.equal(annotation.source, "demo_fixture");
    }

    const compiled = compileCompetitionDemoAnnotations(fixture, fixture.incorrectText);
    for (const suggestion of compiled) {
      assert.equal(fixture.incorrectText.slice(suggestion.span_start, suggestion.span_end), suggestion.original_text);
      assert.ok(getPrimaryReplacement(suggestion));
      assert.equal(suggestion.source, "demo_fixture");
      assert.equal(suggestion.provider, null);
      assert.notEqual(suggestion.provider, "gemini");
      assert.notEqual(suggestion.provider, "openrouter");
    }

    const startedAt = performance.now();
    const response = runCompetitionDemoReview(fixture.id, fixture.incorrectText);
    const durationMs = performance.now() - startedAt;
    assert.ok(durationMs < 300, `${fixture.id} took ${durationMs}ms`);
    assert.equal(response.llm_requested, false);
    assert.equal(response.llm_attempted, false);
    assert.equal(response.llm_used, false);
    assert.equal(response.llm_status, "not_requested");
    assert.equal(response.llm_provider, null);
    assert.ok(response.runtime_warnings.includes("competition_demo_mode"));
    assert.ok(response.suggestions.every((suggestion) => suggestion.source === "rule" || suggestion.source === "spell" || suggestion.source === "demo_fixture"));
    assert.ok(response.suggestions.every((suggestion) => suggestion.source !== "demo_fixture" || suggestion.provider === null));
    assert.ok(response.suggestions.filter((suggestion) => suggestion.source === "rule").length > 0);
    assert.equal(applyCompetitionSuggestions(fixture.incorrectText, response.suggestions), fixture.expectedCorrectedText);
    assert.equal(response.corrected_text, fixture.expectedCorrectedText);
    assert.deepEqual(runCompetitionDemoReview(fixture.id, fixture.incorrectText), response);
  });

  test(`editing ${fixture.id} invalidates stale prepared annotations`, () => {
    const edited = fixture.incorrectText.replace(fixture.annotations[0]?.originalText ?? "!!", "সম্পাদিত অংশ");
    const response = runCompetitionDemoReview(fixture.id, edited);
    assert.ok(response.suggestions.every((suggestion) => edited.slice(suggestion.span_start, suggestion.span_end) === suggestion.original_text));
    if (fixture.annotations[0]) {
      assert.ok(!response.suggestions.some((suggestion) => suggestion.rule_id === fixture.annotations[0].ruleId));
    }
  });
}

test("arbitrary text receives local rules but no prepared fixture suggestions or backend fetch", () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (() => { throw new Error("fetch should not run"); }) as typeof fetch;
  try {
    const text = "আমি বাংলা লিখি  ।। বাংলা বাংলা ভাষা খুব সুন্দর !!";
    const response = runCompetitionDemoReview("student-essay", text);
    assert.equal(response.llm_attempted, false);
    assert.ok(response.suggestions.some((s) => s.subtype === "space_before_punctuation"));
    assert.ok(response.suggestions.some((s) => s.subtype === "duplicate_punctuation"));
    assert.ok(response.suggestions.some((s) => s.subtype === "repeated_word"));
    assert.ok(response.suggestions.every((s) => s.source !== "demo_fixture"));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("normal local analysis still works without AI", () => {
  const response = analyzeTextLocally({ text: "আমি বাংলা বাংলা লিখি।।", mode: "standard" });
  assert.ok(response.suggestions.some((suggestion) => suggestion.source === "rule"));
  assert.equal(response.llm_attempted, undefined);
});

test("suggestion normalization tolerates malformed replacement arrays", () => {
  const [suggestion] = normalizeGatewaySuggestions([
    { id: "bad", rule_id: "bad", span_start: 0, span_end: 2, original_text: "আমি", replacementOptions: ["আমরা"], source: "demo_fixture" },
    { id: "empty", span_start: 0, span_end: 2, original_text: "আমি", replacement_options: null },
  ], "আমি");
  assert.equal(getPrimaryReplacement(suggestion), "আমরা");
});

test("competition mode renders controls when enabled", () => {
  assert.equal(isCompetitionDemoModeEnabled(), true);
  const html = renderToString(React.createElement(App));
  assert.match(html, /Competition Demo · Local Engine/);
  assert.match(html, /Run Demo Review/);
  assert.match(html, /Try Your Own Text/);
  assert.match(html, /This prepared competition example is reviewed locally/);
});

test("competition mode disabled is controlled by VITE_COMPETITION_DEMO_MODE", () => {
  const source = readFileSync(`${process.cwd()}/src/lib/competitionDemo.ts`, "utf8");
  assert.match(source, /VITE_COMPETITION_DEMO_MODE/);
});
