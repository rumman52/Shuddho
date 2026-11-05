import test from "node:test";
import assert from "node:assert/strict";
import { coworkerNavigation, getCoworkerView, getInitialCoworkerView, getInitialConversationId } from "../src/navigation.mjs";

test("Coworker navigation maps only implemented workspace surfaces", () => {
  const ids = coworkerNavigation.map(item => item.id);
  assert.deepEqual(ids, ["home", "projects", "library", "settings", "agent", "goals", "automations", "browser", "files", "approvals", "sandbox", "transactions", "negotiations"]);
  assert.equal(getCoworkerView("home"), "conversations");
  assert.equal(getCoworkerView("projects"), "projects");
  assert.equal(getCoworkerView("library"), "library");
  assert.equal(getCoworkerView("settings"), "settings");
  assert.equal(getCoworkerView("files"), "drafts");
  assert.equal(getCoworkerView("approvals"), "actions");
  assert.equal(getCoworkerView("goals"), "goals");
  assert.equal(getCoworkerView("unknown"), "conversations");
});

test("Coworker initial view accepts only implemented routes", () => {
  assert.equal(getInitialCoworkerView("?view=agent"), "agent");
  assert.equal(getInitialCoworkerView("?view=files"), "drafts");
  assert.equal(getInitialCoworkerView("?view=unknown"), "conversations");
  assert.equal(getInitialCoworkerView(""), "conversations");
  assert.equal(coworkerNavigation[0].label, "Coworker");
});

test("Coworker deep links accept only UUID conversation identifiers", () => {
  const id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  assert.equal(getInitialConversationId(`?conversation=${id}`), id);
  assert.equal(getInitialConversationId("?conversation=../other-owner"), null);
  assert.equal(getInitialConversationId("?conversation="), null);
  assert.equal(getInitialConversationId(""), null);
});
