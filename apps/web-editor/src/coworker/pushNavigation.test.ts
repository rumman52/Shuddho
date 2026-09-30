import test from "node:test";
import assert from "node:assert/strict";
import { requestedNotificationView } from "./pushNavigation";

test("only the bounded push destination opens automations", () => {
  assert.equal(requestedNotificationView("?view=automations"), "automations");
  assert.equal(requestedNotificationView("?view=actions"), null);
  assert.equal(requestedNotificationView("?view=https://evil.example"), null);
  assert.equal(requestedNotificationView(""), null);
});
