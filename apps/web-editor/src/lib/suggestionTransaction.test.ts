import test from "node:test";
import assert from "node:assert/strict";
import type { Suggestion } from "@shared/schemas/contracts";
import { applySuggestionTransaction } from "./suggestionTransaction";

function suggestion(id: string, text: string, original: string, replacement: string): Suggestion {
  const start = text.indexOf(original);
  assert.notEqual(start, -1);
  return { id, rule_id: id, category: "grammar", subtype: id, span_start: start, span_end: start + original.length, original_text: original, replacement_options: [replacement], confidence: 0.9, explanation_bn: "", explanation_en: "", source: "rule", severity: "medium" } as Suggestion;
}

test("sequential official-report applies do not duplicate Bangla characters", () => {
  const initial = "কমিটি সমস্যা সমাধান করার নির্দেশ দেয়। কাজ সন্তোষজনক পাওয়া গেছে।";
  const first = suggestion("a", initial, "সমস্যা সমাধান করার নির্দেশ", "সমস্যাটি সমাধানের নির্দেশ");
  const second = suggestion("b", initial, "সন্তোষজনক পাওয়া গেছে", "সন্তোষজনক বলে প্রতীয়মান হয়েছে");
  const one = applySuggestionTransaction(initial, first, first.replacement_options[0], [first, second]);
  assert.equal(one.ok, true);
  if (!one.ok) return;
  const currentSecond = one.suggestions.find((item) => item.id === "b")!;
  const two = applySuggestionTransaction(one.text, currentSecond, currentSecond.replacement_options[0], one.suggestions);
  assert.equal(two.ok, true);
  if (!two.ok) return;
  assert.match(two.text, /সন্তোষজনক বলে প্রতীয়মান হয়েছে/);
  assert.doesNotMatch(two.text, /সসন্তোষজনক বলে প্রতীয়মান হয়েছে/);
});

test("emoji before Bangla issue keeps UTF-16 offsets safe by exact matching", () => {
  const text = "🙂 এটি সন্তোষজনক পাওয়া গেছে।";
  const item = suggestion("emoji", text, "সন্তোষজনক পাওয়া গেছে", "সন্তোষজনক বলে প্রতীয়মান হয়েছে");
  const result = applySuggestionTransaction(text, item, item.replacement_options[0], [item]);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.text, "🙂 এটি সন্তোষজনক বলে প্রতীয়মান হয়েছে।");
});

test("stale suggestion does not modify text", () => {
  const original = "আমি বাংলা লিখি।";
  const item = suggestion("stale", original, "বাংলা", "বাংলায়");
  const result = applySuggestionTransaction("আমি ইংরেজি লিখি।", item, "বাংলায়", [item]);
  assert.equal(result.ok, false);
});
