import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const extensionRoot = resolve(process.cwd());
const distRoot = resolve(extensionRoot, "dist");

mkdirSync(distRoot, { recursive: true });

for (const file of ["manifest.json", "src/popup.html"]) {
  const source = resolve(extensionRoot, file);
  const target = resolve(distRoot, file === "src/popup.html" ? "popup.html" : file);
  mkdirSync(dirname(target), { recursive: true });
  if (existsSync(source)) {
    cpSync(source, target, { force: true });
  }
}
