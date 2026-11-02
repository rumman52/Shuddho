import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = resolve(appRoot, "src");

function assertRelativeImportsResolve(file) {
  const source = readFileSync(file, "utf8");
  const imports = [...source.matchAll(/(?:from\\s*|import\\s*)["'](\\.[^"']+)["']/g)];
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
  assert.match(readFileSync(app, "utf8"), /export\\s+default/);
});
