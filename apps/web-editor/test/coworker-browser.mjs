import { navigateWorkspace } from "./coworker-navigation-browser.mjs";
import assert from "node:assert/strict";
import { readFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";
import { verifyActions } from "./coworker-actions-browser.mjs";
import { verifyAgentProposals } from "./coworker-agent-browser.mjs";
import { verifyNotificationDigests } from "./coworker-notification-digests-browser.mjs";

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
  // Coworker is the approved default workspace when the release flag is enabled.
  // The unauthenticated entry exposes the first-message composer; sign-in opens
  // only after the user chooses to continue, preserving the unsent draft.
  await page.goto("http://127.0.0.1:5173/");
  await page.getByRole("heading", { name: "What shall we work on today?" }).waitFor();
  await page.getByRole("link", { name: "Fly", exact: true }).waitFor();
  await page.getByRole("link", { name: "Writing Assistant", exact: true }).waitFor();
  await page.locator("#rukh-first-message").waitFor();
  assert.equal(await page.locator("#rukh-first-message").isVisible(), true);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: join(folder, "screenshots/coworker-entry-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: join(folder, "screenshots/coworker-entry-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1365, height: 960 });
  // A direct Projects deep link on a fresh preview origin has no inherited
  // production session. It must request Projects access, never render Coworker.
  const projectsEntryPage = await context.newPage();
  await projectsEntryPage.goto("http://127.0.0.1:5173/coworker?view=projects");
  await projectsEntryPage.getByRole("heading", { name: /^Welcome back\.?$/ }).waitFor();
  await projectsEntryPage.getByText("Sign in to open Projects.", { exact: true }).waitFor();
  assert.equal(await projectsEntryPage.locator("#rukh-first-message").count(), 0);
  await projectsEntryPage.screenshot({ path: join(folder, "screenshots/projects-sign-in-desktop.png"), fullPage: true });
  await projectsEntryPage.close();

  // Signed-out navigation must work too: the Coworker control on /fly
  // previously did nothing except close the mobile menu.
  await page.getByRole("link", { name: "Fly", exact: true }).click();
  await page.waitForURL(url => url.pathname === "/fly");
  await page.getByRole("main", { name: "Rukh AI Fly" }).waitFor();
  await page.getByRole("link", { name: "Coworker", exact: true }).click();
  await page.waitForURL(url => url.pathname === "/coworker");
  await page.getByRole("main", { name: "Rukh AI Coworker" }).waitFor();
  await page.locator("#rukh-first-message").fill("Please help me prepare a short project update.");
  await page.getByRole("button", { name: "Continue to sign in" }).click();
  await page.getByRole("heading", { name: /^Welcome back\.?$/ }).waitFor();
  await page.getByLabel("Email address", { exact: true }).fill("alice@example.test");
  await page.getByLabel("Password", { exact: true }).fill("test-password-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator("#cw-conversation-message").waitFor();
  await page.locator("#cw-conversation-message").waitFor();
  assert.equal(await page.locator("#cw-conversation-message").isVisible(), true);

  // Confirm an authenticated refresh at / still restores the persistent chat workspace.
  await page.goto("http://127.0.0.1:5173/");
  await page.locator("#cw-conversation-message").waitFor();
  await page.locator("#cw-conversation-message").waitFor();

  // Projects must be reachable from the authenticated sidebar, use the approved
  // section shell, and remain selected after a full refresh.
  await navigateWorkspace(page, "Projects");
  await page.waitForURL(url => url.pathname === "/coworker" && url.searchParams.get("view") === "projects");
  await page.locator(".rukh-design-sidebar").waitFor();
  await page.locator(".rukh-design-history").waitFor();
  await page.locator(".rukh-cw-account-footer").waitFor();
  await page.locator(".rukh-section-context > summary").waitFor();
  await page.reload();
  await page.waitForURL(url => url.pathname === "/coworker" && url.searchParams.get("view") === "projects");
  await page.locator(".rukh-section-context > summary").waitFor();

  // Projects opens the dashboard first. Creation is an explicit action,
  // and cancelling it returns to the same project list.
  await page.getByRole("heading", { name: "Projects", exact: true }).first().waitFor();
  await page.getByRole("button", { name: "+ New project", exact: true }).waitFor();
  await page.getByLabel("Search projects").waitFor();
  await page.locator(".rukh-projects-page").waitFor();
  await page.screenshot({ path: join(folder, "screenshots/rukh-projects-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: join(folder, "screenshots/rukh-projects-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1365, height: 960 });

  await page.getByRole("button", { name: "+ New project", exact: true }).click();
  await page.getByRole("heading", { name: "New project", exact: true }).waitFor();
  await page.getByRole("heading", { name: "Create a project", exact: true }).waitFor();
  await page.locator(".rukh-project-create-form").waitFor();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("heading", { name: "Projects", exact: true }).first().waitFor();

  await page.getByRole("button", { name: "+ New project", exact: true }).click();
  await page.getByRole("heading", { name: "New project", exact: true }).waitFor();
  await page.getByRole("heading", { name: "Create a project", exact: true }).waitFor();
  await page.locator(".rukh-project-create-form").waitFor();
  await page.getByLabel("Project name").fill("Project chatbot QA");
  await page.getByLabel("Project instructions").fill("Always answer concisely and use the project name in context.");
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.getByRole("heading", { name: "Project chatbot QA", exact: true }).waitFor();
  await page.getByRole("link", { name: "+ New project chat", exact: true }).first().click();
  await page.waitForURL(url => url.pathname === "/coworker" && Boolean(url.searchParams.get("project")));
  await page.getByRole("region", { name: "Project context" }).waitFor();
  await page.getByText("Always answer concisely and use the project name in context.", { exact: true }).waitFor();
  const projectMessage = page.locator("#cw-conversation-message");
  await projectMessage.fill("What should Rukh know about this project?");
  await page.locator(".rukh-design-send").click();
  await page.getByText("This reply used the project instructions.", { exact: true }).waitFor();
  const chatContextResponse = await page.request.get("http://127.0.0.1:8000/fixture/chat/context");
  const chatContext = await chatContextResponse.json();
  assert.match(chatContext.messages[0].content, /Project name: Project chatbot QA/);
  assert.match(chatContext.messages[0].content, /Always answer concisely and use the project name in context\./);
  await page.getByRole("button", { name: "All projects", exact: true }).click();
  await page.waitForURL(url => url.pathname === "/coworker" && url.searchParams.get("view") === "projects");
  await page.locator(".rukh-project-card").filter({ hasText: "Project chatbot QA" }).click();
  await page.getByRole("tab", { name: /Chats/ }).click();
  await page.getByRole("link", { name: "What should Rukh know about this project?" }).waitFor();

  await navigateWorkspace(page, "Coworker");
  await page.waitForURL(url => url.pathname === "/coworker" && !url.searchParams.has("view"));
  await page.locator("#cw-conversation-message").waitFor();

  // The workspace directory is optional and remains available at /workspaces.
  await page.goto("http://127.0.0.1:5173/workspaces");
  await page.getByRole("heading", { name: "Think clearly. Move work forward." }).waitFor();
  await page.getByRole("heading", { name: "AI Coworker", exact: true }).waitFor();
  assert.equal(await page.getByRole("heading", { name: "Web Editor", exact: true }).count(), 0);
  await page.getByRole("heading", { name: "Fly", exact: true }).first().waitFor();
  await page.getByRole("heading", { name: "Writing Assistant", exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: join(folder, "screenshots/rukh-workspaces-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: join(folder, "screenshots/rukh-workspaces-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1365, height: 960 });
  await page.getByRole("link", { name: "AI Coworker", exact: true }).click();
  await page.locator("#cw-conversation-message").waitFor();
  await navigateWorkspace(page, "Fly");
  await page.waitForURL(url => url.pathname === "/fly");
  await page.getByRole("heading", { name: "Fly", exact: true }).first().waitFor();
  await page.getByRole("heading", { name: "What are we building?", exact: true }).waitFor();
  await page.getByRole("region", { name: "Terminal output" }).waitFor();
  await page.getByRole("textbox", { name: "Ask Rukh about this code" }).waitFor();
  await page.locator(".rukh-fly-v2-runtime").waitFor();
  // A Fly → Coworker switch must change both the visible application and its
  // canonical URL. Otherwise a refresh silently reopens Fly.
  await page.getByRole("link", { name: "Coworker", exact: true }).click();
  await page.waitForURL(url => url.pathname === "/coworker");
  const restoredComposer = page.locator("#cw-conversation-message");
  await restoredComposer.waitFor();
  await restoredComposer.fill("My unsent Coworker text should not redirect Fly back to Coworker.");
  assert.equal(await restoredComposer.inputValue(), "My unsent Coworker text should not redirect Fly back to Coworker.");

  // A stored Coworker draft must not override an explicit /fly deep link,
  // even after a full reload. Verify both directions repeatedly.
  await navigateWorkspace(page, "Fly");
  await page.waitForURL(url => url.pathname === "/fly");
  await page.getByRole("heading", { name: "Fly", exact: true }).first().waitFor();
  await page.reload();
  await page.getByRole("heading", { name: "Fly", exact: true }).first().waitFor();
  await page.getByRole("link", { name: "Coworker", exact: true }).click();
  await page.waitForURL(url => url.pathname === "/coworker");
  await page.locator("#cw-conversation-message").waitFor();
  await navigateWorkspace(page, "Fly");
  await page.waitForURL(url => url.pathname === "/fly");
  await page.getByRole("heading", { name: "Fly", exact: true }).first().waitFor();
  await navigateWorkspace(page, "Files & drafts");
  await page.getByLabel("Your notes").fill("The team completed 12 reviews on 10 September 2026.");
  await page.getByLabel("Add source files").setInputFiles({ name: "meeting.txt", mimeType: "text/plain", buffer: Buffer.from("Meeting held on 10 September 2026. The team completed 12 reviews.") });
  await page.getByRole("button", { name: "Remove meeting.txt from this task" }).waitFor();
  await page.getByLabel("Output language").selectOption("bn");
  await page.getByRole("button", { name: "Create report & email draft" }).click();
  await page.getByRole("region", { name: "Task result" }).waitFor();
  assert.equal(await page.getByRole("link", { name: "Web Editor", exact: true }).count(), 0);
  await page.getByRole("link", { name: "Writing Assistant", exact: true }).click();
  await page.waitForURL(url => url.pathname === "/writing");
  await page.locator(".rukh-editor-topbar-heading strong").getByText("Writing Assistant", { exact: true }).waitFor();

  // The Writing Assistant opens on its Documents landing page. Its editor
  // canvas is intentionally hidden until the owner chooses New document.
  await page.getByRole("heading", { name: "Documents", exact: true }).waitFor();
  await page.getByRole("button", { name: "New document", exact: true }).click();
  await page.getByText("Multilingual Writing Studio", { exact: true }).waitFor();

  // The Documents landing page and the writing canvas must occupy the same
  // full-width desktop canvas slot; neither may create an implicit grid track.
  await page.getByRole("button", { name: "← Documents", exact: true }).click();
  await page.getByRole("heading", { name: "Documents", exact: true }).waitFor();
  await page.setViewportSize({ width: 1366, height: 604 });
  const documentsLayout = await page.evaluate(() => {
    const rect = (selector) => {
      const element = document.querySelector(selector);
      if (!element) throw new Error("Missing Writing Assistant layout element: " + selector);
      const box = element.getBoundingClientRect();
      return { left: box.left, right: box.right, width: box.width };
    };
    return {
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      sidebar: rect(".rukh-editor-library"),
      topbar: rect(".rukh-editor-topbar"),
      dashboard: rect(".rukh-document-dashboard"),
    };
  });
  assert.ok(documentsLayout.documentWidth <= documentsLayout.viewportWidth, `Writing Assistant documents overflow horizontally: ${JSON.stringify(documentsLayout)}`);
  assert.ok(Math.abs(documentsLayout.topbar.left - documentsLayout.sidebar.right) <= 1, `Writing Assistant toolbar is detached from the sidebar: ${JSON.stringify(documentsLayout)}`);
  assert.ok(Math.abs(documentsLayout.dashboard.left - documentsLayout.sidebar.right) <= 1, `Writing Assistant documents dashboard is detached from the sidebar: ${JSON.stringify(documentsLayout)}`);
  assert.ok(documentsLayout.topbar.width > documentsLayout.viewportWidth * .75, `Writing Assistant toolbar is too narrow: ${JSON.stringify(documentsLayout)}`);
  assert.ok(documentsLayout.dashboard.width > documentsLayout.viewportWidth * .75, `Writing Assistant documents dashboard is too narrow: ${JSON.stringify(documentsLayout)}`);
  await page.screenshot({ path: join(folder, "screenshots/writing-assistant-documents-desktop.png"), fullPage: true });

  await page.getByRole("button", { name: "New document", exact: true }).click();
  await page.getByText("Multilingual Writing Studio", { exact: true }).waitFor();
  const editorLayout = await page.evaluate(() => {
    const sidebarElement = document.querySelector(".rukh-editor-library");
    const canvasElement = document.querySelector(".rukh-editor-canvas");
    if (!sidebarElement || !canvasElement) throw new Error("Missing Writing Assistant editor grid elements.");
    const sidebar = sidebarElement.getBoundingClientRect();
    const canvas = canvasElement.getBoundingClientRect();
    return { viewportWidth: window.innerWidth, documentWidth: document.documentElement.scrollWidth, sidebarRight: sidebar.right, canvasLeft: canvas.left, canvasWidth: canvas.width };
  });
  assert.ok(editorLayout.documentWidth <= editorLayout.viewportWidth, `Writing Assistant editor overflow horizontally: ${JSON.stringify(editorLayout)}`);
  assert.ok(Math.abs(editorLayout.canvasLeft - editorLayout.sidebarRight) <= 1, `Writing Assistant editor canvas is detached from the sidebar: ${JSON.stringify(editorLayout)}`);
  assert.ok(editorLayout.canvasWidth > editorLayout.viewportWidth * .75, `Writing Assistant editor canvas is too narrow: ${JSON.stringify(editorLayout)}`);
  await page.screenshot({ path: join(folder, "screenshots/writing-assistant-editor-desktop.png"), fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  const reviewToggle = page.getByRole("button", { name: /^Review ·/ });
  await reviewToggle.click();
  await page.locator(".rukh-writing-review.review-panel--open").waitFor();
  await page.keyboard.press("Escape");
  await page.locator(".rukh-writing-review:not(.review-panel--open)").waitFor();
  await page.waitForFunction(() => document.activeElement?.getAttribute("aria-controls") === "writing-review-panel");
  await reviewToggle.click();
  await page.locator(".rukh-writing-review.review-panel--open").waitFor();
  await page.locator(".review-panel-backdrop").click({ position: { x: 10, y: 10 } });
  await page.locator(".rukh-writing-review:not(.review-panel--open)").waitFor();
  await reviewToggle.click();
  await page.locator(".rukh-writing-review.review-panel--open").waitFor();
  await page.getByRole("button", { name: "Close writing review" }).click();
  await page.locator(".rukh-writing-review:not(.review-panel--open)").waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: join(folder, "screenshots/writing-assistant-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1365, height: 960 });
  await page.getByRole("button", { name: "Coworker", exact: true }).click();
  await page.waitForURL(url => url.pathname === "/coworker");
  const coworkerPage = page;
  await coworkerPage.getByRole("heading", { name: "What are we working on?" }).waitFor();
  await coworkerPage.setViewportSize({ width: 390, height: 844 });
  assert.equal(await coworkerPage.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await coworkerPage.screenshot({ path: join(folder, "screenshots/coworker-switch-mobile.png"), fullPage: true });
  await page.reload();
  await navigateWorkspace(page, "Files & drafts");
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
    ["presentation", "bn", "Presentation preview", "presentation.pptx"],
    ["spreadsheet", "ar", "Spreadsheet preview", "spreadsheet.xlsx"],
    ["research", "bn", "Research report", "research-report.docx"],
  ]) {
    await page.getByLabel("Work service", { exact: true }).selectOption(skill);
    await page.getByLabel("What would you like to create?").fill(`Prepare ${skill} from my project notes.`);
    await page.getByLabel("Your notes").fill("The team completed 12 reviews. Draft only; no external actions.");
    await page.getByLabel("Output language").selectOption(language);
    if (skill === "research") {
      await page.getByLabel("Public search query").fill("public project reviews");
      await page.getByLabel("Source date range").selectOption("week");
      assert.match(await page.locator("#cw-search-help").innerText(), /not sent to web search/);
    }
    if (skill === "spreadsheet") {
      assert.match(await page.getByLabel("Add source files").getAttribute("accept"), /\.xlsx/);
      await page.getByLabel("Add source files").setInputFiles({ name: "costs.csv", mimeType: "text/csv", buffer: Buffer.from("Item,Quantity,Unit price\nA,3,12.5\nB,2,8\nC,0,15\n") });
      await page.getByRole("button", { name: "Remove costs.csv from this task" }).waitFor();
    }
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
    const downloaded = await nextDownload;
    assert.equal(downloaded.suggestedFilename(), filename);
    if (["presentation", "spreadsheet"].includes(skill)) {
      await downloaded.saveAs(join(folder, "screenshots", filename));
      if (skill === "spreadsheet") {
        await current.getByRole("cell", { name: "37.50", exact: true }).waitFor();
        await current.getByText("costs.csv", { exact: false }).first().waitFor();
      } else {
        assert.equal(await current.getByRole("article").count(), 3);
        assert.equal(await current.locator(".cw-slide-preview .cw-eyebrow").first().getAttribute("dir"), "ltr");
        await current.getByText("Speaker notes", { exact: true }).first().click();
      }
    }
    if (skill === "social") {
      await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: "http://127.0.0.1:5173" });
      await current.getByRole("button", { name: "Copy post", exact: true }).first().click();
      await current.getByText("Copied.", { exact: true }).waitFor();
      assert.equal(await page.evaluate(() => navigator.clipboard.readText()), "দলটি ১২টি পর্যালোচনা সম্পন্ন করেছে।");
      await page.reload();
      await navigateWorkspace(page, "Files & drafts");
      await page.locator(`.cw-result[data-task-id="${created.id}"]`).getByText("Ready", { exact: true }).waitFor();
      await page.getByRole("button", { name: "Use these sources for a new draft" }).click();
      assert.equal(await page.getByLabel("Work service", { exact: true }).inputValue(), "social");
      assert.equal(await page.getByLabel("Your notes").inputValue(), "The team completed 12 reviews. Draft only; no external actions.");
    }
    if (skill === "research") {
      const link = current.getByRole("link", { name: /Example project update/ });
      assert.equal(await link.getAttribute("href"), "https://example.org/project-update");
      assert.equal(await link.getAttribute("rel"), "noopener noreferrer");
      assert.equal(await link.getAttribute("referrerpolicy"), "no-referrer");
      await current.locator(".cw-evidence summary").click();
      assert.equal(await current.locator("blockquote p").textContent(), "The team completed 12 reviews.");
      await downloaded.saveAs(join(folder, "screenshots", filename));
      await page.reload();
      await navigateWorkspace(page, "Files & drafts");
      await current.getByText("Ready", { exact: true }).waitFor();
      await page.getByRole("button", { name: "Use these sources for a new draft" }).click();
      assert.equal(await page.getByLabel("Work service", { exact: true }).inputValue(), "research");
      assert.equal(await page.getByLabel("Public search query").inputValue(), "public project reviews");
      assert.equal(await page.getByLabel("Source date range").inputValue(), "week");
      await current.locator(".cw-evidence summary").click();
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: join(folder, `screenshots/service-${skill}.png`), fullPage: true });
    if (["social", "meeting", "daily_plan", "presentation", "spreadsheet", "research"].includes(skill)) {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.getByRole("button", { name: "View current task", exact: true }).click();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
      await page.screenshot({ path: join(folder, `screenshots/service-${skill}-mobile.png`), fullPage: true });
      await page.setViewportSize({ width: 1365, height: 960 });
    }
  }
  assert.equal(await page.locator(".cw-history li").count(), 11);
  await verifyActions(page, folder);
  await verifyAgentProposals(page, folder);
  await verifyNotificationDigests(page, folder);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: /^Welcome back\.?$/ }).waitFor();
  assert.equal(await page.getByText("প্রকল্পের অগ্রগতি", { exact: true }).count(), 0);
  await page.getByLabel("Email address", { exact: true }).fill("bob@example.test");
  await page.getByLabel("Password", { exact: true }).fill("test-password-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.locator("#cw-conversation-message").waitFor();
  await navigateWorkspace(page, "Files & drafts");
  await page.getByRole("button", { name: "Create report & email draft" }).waitFor();
  assert.equal(await page.locator(".cw-history li").count(), 0);
  assert.equal(await page.locator(".cw-file-chips li").count(), 0);
  await navigateWorkspace(page, "Plugins");
  await page.getByRole("button", { name: "Connect Gmail", exact: true }).waitFor();
  assert.equal(await page.locator(".cw-actions .cw-history li").count(), 0);
  assert.equal(await page.getByRole("button", { name: "Disconnect Calendar", exact: true }).count(), 0);
  assert.deepEqual(failures, []);
  console.log("Browser workflow passed: login, Coworker chat, Fly coding workbench, Writing Assistant, uploads, all eleven work services, refresh recovery, service-aware revision, Bangla and RTL previews, editable PPTX/XLSX downloads, formula values, research citations and query restoration, copy post, mobile layout, sign-out and account switch.");
} finally {
  await context.close();
  await browser.close();
}
