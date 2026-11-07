import { copyFile, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "esbuild";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const outdir = join(root, ".test-dist");
const tests = [
  "test/app-routes.test.mjs",
  "test/rukh-home.test.tsx",
  "test/editor-feature-gate.test.tsx",
  "test/coworker-app-navigation.test.tsx",
  "test/fly-workspace.test.tsx",
  "test/editor-workspace-layout.test.tsx",
  "test/rukh-responsive-ui.test.tsx",
  "test/rukh-responsive-css.test.mjs",
  "src/coworker/client.test.ts",
  "src/coworker/CoworkerGate.test.tsx",
  "src/coworker/CoworkerWorkspace.test.tsx",
  "src/coworker/refreshOrder.test.ts",
  "src/coworker/conversationIdentity.test.tsx",
  "src/coworker/conversationUsability.test.tsx",
  "src/coworker/ProjectWorkspace.test.tsx",
  "src/coworker/conversationExport.test.ts",
  "src/coworker/markdownMessage.test.tsx",
  "src/coworker/speech.test.ts",
  "src/coworker/VoiceDictation.test.tsx",
  "src/coworker/ConversationReply.test.tsx",
  "src/coworker/conversationRunStatus.test.tsx",
  "src/coworker/agentSubmissionIdentity.test.tsx",
  "src/coworker/goalRunIdentity.test.tsx",
  "src/coworker/connectorGrantAdmission.test.tsx",
  "src/coworker/pushNavigation.test.ts",
  "src/coworker/actions.test.ts",
  "src/lib/api.test.ts",
  "src/lib/analysis.test.ts",
  "src/lib/llmStatus.test.ts",
  "src/lib/suggestionAdapter.test.ts",
  "src/lib/suggestionTransaction.test.ts",
  "src/lib/fetchWithTimeout.test.ts",
  "src/App.test.tsx",
  "src/lib/preferences.test.ts",
  "src/lib/runtimeStatus.test.ts",
  "src/lib/textSurface.test.ts",
  "src/lib/competitionDemo.test.ts",
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
    loader: { ".woff2": "dataurl" },
    external: ["react", "react-dom/*", "react-test-renderer"],
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
      "import.meta.env.VITE_COMPETITION_DEMO_MODE": '"true"',
      "import.meta.env.VITE_MICROSOFT_ACTIONS_ENABLED": '"false"',
      "import.meta.env.VITE_COWORKER_ENABLED": JSON.stringify(["test/editor-workspace-layout.test.tsx", "test/rukh-responsive-ui.test.tsx"].includes(testFile) ? "true" : "false"),
      "import.meta.env.VITE_SUPABASE_URL": '""',
      "import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY": '""',
      "import.meta.env.VITE_COWORKER_API_BASE_URL": '"/backend"',
      "import.meta.env.VITE_COWORKER_APP_URL": '"/coworker"',
      "import.meta.env.VITE_EDITOR_APP_URL": '"/writing"',
    },
  });
  await import(pathToFileURL(outfile));
}

await rm(outdir, { recursive: true, force: true });
