import test from "node:test";
import assert from "node:assert/strict";
import { getStandaloneAppRoute, getWorkspaceAppRoute } from "../src/appRoutes.mjs";

test("same-origin routes identify the independent Rukh applications and workspace directory", () => {
  assert.equal(getStandaloneAppRoute("/coworker"), "coworker");
  assert.equal(getStandaloneAppRoute("/coworker/"), "coworker");
  assert.equal(getStandaloneAppRoute("/coworker?conversation=abc"), "coworker");
  assert.equal(getStandaloneAppRoute("/editor"), "editor");
  assert.equal(getStandaloneAppRoute("/editor/recent"), "editor");
  assert.equal(getStandaloneAppRoute("/workspaces"), "home");
  assert.equal(getStandaloneAppRoute("/workspaces/?from=editor"), "home");
  assert.equal(getStandaloneAppRoute("/"), "default");
  assert.equal(getStandaloneAppRoute("/unknown"), "default");
});

test("the root route always presents the workspace chooser while direct Coworker access remains feature-gated", () => {
  assert.equal(getWorkspaceAppRoute("/", true), "home");
  assert.equal(getWorkspaceAppRoute("/?from=bookmark", true), "home");
  assert.equal(getWorkspaceAppRoute("/unknown", true), "home");
  assert.equal(getWorkspaceAppRoute("/", false), "home");
  assert.equal(getWorkspaceAppRoute("/coworker", false), "home");
  assert.equal(getWorkspaceAppRoute("/coworker?conversation=abc", false), "home");
  assert.equal(getWorkspaceAppRoute("/coworker", true), "coworker");
  assert.equal(getWorkspaceAppRoute("/coworker/conversations/abc", true), "coworker");
  assert.equal(getWorkspaceAppRoute("/workspaces", true), "home");
  assert.equal(getWorkspaceAppRoute("/workspaces", false), "home");
  assert.equal(getWorkspaceAppRoute("/workspaces/?from=editor", true), "home");
  assert.equal(getWorkspaceAppRoute("/workspaces/?from=editor", false), "home");
  assert.equal(getWorkspaceAppRoute("/editor", false), "editor");
  assert.equal(getWorkspaceAppRoute("/editor", true), "editor");
});
