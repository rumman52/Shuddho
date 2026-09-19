import assert from "node:assert/strict";
import { readFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";

const folder = process.env.SHUDDHO_TEST_WORKDIR;
if (!folder) throw new Error("SHUDDHO_TEST_WORKDIR must point to the local browser fixture directory.");
const sessions = JSON.parse(await readFile(join(folder, "sessions.json"), "utf8"));
await mkdir(join(folder, "screenshots"), { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.SHUDDHO_TEST_BROWSER ? { executablePath: process.env.SHUDDHO_TEST_BROWSER } : {}) });
const context = await browser.newContext({ viewport: { width: 1365, height: 960 }, acceptDownloads: true });
const page = await context.newPage();
const failures = [];
page.on("pageerror", error => failures.push(error.message));
await page.route("https://identity.example.test/auth/v1/**", async route => {
  const request = route.request();
  if (request.method() === "OPTIONS") {
    await route.fulfill({ status: 204, headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:5173", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "*" } }); return;
  }
  const path = new URL(request.url()).pathname;
  if (path.endsWith("/logout")) { await route.fulfill({ status: 204 }); return; }
  if (path.endsWith("/token")) {
    const body = request.postDataJSON();
    const subject = body.email?.startsWith("bob") || body.refresh_token?.endsWith("bob") ? "bob" : "alice";
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sessions[subject]) }); return;
  }
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
});

try {
  await page.goto("http://127.0.0.1:5173/");
  await page.getByRole("button", { name: "AI coworker", exact: true }).click();
  await page.getByRole("heading", { name: "Welcome back." }).waitFor();
  await page.screenshot({ path: join(folder, "screenshots/signin.png"), fullPage: true });
  await page.getByLabel("Email", { exact: true }).fill("alice@example.test");
  await page.getByLabel("Password", { exact: true }).fill("test-password-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: "Good work starts here." }).waitFor();
  await page.getByLabel("Your notes").fill("The team completed 12 reviews on 10 September 2026.");
  await page.getByLabel("Add source files").setInputFiles({ name: "meeting.txt", mimeType: "text/plain", buffer: Buffer.from("Meeting held on 10 September 2026. The team completed 12 reviews.") });
  await page.getByRole("button", { name: "Remove meeting.txt from this task" }).waitFor();
  await page.getByLabel("Output language").selectOption("bn");
  await page.getByRole("button", { name: "Create report & email draft" }).click();
  await page.getByRole("region", { name: "Task result" }).waitFor();
  await page.getByRole("button", { name: /Writing assistant/ }).click();
  assert.equal(await page.locator(".workspace-writing").isVisible(), true);
  await page.getByRole("button", { name: "AI coworker", exact: true }).click();
  await page.reload();
  const result = page.getByRole("region", { name: "Task result" });
  await result.getByText("Ready", { exact: true }).waitFor({ timeout: 60000 });
  await result.getByRole("heading", { name: "প্রকল্পের অগ্রগতি", exact: true }).first().waitFor();
  assert.equal(await page.locator(".cw-history li").count(), 1);
  await page.screenshot({ path: join(folder, "screenshots/coworker-desktop.png"), fullPage: true });
  const pendingDownload = page.waitForEvent("download");
  await result.getByRole("button", { name: /report.docx/ }).click();
  const download = await pendingDownload;
  assert.equal(download.suggestedFilename(), "report.docx");
  await download.saveAs(join(folder, "browser-report.docx"));
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.getByRole("button", { name: "View current task", exact: true }).click();
  assert.equal(await result.evaluate(element => {
    const bounds = element.getBoundingClientRect();
    return bounds.top >= 0 && bounds.top < window.innerHeight / 2;
  }), true);
  await page.screenshot({ path: join(folder, "screenshots/coworker-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1365, height: 960 });
  await page.getByLabel("What would you like to create?").fill("Keep my custom brief while I choose a service.");
  await page.getByLabel("Work service", { exact: true }).selectOption("email");
  assert.equal(await page.getByLabel("What would you like to create?").inputValue(), "Keep my custom brief while I choose a service.");
  for (const [skill, language, preview, filename] of [
    ["email", "ar", "Email draft", "email-draft.txt"],
    ["document", "bn", "Document preview", "document.docx"],
    ["career", "en", "Document preview", "career-document.docx"],
    ["social", "bn", "Post drafts", "social-posts.txt"],
    ["meeting", "ar", "Meeting draft", "meeting-notes.docx"],
    ["daily_plan", "bn", "Proposed plan", "daily-plan.txt"],
    ["personal_plan", "en", "Proposed plan", "personal-plan.txt"],
  ]) {
    await page.getByLabel("Work service", { exact: true }).selectOption(skill);
    await page.getByLabel("What would you like to create?").fill(`Prepare ${skill} from my project notes.`);
    await page.getByLabel("Your notes").fill("The team completed 12 reviews. Draft only; no external actions.");
    await page.getByLabel("Output language").selectOption(language);
    const response = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith("/api/v1/tasks"));
    await page.getByRole("button", { name: "Create draft", exact: true }).click();
    const created = await (await response).json();
    assert.equal(created.skill_id, skill);
    const current = page.locator(`.cw-result[data-task-id="${created.id}"]`);
    await current.getByText("Ready", { exact: true }).waitFor({ timeout: 60000 });
    await current.locator("summary").filter({ hasText: preview }).waitFor();
    assert.equal(await current.locator(".cw-paper, .cw-email").first().getAttribute("lang"), language);
    const nextDownload = page.waitForEvent("download");
    await current.getByRole("button", { name: new RegExp(filename.replaceAll(".", "\\.")) }).click();
    assert.equal((await nextDownload).suggestedFilename(), filename);
    if (skill === "social") {
      await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: "http://127.0.0.1:5173" });
      await current.getByRole("button", { name: "Copy post", exact: true }).first().click();
      await current.getByText("Copied.", { exact: true }).waitFor();
      assert.equal(await page.evaluate(() => navigator.clipboard.readText()), "দলটি ১২টি পর্যালোচনা সম্পন্ন করেছে।");
      await page.reload();
      await page.locator(`.cw-result[data-task-id="${created.id}"]`).getByText("Ready", { exact: true }).waitFor();
      await page.getByRole("button", { name: "Use these sources for a new draft" }).click();
      assert.equal(await page.getByLabel("Work service", { exact: true }).inputValue(), "social");
      assert.equal(await page.getByLabel("Your notes").inputValue(), "The team completed 12 reviews. Draft only; no external actions.");
    }
    await page.locator(".workspace-coworker").evaluate(element => { element.scrollTop = 0; });
    await page.screenshot({ path: join(folder, `screenshots/service-${skill}.png`), fullPage: true });
    if (["social", "meeting", "daily_plan"].includes(skill)) {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.getByRole("button", { name: "View current task", exact: true }).click();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
      await page.screenshot({ path: join(folder, `screenshots/service-${skill}-mobile.png`), fullPage: true });
      await page.setViewportSize({ width: 1365, height: 960 });
    }
  }
  assert.equal(await page.locator(".cw-history li").count(), 8);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("heading", { name: "Welcome back." }).waitFor();
  assert.equal(await page.getByText("প্রকল্পের অগ্রগতি", { exact: true }).count(), 0);
  await page.getByLabel("Email", { exact: true }).fill("bob@example.test");
  await page.getByLabel("Password", { exact: true }).fill("test-password-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: "Good work starts here." }).waitFor();
  await page.getByRole("button", { name: "Create report & email draft" }).waitFor();
  assert.equal(await page.locator(".cw-history li").count(), 0);
  assert.equal(await page.locator(".cw-file-chips li").count(), 0);
  assert.deepEqual(failures, []);
  console.log("Browser workflow passed: login, upload, all eight work services, writing tab, refresh recovery, service-aware revision, Bangla and RTL previews, downloads, copy post, mobile layout, sign-out and account switch.");
} finally {
  await context.close();
  await browser.close();
}
