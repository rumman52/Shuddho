import assert from "node:assert/strict";
import { test } from "node:test";
import { chromium } from "playwright";
import { navigateWorkspace } from "./coworker-navigation-browser.mjs";

const markup = [
  '<style>',
  '  .rukh-mobile-workspace-tools { display: block; }',
  '  #rukh-conversation-list { display: none; }',
  '  #rukh-conversation-list.rukh-mobile-panel-open { display: block; }',
  '  @media (min-width: 901px) {',
  '    .rukh-mobile-workspace-tools { display: none; }',
  '    #rukh-conversation-list { display: block; }',
  '  }',
  '</style>',
  '<div id="mount" aria-live="polite">Restoring authenticated workspace…</div>',
  '<div id="visited"></div>',
].join("");

async function mountNavigation(page, delayMs) {
  await page.setContent(markup);
  await page.evaluate(delay => {
    setTimeout(() => {
      const mount = document.getElementById("mount");
      mount.innerHTML = [
        '<div class="rukh-mobile-workspace-tools">',
        '  <button type="button" aria-label="Open navigation">Navigation</button>',
        '</div>',
        '<aside id="rukh-conversation-list" class="rukh-conversation-list">',
        '  <button type="button" data-view="projects">Projects</button>',
        '  <details class="rukh-design-more-tools">',
        '    <summary>More tools</summary>',
        '    <nav aria-label="Additional tools">',
        '      <button type="button" data-view="drafts">Files &amp; drafts</button>',
        '    </nav>',
        '  </details>',
        '</aside>',
      ].join("");
      mount.querySelector("[aria-label='Open navigation']").addEventListener("click", () => {
        mount.querySelector("#rukh-conversation-list").classList.add("rukh-mobile-panel-open");
      });
      for (const target of mount.querySelectorAll("[data-view]")) {
        target.addEventListener("click", () => {
          document.getElementById("visited").textContent = target.getAttribute("data-view");
        });
      }
    }, delay);
  }, delayMs);
}

test("mobile navigation waits for restored workspace and opens hidden disclosure", async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await mountNavigation(page, 125);
    await navigateWorkspace(page, "Files & drafts");
    assert.equal(await page.locator("#visited").textContent(), "drafts");
    assert.equal(await page.locator("#rukh-conversation-list").getAttribute("class"),
      "rukh-conversation-list rukh-mobile-panel-open");
    assert.equal(await page.locator("details.rukh-design-more-tools").evaluate(element => element.open), true);
    await page.close();
  } finally {
    await browser.close();
  }
});

test("desktop navigation selects visible workspace directly after hydration", async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1365, height: 960 } });
    await mountNavigation(page, 125);
    await navigateWorkspace(page, "Projects");
    assert.equal(await page.locator("#visited").textContent(), "projects");
    assert.equal(await page.locator("details.rukh-design-more-tools").evaluate(element => element.open), false);
    await page.close();
  } finally {
    await browser.close();
  }
});
