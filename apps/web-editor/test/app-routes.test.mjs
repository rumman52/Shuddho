import test from "node:test";
import assert from "node:assert/strict";
import { getStandaloneAppRoute, getWorkspaceAppRoute } from "../src/appRoutes.mjs";

test("same-origin routes select the independent Rukh applications", () => {
  assert.equal(getStandaloneAppRoute("/coworker"), "coworker");
  assert.equal(getStandaloneAppRoute("/coworker/"), "coworker");
  assert.equal(getStandaloneAppRoute("/coworker?conversation=abc"), "coworker");
  assert.equal(getStandaloneAppRoute("/editor"), "editor");
  assert.equal(getStandaloneAppRoute("/editor/recent"), "editor");
  assert.equal(getStandaloneAppRoute("/"), "default");
  assert.equal(getStandaloneAppRoute("/unknown"), "default");
});

test("the default-off Coworker gate blocks direct routes but preserves Editor", () => {
  assert.equal(getWorkspaceAppRoute("/coworker", false), "editor");
  assert.equal(getWorkspaceAppRoute("/coworker?conversation=abc", false), "editor");
  assert.equal(getWorkspaceAppRoute("/coworker", true), "coworker");
  assert.equal(getWorkspaceAppRoute("/editor", false), "editor");
  assert.equal(getWorkspaceAppRoute("/", false), "editor");
  assert.equal(getWorkspaceAppRoute("/", true), "default");
});
