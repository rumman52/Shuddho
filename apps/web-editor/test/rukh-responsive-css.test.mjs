import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

const cwd = process.cwd();

test("Rukh design tokens use the researched green accent and define a dark theme", async () => {
  const css = await readFile(join(cwd, "../../packages/design-system/src/tokens.css"), "utf8");
  assert.match(css, /--rukh-accent:\s*#176b5b/i);
  assert.match(css, /\[data-rukh-theme="dark"\]/);
});

test("Coworker mobile sheets and touch targets are defined", async () => {
  const css = await readFile(join(cwd, "../coworker/src/styles.css"), "utf8");
  assert.match(css, /rukh-mobile-panel-open/);
  assert.match(css, /rukh-mobile-backdrop/);
  assert.match(css, /min-height:\s*44px/);
});

test("Coworker task drafts collapse to one column at mobile widths", async () => {
  const css = await readFile(join(cwd, "../coworker/src/styles.css"), "utf8");
  assert.match(css, /@media\s*\(max-width:\s*680px\)[\s\S]*?\.cw-layout\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
});

test("Editor mobile layout removes the fixed desktop-height canvas", async () => {
  const css = await readFile(join(cwd, "../editor/src/styles.css"), "utf8");
  const appEntry = await readFile(join(cwd, "src/main.tsx"), "utf8");
  assert.match(appEntry, /import "\.\.\/\.\.\/editor\/src\/styles\.css";/);
  assert.match(css, /rukh-editor-library--open/);
  assert.match(css, /rukh-editor-mobile-backdrop/);
  assert.doesNotMatch(css, /flex:\s*0\s+0\s+720px/);
  assert.match(css, /\.rukh-writing-workspace/);
  assert.match(css, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(300px,\s*360px\)/);
  assert.match(css, /\.review-panel-backdrop/);
  assert.match(css, /\.review-panel--open/);
  assert.match(css, /@media\s*\(max-width:\s*900px\)/);
});

test("assistant Markdown wraps long Unicode replies and contains code and tables on narrow screens", async () => {
  const css = await readFile(join(cwd, "src/coworker/markdown-message.css"), "utf8");
  assert.match(css, /\.rukh-markdown\s*\{[^}]*max-width:\s*100%[^}]*min-width:\s*0[^}]*overflow-wrap:\s*anywhere/s);
  assert.match(css, /\.rukh-markdown\s+pre\s*\{[^}]*max-width:\s*100%[^}]*overflow:\s*auto/s);
  assert.match(css, /\.rukh-markdown-table-scroll\s*\{[^}]*max-width:\s*100%[^}]*overflow-x:\s*auto/s);
});


test("Coworker follows the approved palette and keeps its composer outside transcript scrolling", async () => {
  const css = await readFile(join(cwd, "../coworker/src/styles.css"), "utf8");
  assert.match(css, /--rukh-bg:\s*#FAFAF7/i);
  assert.match(css, /--rukh-accent:\s*#245A43/i);
  assert.match(css, /\.rukh-message-list\s*\{[^}]*flex:\s*1 1 auto[^}]*overflow-y:\s*auto/s);
  assert.match(css, /\.rukh-message-composer\s*\{[^}]*position:\s*sticky[^}]*bottom:\s*0/s);
  assert.match(css, /\.rukh-conversation-list\.rukh-mobile-panel-open/);
  assert.match(css, /@media\s*\(max-width:\s*900px\)/);
});

test("Writing Assistant desktop documents and editor views share one explicit canvas grid area", async () => {
  const css = await readFile(join(cwd, "../editor/src/styles.css"), "utf8");
  const desktopShell = css.slice(css.lastIndexOf(".rukh-editor-app:has(.rukh-editor-library) {"));

  assert.match(desktopShell, /grid-template-areas:\s*"library topbar"\s*"library canvas"/);
  assert.match(desktopShell, /\.rukh-editor-app:has\(\.rukh-editor-library\)\s+\.rukh-editor-topbar\s*\{[^}]*grid-area:\s*topbar/s);
  assert.match(desktopShell, /\.rukh-editor-app:has\(\.rukh-editor-library\)\s+\.rukh-editor-library\s*\{[^}]*grid-area:\s*library/s);
  assert.match(desktopShell, /\.rukh-editor-app:has\(\.rukh-editor-library\)\s+\.rukh-editor-canvas\s*\{[^}]*grid-area:\s*canvas/s);
  assert.match(css, /\.rukh-document-dashboard\s*\{[^}]*grid-area:\s*canvas/s);
});
