import test from "node:test";
import assert from "node:assert/strict";
import { getStandaloneAppRoute, getWorkspaceAppRoute } from "../src/appRoutes.mjs";

test("same-origin routes identify the independent Rukh applications and workspace directory", () => {
  assert.equal(getStandaloneAppRoute("/coworker"), "coworker");
  assert.equal(getStandaloneAppRoute("/coworker/"), "coworker");
  assert.equal(getStandaloneAppRoute("/coworker?conversation=abc"), "coworker");
  assert.equal(getStandaloneAppRoute("/fly"), "coworker");
  assert.equal(getStandaloneAppRoute("/editor"), "default");
  assert.equal(getStandaloneAppRoute("/writing"), "writing");
  assert.equal(getStandaloneAppRoute("/editor/recent"), "default");
  assert.equal(getStandaloneAppRoute("/workspaces"), "home");
  assert.equal(getStandaloneAppRoute("/workspaces/?from=editor"), "home");
  assert.equal(getStandaloneAppRoute("/"), "default");
  assert.equal(getStandaloneAppRoute("/unknown"), "default");
  assert.equal(getStandaloneAppRoute(undefined), "default");
});

test("Rukh opens Coworker by default and keeps the workspace directory available as an explicit route", () => {
  assert.equal(getWorkspaceAppRoute("/"), "coworker");
  assert.equal(getWorkspaceAppRoute("/", true), "coworker");
  assert.equal(getWorkspaceAppRoute("/?from=bookmark", true), "coworker");
  assert.equal(getWorkspaceAppRoute("/unknown", true), "home");
  assert.equal(getWorkspaceAppRoute("/", false), "home");
  assert.equal(getWorkspaceAppRoute(undefined, false), "home");
  assert.equal(getWorkspaceAppRoute("/coworker", false), "coworker");
  assert.equal(getWorkspaceAppRoute("/coworker?conversation=abc", false), "coworker");
  assert.equal(getWorkspaceAppRoute("/coworker", true), "coworker");
  assert.equal(getWorkspaceAppRoute("/fly", true), "coworker");
  assert.equal(getWorkspaceAppRoute("/fly", false), "coworker");
  assert.equal(getWorkspaceAppRoute("/writing", true), "writing");
  assert.equal(getWorkspaceAppRoute("/writing", false), "writing");
  assert.equal(getWorkspaceAppRoute("/coworker/conversations/abc", true), "coworker");
  assert.equal(getWorkspaceAppRoute("/workspaces", true), "home");
  assert.equal(getWorkspaceAppRoute("/workspaces", false), "home");
  assert.equal(getWorkspaceAppRoute("/workspaces/?from=editor", true), "home");
  assert.equal(getWorkspaceAppRoute("/workspaces/?from=editor", false), "home");
  assert.equal(getWorkspaceAppRoute("/editor", false), "home");
  assert.equal(getWorkspaceAppRoute("/editor", true), "home");
});


test("provider OAuth callbacks reach the authenticated Coworker handler regardless of landing preference", () => {
  const callbacks = [
    "/oauth/google/callback",
    "/oauth/microsoft/callback",
    "/oauth/linkedin/callback",
  ];
  for (const path of callbacks) {
    assert.equal(getStandaloneAppRoute(path), "coworker");
    assert.equal(getWorkspaceAppRoute(path, true), "coworker");
    assert.equal(getWorkspaceAppRoute(path + "?code=callback-code&state=callback-state", true), "coworker");
    assert.equal(getWorkspaceAppRoute(path, false), "coworker");
  }
});
