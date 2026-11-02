import test from "node:test";
import assert from "node:assert/strict";
import { coworkerNavigation, getCoworkerView, getInitialConversationId } from "../src/navigation.mjs";

test("Coworker navigation maps only implemented workspace surfaces", () => {
  const ids = coworkerNavigation.map(item => item.id);
  assert.deepEqual(ids, ["home", "agent", "goals", "automations", "browser", "files", "approvals", "sandbox", "transactions", "negotiations"]);
  assert.equal(getCoworkerView("home"), "conversations");
  assert.equal(getCoworkerView("files"), "drafts");
  assert.equal(getCoworkerView("approvals"), "actions");
  assert.equal(getCoworkerView("unknown"), "conversations");
});

test("Coworker deep links accept only UUID conversation identifiers", () => {
  const id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  assert.equal(getInitialConversationId(`?conversation=${id}`), id);
  assert.equal(getInitialConversationId("?conversation=../other-owner"), null);
  assert.equal(getInitialConversationId("?conversation="), null);
  assert.equal(getInitialConversationId(""), null);
});
