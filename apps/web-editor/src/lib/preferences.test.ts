import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_PREFERENCES, normalizePreferences } from "./preferences";

const maybeUndefinedArrays = normalizePreferences({
  user_id: "u1",
  personal_dictionary: undefined,
  suppressed_rule_keys: undefined,
  disabledSuggestionTypes: undefined,
  ignoredRuleIds: undefined,
});

test("normalizePreferences fills missing preference arrays", () => {
  assert.deepEqual(maybeUndefinedArrays.personal_dictionary, []);
  assert.deepEqual(maybeUndefinedArrays.suppressed_rule_keys, []);
  assert.deepEqual(maybeUndefinedArrays.disabledSuggestionTypes, []);
  assert.deepEqual(maybeUndefinedArrays.ignoredRuleIds, []);
  assert.deepEqual(maybeUndefinedArrays.enabledSuggestionTypes, DEFAULT_PREFERENCES.enabledSuggestionTypes);
});

test("normalized preferences arrays are safe for includes checks", () => {
  assert.equal(maybeUndefinedArrays.disabledSuggestionTypes.includes("grammar"), false);
  assert.equal(maybeUndefinedArrays.enabledSuggestionTypes.includes("grammar"), true);
});
