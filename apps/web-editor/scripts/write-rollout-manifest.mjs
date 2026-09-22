import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

function flag(name) {
  return String(process.env[name] ?? "").toLowerCase() === "true";
}

const revision =
  process.env.VERCEL_GIT_COMMIT_SHA
  || process.env.GITHUB_SHA
  || process.env.SHUDDHO_BUILD_REVISION
  || "unknown";

const manifest = {
  schema_version: 1,
  app: "shuddho-web-editor",
  source_revision: revision,
  coworker_enabled: flag("VITE_COWORKER_ENABLED"),
  microsoft_actions_enabled: flag("VITE_MICROSOFT_ACTIONS_ENABLED"),
};

const outdir = join(process.cwd(), "dist");
await mkdir(outdir, { recursive: true });
await writeFile(
  join(outdir, "shuddho-rollout-manifest.json"),
  JSON.stringify(manifest, null, 2) + "\n",
  "utf8",
);
