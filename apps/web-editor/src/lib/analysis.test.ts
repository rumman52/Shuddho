import assert from "node:assert/strict";
import test from "node:test";

import { normalizeAnalyzeResponse } from "./analysis";

test("normalizeAnalyzeResponse prevents undefined array length crashes", () => {
  const normalized = normalizeAnalyzeResponse(
    {
      text: "আমি ভাত খাই।",
    },
    "আমি ভাত খাই।",
    "standard",
  );

  assert.equal(normalized.suggestions.length, 0);
  assert.equal(normalized.runtime_warnings.length, 0);
  assert.equal(normalized.sentence_count, 1);
  assert.equal(normalized.backend_warning, null);
});
