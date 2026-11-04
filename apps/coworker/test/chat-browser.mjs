// Real-browser UI checks against a synthetic API. No live AI/provider claim.
// RUKH_BROWSER_EXECUTABLE=/path/to/chromium node apps/coworker/test/chat-browser.mjs
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createServer } from "node:http";
import { build } from "esbuild";
import { chromium } from "playwright";

const output = await mkdtemp(join(tmpdir(), "rukh-chat-browser-"));
await mkdir(join(output, "screenshots"));
await build({ entryPoints: ["apps/coworker/test/chat-browser-fixture.tsx"], bundle: true,
  outfile: join(output, "index.js"), platform: "browser", format: "esm", jsx: "automatic",
  define: { "import.meta.env": "{}", "process.env.NODE_ENV": '"production"' } });
await writeFile(join(output, "index.html"), '<!doctype html><html lang="en"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/index.css"><div id="root"></div><script type="module" src="/index.js"></script></html>');
const server = createServer(async (request, response) => {
  const file = ({ "/": "index.html", "/index.js": "index.js", "/index.css": "index.css" })[request.url];
  if (!file) { response.writeHead(404).end(); return; }
  response.setHeader("Content-Type", file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html");
  response.end(await readFile(join(output, file)));
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
const results = [];
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.RUKH_BROWSER_EXECUTABLE || undefined,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"] });
  for (const [name, width, height] of [["desktop", 1440, 1000], ["laptop", 1366, 768], ["tablet", 1024, 768], ["mobile", 390, 844], ["small-mobile", 375, 812]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    // Optional local copy of the same Bengali webfont for offline CI hosts.
    // No production font/dependency is substituted by this fixture.
    await page.route("https://**/*", route => route.abort());
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    if (process.env.RUKH_BROWSER_BENGALI_FONT) {
      const font = await readFile(process.env.RUKH_BROWSER_BENGALI_FONT);
      await page.addStyleTag({ content: `@font-face{font-family:"Noto Serif Bengali";src:url(data:font/woff2;base64,${font.toString("base64")}) format("woff2");font-weight:400;font-style:normal;font-display:swap;}` });
      await page.evaluate(() => document.fonts.ready);
    }
    const composer = page.getByRole("textbox", { name: "New message", exact: true });
    await composer.waitFor();
    await page.getByRole("button", { name: "Chat with Rukh", exact: true }).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${name}: horizontal overflow`);
    const composerBounds = await page.locator(".rukh-message-composer").boundingBox();
    assert.ok(composerBounds.y >= 0 && composerBounds.y + composerBounds.height <= height, `${name}: composer must be in the initial viewport`);
    await page.screenshot({ path: join(output, "screenshots", `${name}-empty.png`), fullPage: true });
    await composer.fill("Help me plan my study week");
    await composer.press("Enter");
    await page.getByText("Let’s turn that idea into a clear plan.", { exact: false }).waitFor();
    assert.equal(await page.getByRole("region", { name: "Rukh AI reply" }).count(), 1);
    await composer.fill("বাংলায় পরিকল্পনাটি বুঝিয়ে বলুন");
    await composer.press("Shift+Enter");
    assert.match(await composer.inputValue(), /\n$/);
    await composer.press("Enter");
    await page.waitForFunction(() => document.querySelectorAll(".rukh-answer-text").length === 2);
    await composer.waitFor({ state: "visible" });
    const afterReply = await page.locator(".rukh-message-composer").boundingBox();
    assert.ok(afterReply.y >= 0 && afterReply.y + afterReply.height <= height, `${name}: replies must not push composer below viewport`);
    assert.ok(await page.locator(".rukh-message-list").evaluate(list => list.scrollHeight - list.scrollTop - list.clientHeight < 96), `${name}: new reply is visible`);
    await page.screenshot({ path: join(output, "screenshots", `${name}-chat.png`), fullPage: true });
    if (width <= 1220) {
      const trigger = page.getByRole("button", { name: "Open conversations", exact: true });
      await trigger.click();
      const search = page.getByRole("searchbox", { name: "Search conversations" });
      await search.fill("study");
      assert.equal(await page.locator(".rukh-conversation-items li").count(), 1);
      await page.keyboard.press("Escape");
      await page.waitForFunction(() => document.activeElement?.getAttribute("aria-label") === "Open conversations");
    }
    await page.getByRole("button", { name: "New conversation", exact: true }).click();
    assert.equal(await composer.inputValue(), "");
    await page.getByText("What should we work on?", { exact: true }).waitFor();
    const theme = page.getByRole("button", { name: /Switch to dark theme/ });
    await theme.click();
    await page.screenshot({ path: join(output, "screenshots", `${name}-dark.png`), fullPage: true, animations: "disabled" });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, [], `${name}: browser errors`);
    results.push({ viewport: name, width, height, passed: true });
    await page.close();
  }
  await writeFile(join(output, "results.json"), JSON.stringify({ fixture: "synthetic API; real workspace UI", results }, null, 2));
  console.log(JSON.stringify({ results, screenshots: resolve(output, "screenshots") }, null, 2));
} finally {
  await browser?.close();
  server.close();
}
