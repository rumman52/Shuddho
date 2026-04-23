import assert from "node:assert/strict";
import test from "node:test";

import { getHostnameFromUrl, modeFromWritingGoal } from "./config";

test("modeFromWritingGoal prefers formal mode for formal goals", () => {
  assert.equal(modeFromWritingGoal("general"), "standard");
  assert.equal(modeFromWritingGoal("formal"), "formal");
  assert.equal(modeFromWritingGoal("academic"), "formal");
  assert.equal(modeFromWritingGoal("business"), "formal");
});

test("getHostnameFromUrl extracts hostnames safely", () => {
  assert.equal(getHostnameFromUrl("https://mail.example.com/compose"), "mail.example.com");
  assert.equal(getHostnameFromUrl("not-a-url"), null);
  assert.equal(getHostnameFromUrl(undefined), null);
});
