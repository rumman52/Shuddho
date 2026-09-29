import assert from "node:assert/strict";
import { join } from "node:path";

export async function verifyNotificationDigests(page, folder) {
  const digestId = "a".repeat(64);
  const notices = [1, 2].map(index => ({
    id: `0000000${index}-0000-4000-8000-000000000000`,
    automation_id: null, occurrence_id: null, kind: "personal_suggestion",
    title: index === 1 ? "Review your study plan" : "Review your project deadline",
    message: index === 1 ? "আপনার পড়াশোনার পরিকল্পনা পর্যালোচনা করুন।" : "Review the saved goal before starting work.",
    state: "delivered", visible_at: "2026-09-29T12:00:00+00:00",
    created_at: "2026-09-29T12:00:00+00:00", read_at: null,
  }));
  let withdrawn = false;
  let readRequests = 0;
  const pattern = "**/api/v1/{goals,automations,notifications,notification-preferences,notification-digests,notification-digests/*/read}";
  // UI fixtures only; backend authorization and source revocation are exercised by Python integration tests.
  const handler = async route => {
    const request = route.request();
    const headers = {
      "Access-Control-Allow-Origin": "http://127.0.0.1:5173",
      "Access-Control-Allow-Headers": "Authorization, Content-Type",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    };
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers });
      return;
    }
    const path = new URL(request.url()).pathname;
    assert.match(request.headers().authorization ?? "", /^Bearer /);
    let body;
    let status = 200;
    if (path.endsWith("/goals")) body = { enabled: true, goals: [] };
    else if (path.endsWith("/automations")) body = { enabled: true, automations: [] };
    else if (path.endsWith("/notification-preferences")) body = { in_app_enabled: true, automation_updates_enabled: true };
    else if (path.endsWith("/notifications")) body = { enabled: true, notifications: withdrawn ? [] : notices };
    else if (path.endsWith("/read")) {
      readRequests++;
      assert.equal(request.method(), "POST");
      assert.deepEqual(request.postDataJSON(), { notification_ids: notices.map(item => item.id) });
      if (withdrawn) {
        status = 409;
        body = { error: { code: "notification_digest_changed", message: "This digest changed or is no longer available. Refresh your inbox." } };
      } else {
        notices.forEach(item => { item.state = "read"; item.read_at = "2026-09-29T13:00:00+00:00"; });
        body = { id: digestId, notifications: notices.map(({ id, state, read_at }) => ({ id, state, read_at })) };
      }
    } else body = { enabled: true, digests: withdrawn ? [] : [{
      id: digestId, kind: "personal_suggestion", title: "2 goal suggestions", count: 2,
      unread_count: notices.filter(item => item.state === "delivered").length,
      latest_at: notices[0].visible_at, notifications: notices,
    }] };
    await route.fulfill({ status, headers, contentType: "application/json", body: JSON.stringify(body) });
  };
  await page.route(pattern, handler);
  try {
    await page.getByRole("button", { name: "Automations", exact: true }).click();
    const workspace = page.getByRole("region", { name: "Automations and notifications" });
    await workspace.getByText("Review your study plan", { exact: true }).waitFor();
    const toggle = workspace.getByLabel("Group suggestion notices into digests");
    assert.equal(await toggle.isChecked(), false);
    await toggle.check();
    await workspace.getByText("2 goal suggestions", { exact: true }).click();
    await workspace.getByText(notices[0].message, { exact: true }).waitFor();
    await page.screenshot({ path: join(folder, "screenshots/notification-digests-desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: join(folder, "screenshots/notification-digests-mobile.png"), fullPage: true });
    await page.setViewportSize({ width: 1365, height: 960 });
    await workspace.getByRole("button", { name: "Mark digest as read", exact: true }).click();
    await workspace.getByRole("button", { name: "All read", exact: true }).waitFor();
    assert.equal(await workspace.getByRole("button", { name: "All read", exact: true }).isDisabled(), true);
    assert.equal(readRequests, 1);
    // A source withdrawn after display must refresh away after the action returns a conflict.
    notices.forEach(item => { item.state = "delivered"; item.read_at = null; });
    await page.getByRole("button", { name: "Drafts & files", exact: true }).click();
    await page.getByRole("button", { name: "Automations", exact: true }).click();
    await workspace.getByText("Review your study plan", { exact: true }).waitFor();
    await workspace.getByLabel("Group suggestion notices into digests").check();
    withdrawn = true;
    await workspace.getByRole("button", { name: "Mark digest as read", exact: true }).click();
    await workspace.getByRole("alert").filter({ hasText: "This digest changed" }).waitFor();
    await workspace.getByText("No available digests.", { exact: false }).waitFor();
    assert.equal(readRequests, 2);
  } finally {
    await page.unroute(pattern, handler);
    await page.setViewportSize({ width: 1365, height: 960 });
    await page.getByRole("button", { name: "Drafts & files", exact: true }).click();
  }
}
