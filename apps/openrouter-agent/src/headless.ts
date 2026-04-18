import { config as loadDotEnv } from "dotenv";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { createInterface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { createAgent } from "./agent.js";
import { defaultTools } from "./tools.js";

const CURRENT_FILE = fileURLToPath(import.meta.url);
const CURRENT_DIR = dirname(CURRENT_FILE);
const REPO_ROOT = resolve(CURRENT_DIR, "..", "..", "..");

loadDotEnv({ path: resolve(REPO_ROOT, ".env") });

async function main(): Promise<void> {
  const apiKey = process.env.OPENROUTER_API_KEY?.trim();
  if (!apiKey || apiKey.includes("your_openrouter_api_key") || apiKey.toLowerCase().includes("placeholder")) {
    throw new Error(
      "OPENROUTER_API_KEY is missing or still a placeholder. Set it in the repo-root .env before starting the agent.",
    );
  }

  const model = process.env.OPENROUTER_AGENT_MODEL?.trim()
    || process.env.OPENROUTER_MODEL?.trim()
    || "openrouter/auto";

  const agent = createAgent({
    apiKey,
    model,
    instructions:
      "You are a practical OpenRouter-powered CLI agent inside the Shuddho repository. Be concise, use tools when helpful, and prefer actionable answers.",
    tools: [...defaultTools],
    maxSteps: 5,
    httpReferer: process.env.OPENROUTER_AGENT_SITE_URL?.trim() || undefined,
    appTitle: process.env.OPENROUTER_AGENT_TITLE?.trim() || "Shuddho OpenRouter Agent",
    timeoutMs: 30_000,
  });

  let assistantPrefixPrinted = false;
  agent.on("stream:start", () => {
    assistantPrefixPrinted = false;
  });
  agent.on("stream:delta", (delta) => {
    if (!assistantPrefixPrinted) {
      output.write("Assistant: ");
      assistantPrefixPrinted = true;
    }
    output.write(delta);
  });
  agent.on("stream:end", () => {
    output.write("\n");
  });
  agent.on("tool:call", (name, args) => {
    output.write(`\n[tool:${name}] ${JSON.stringify(args)}\n`);
  });
  agent.on("tool:result", (callId, result) => {
    output.write(`[tool-result:${callId}] ${JSON.stringify(result)}\n`);
  });
  agent.on("error", (error) => {
    output.write(`\n[error] ${error.message}\n`);
  });

  const rl = createInterface({ input, output });
  output.write(
    [
      "OpenRouter Agent Quickstart",
      `Model: ${agent.model}`,
      "Type a message and press Enter.",
      "Commands: /clear resets history, /exit quits.",
      "",
    ].join("\n"),
  );

  try {
    while (true) {
      const message = (await rl.question("You: ")).trim();
      if (!message) {
        continue;
      }
      if (message === "/exit" || message === "exit" || message === "quit") {
        break;
      }
      if (message === "/clear") {
        agent.clearHistory();
        output.write("Conversation history cleared.\n");
        continue;
      }

      await agent.send(message);
    }
  } finally {
    rl.close();
  }
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Failed to start OpenRouter agent: ${message}`);
  process.exitCode = 1;
});
