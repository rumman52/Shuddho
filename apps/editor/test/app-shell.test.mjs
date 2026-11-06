import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = resolve(appRoot, "src");

function assertRelativeImportsResolve(file) {
  const source = readFileSync(file, "utf8");
  const imports = [...source.matchAll(/(?:from\s*|import\s*)["'](\.[^"']+)["']/g)];
  for (const [, specifier] of imports) {
    const target = resolve(dirname(file), specifier);
    const candidates = [
      target,
      ...[".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".json"].map(extension => target + extension),
      ...["index.ts", "index.tsx", "index.js", "index.mjs"].map(name => resolve(target, name)),
    ];
    assert.ok(candidates.some(existsSync), `Missing local import "${specifier}" from ${file}`);
  }
}

test("Editor standalone app entry resolves every local module and stylesheet", () => {
  const entry = resolve(sourceRoot, "main.tsx");
  const app = resolve(sourceRoot, "App.tsx");
  assert.ok(existsSync(app), "Standalone app must provide src/App.tsx");
  assert.ok(existsSync(resolve(sourceRoot, "styles.css")), "Standalone app must provide src/styles.css");
  assertRelativeImportsResolve(entry);
  assertRelativeImportsResolve(app);
  assert.match(readFileSync(app, "utf8"), /export\s+default/);
});


test("Writing Assistant exposes a document-library landing page with real document actions", () => {
  const app = readFileSync(resolve(sourceRoot, "App.tsx"), "utf8");
  assert.match(app, /Documents/);
  assert.match(app, /New document/);
  assert.match(app, /Upload file/);
  assert.match(app, /Search documents/);
  assert.match(app, /Version history/);
  assert.match(app, /Trash/);
  assert.match(app, /client\.documents\(/);
  assert.match(app, /client\.upload\(/);
  assert.match(app, /client\.deleteDocument\(/);
  assert.match(app, /client\.readTextDocument\(/);
});

test("Writing Assistant document cards use responsive Rukh theme tokens", () => {
  const css = readFileSync(resolve(sourceRoot, "styles.css"), "utf8");
  assert.match(css, /\.rukh-document-dashboard/);
  assert.match(css, /\.rukh-document-card/);
  assert.match(css, /var\(--rukh-accent\)/);
  assert.match(css, /@media\s*\(max-width:\s*900px\)/);
});
