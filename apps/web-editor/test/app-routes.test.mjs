import test from "node:test";
import assert from "node:assert/strict";
import { getStandaloneAppRoute, getWorkspaceAppRoute } from "../src/appRoutes.mjs";

test("same-origin routes identify the independent Rukh applications", () => {
  assert.equal(getStandaloneAppRoute("/coworker"), "coworker");
  assert.equal(getStandaloneAppRoute("/coworker/"), "coworker");
  assert.equal(getStandaloneAppRoute("/coworker?conversation=abc"), "coworker");
  assert.equal(getStandaloneAppRoute("/editor"), "editor");
  assert.equal(getStandaloneAppRoute("/editor/recent"), "editor");
  assert.equal(getStandaloneAppRoute("/"), "default");
  assert.equal(getStandaloneAppRoute("/unknown"), "default");
});

test("the Rukh home is the default entry point while Coworker stays behind its release gate", () => {
  assert.equal(getWorkspaceAppRoute("/", false), "home");
  assert.equal(getWorkspaceAppRoute("/unknown", false), "home");
  assert.equal(getWorkspaceAppRoute("/coworker", false), "home");
  assert.equal(getWorkspaceAppRoute("/coworker?conversation=abc", false), "home");
  assert.equal(getWorkspaceAppRoute("/coworker", true), "coworker");
  assert.equal(getWorkspaceAppRoute("/editor", false), "editor");
  assert.equal(getWorkspaceAppRoute("/editor", true), "editor");
  assert.equal(getWorkspaceAppRoute("/", true), "home");
});
