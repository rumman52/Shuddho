import { copyFile, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "esbuild";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const outdir = join(root, ".test-dist");
const tests = [
  "src/lib/api.test.ts",
  "src/lib/analysis.test.ts",
  "src/App.test.tsx",
  "src/lib/preferences.test.ts",
  "src/lib/runtimeStatus.test.ts",
  "src/lib/textSurface.test.ts",
];

await rm(outdir, { recursive: true, force: true });
await mkdir(outdir, { recursive: true });
await copyFile(join(root, "src/App.tsx"), join(outdir, "App.tsx"));

for (const testFile of tests) {
  const outfile = join(outdir, testFile.replace(/\W+/g, "_") + ".mjs");
  await build({
    entryPoints: [join(root, testFile)],
    outfile,
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node18",
    sourcemap: "inline",
    define: {
      "import.meta.env.PROD": "false",
      "import.meta.env.DEV": "true",
      "import.meta.env.VITE_USE_GATEWAY": '"true"',
      "import.meta.env.VITE_ENABLE_LOCAL_FALLBACK": '"false"',
      "import.meta.env.VITE_API_BASE_URL": '"https://shuddho-api.onrender.com"',
    },
  });
  await import(pathToFileURL(outfile));
}

await rm(outdir, { recursive: true, force: true });
