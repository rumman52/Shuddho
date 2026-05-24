import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const extensionRoot = resolve(process.cwd());
const distRoot = resolve(extensionRoot, "dist");
const defaultApiBaseUrl = "http://127.0.0.1:4000";
const apiBaseUrl = resolveApiBaseUrl(
  process.env.SHUDDHO_EXTENSION_API_BASE_URL ?? process.env.SHUDDHO_API_BASE_URL ?? defaultApiBaseUrl
);

mkdirSync(distRoot, { recursive: true });

for (const file of ["manifest.json", "src/popup.html"]) {
  const source = resolve(extensionRoot, file);
  const target = resolve(distRoot, file === "src/popup.html" ? "popup.html" : file);
  mkdirSync(dirname(target), { recursive: true });
  if (existsSync(source)) {
    if (file === "manifest.json") {
      const manifest = JSON.parse(readFileSync(source, "utf8"));
      const hostPermissions = new Set(manifest.host_permissions ?? []);
      hostPermissions.add(`${new URL(apiBaseUrl).origin}/*`);
      manifest.host_permissions = [...hostPermissions];
      writeFileSync(target, `${JSON.stringify(manifest, null, 2)}\n`);
      continue;
    }

    cpSync(source, target, { force: true });
  }
}

replaceTokenInDirectory(distRoot, "__SHUDDHO_EXTENSION_API_BASE_URL__", apiBaseUrl);

function resolveApiBaseUrl(value) {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error(`Unsupported SHUDDHO extension API protocol: ${url.protocol}`);
  }

  return value.replace(/\/+$/, "");
}

function replaceTokenInDirectory(directory, token, replacement) {
  for (const entry of readdirSync(directory)) {
    const entryPath = resolve(directory, entry);
    const entryStat = statSync(entryPath);
    if (entryStat.isDirectory()) {
      replaceTokenInDirectory(entryPath, token, replacement);
      continue;
    }

    if (!entryPath.endsWith(".js")) {
      continue;
    }

    const content = readFileSync(entryPath, "utf8");
    if (!content.includes(token)) {
      continue;
    }

    writeFileSync(entryPath, content.replaceAll(token, replacement));
  }
}
