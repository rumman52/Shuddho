import http from "node:http";
import net from "node:net";
import dns from "node:dns/promises";
import os from "node:os";
import { chromium } from "playwright";
import { normalizedBaseUrl, parseConnectAuthority, safeWorkerId } from "./browser_worker_policy.mjs";

const API_BASE = normalizedBaseUrl(process.env.SHUDDHO_BROWSER_API_BASE_URL || "http://127.0.0.1:8000");
const WORKER_TOKEN = process.env.SHUDDHO_BROWSER_WORKER_TOKEN || "";
const WORKER_ID = safeWorkerId(
  process.env.SHUDDHO_BROWSER_WORKER_ID || `browser-${os.hostname().replace(/[^A-Za-z0-9_.:-]/g, "-").slice(0, 48)}`
);
const POLL_MS = Math.max(250, Math.min(Number(process.env.SHUDDHO_BROWSER_POLL_MS || "1000"), 5000));
const NAVIGATION_TIMEOUT_MS = Math.max(
  3000,
  Math.min(Number(process.env.SHUDDHO_BROWSER_NAVIGATION_TIMEOUT_MS || "15000"), 25000),
);

if (WORKER_TOKEN.length < 32) {
  throw new Error("SHUDDHO_BROWSER_WORKER_TOKEN must contain at least 32 characters");
}

let stopping = false;
process.on("SIGTERM", () => { stopping = true; });
process.on("SIGINT", () => { stopping = true; });

async function api(path, body) {
  const response = await fetch(API_BASE + path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Shuddho-Browser-Worker-Token": WORKER_TOKEN,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10000),
  });
  const text = await response.text();
  let value = {};
  try { value = text ? JSON.parse(text) : {}; } catch {}
  if (!response.ok) {
    const code = value?.error?.code || `http_${response.status}`;
    throw Object.assign(new Error(code), { code, status: response.status });
  }
  return value;
}

async function validateHost(commandId, host) {
  const answers = await dns.lookup(host, { all: true, verbatim: true });
  const addresses = [...new Set(answers.map((item) => item.address))];
  return api(`/api/v1/internal/browser-worker/commands/${commandId}/network-check`, {
    worker_id: WORKER_ID,
    url: `https://${host}/`,
    resolved_ips: addresses,
  });
}

async function createPinnedProxy(command, evidence) {
  const sockets = new Set();
  const server = http.createServer((_req, res) => {
    res.writeHead(403, { "Content-Type": "text/plain", "Connection": "close" });
    res.end("HTTPS CONNECT only");
  });

  server.on("connect", async (req, clientSocket, head) => {
    let target;
    try {
      target = parseConnectAuthority(req.url || "");
      const checked = await validateHost(command.id, target.host);
      evidence[checked.hostname] = checked.resolved_ips;
      const pinnedIp = checked.resolved_ips[0];
      const upstream = net.connect({ host: pinnedIp, port: 443 });
      sockets.add(upstream);
      sockets.add(clientSocket);
      upstream.setTimeout(NAVIGATION_TIMEOUT_MS);

      upstream.once("connect", () => {
        clientSocket.write("HTTP/1.1 200 Connection Established\r\nProxy-Agent: shuddho-browser-worker\r\n\r\n");
        if (head?.length) upstream.write(head);
        clientSocket.pipe(upstream);
        upstream.pipe(clientSocket);
      });
      upstream.once("timeout", () => upstream.destroy(new Error("upstream_timeout")));
      upstream.once("close", () => sockets.delete(upstream));
      clientSocket.once("close", () => sockets.delete(clientSocket));
      upstream.once("error", () => clientSocket.destroy());
      clientSocket.once("error", () => upstream.destroy());
    } catch {
      clientSocket.write("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
      clientSocket.destroy();
    }
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("proxy_bind_failed");
  return {
    server,
    url: `http://127.0.0.1:${address.port}`,
    destroy() {
      for (const socket of sockets) socket.destroy();
      sockets.clear();
    },
  };
}

async function monitorControl(commandId, onStop) {
  let finished = false;
  const loop = (async () => {
    while (!finished && !stopping) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      if (finished || stopping) break;
      try {
        const control = await api(`/api/v1/internal/browser-worker/commands/${commandId}/control`, {
          worker_id: WORKER_ID,
        });
        if (control.action === "stop" || control.action === "pause") {
          await onStop(control);
          break;
        }
      } catch (error) {
        if (error?.code === "browser_worker_claim_invalid") {
          await onStop({ action: "stop", reason: "claim_lost" });
          break;
        }
      }
    }
  })();
  return {
    async finish() {
      finished = true;
      await loop;
    },
  };
}

async function resolveFormField(page, spec) {
  const candidates = [];
  if (spec.by === "label") {
    const locator = page.getByLabel(spec.field, { exact: true });
    const count = await locator.count();
    for (let index = 0; index < count; index += 1) candidates.push(locator.nth(index));
  } else if (spec.by === "name") {
    const locator = page.locator("input, textarea");
    const count = await locator.count();
    for (let index = 0; index < count; index += 1) {
      const item = locator.nth(index);
      if ((await item.getAttribute("name")) === spec.field) candidates.push(item);
    }
  }
  if (candidates.length === 0) {
    throw Object.assign(new Error("form_field_not_found"), { code: "form_field_not_found" });
  }
  if (candidates.length !== 1) {
    throw Object.assign(new Error("form_field_ambiguous"), { code: "form_field_ambiguous" });
  }
  return candidates[0];
}

async function fillPreparedField(page, spec) {
  const locator = await resolveFormField(page, spec);
  const metadata = await locator.evaluate((element) => ({
    tag: element.tagName.toLowerCase(),
    type: (element.getAttribute("type") || "text").toLowerCase(),
    autocomplete: (element.getAttribute("autocomplete") || "").toLowerCase(),
    disabled: Boolean(element.disabled),
    readOnly: Boolean(element.readOnly),
  }));
  const blockedTypes = new Set(["password", "file", "hidden", "submit", "button", "image", "checkbox", "radio"]);
  const sensitiveAutocomplete = new Set(["current-password", "new-password", "one-time-code", "cc-number", "cc-csc"]);
  if (
    metadata.disabled
    || metadata.readOnly
    || !["input", "textarea"].includes(metadata.tag)
    || blockedTypes.has(metadata.type)
  ) {
    throw Object.assign(new Error("form_field_not_editable"), { code: "form_field_not_editable" });
  }
  if (sensitiveAutocomplete.has(metadata.autocomplete)) {
    throw Object.assign(new Error("sensitive_field_requires_takeover"), { code: "sensitive_field_requires_takeover" });
  }
  await locator.fill(spec.value);
}

async function execute(command) {
  const evidence = {};
  let proxy;
  let browser;
  let control;
  let interrupted = null;
  try {
    proxy = await createPinnedProxy(command, evidence);
    browser = await chromium.launch({
      headless: true,
      proxy: { server: proxy.url },
      env: { HOME: process.env.HOME || "/tmp" },
    });
    control = await monitorControl(command.id, async (value) => {
      interrupted = value;
      if (browser) await browser.close().catch(() => {});
      if (proxy) proxy.destroy();
    });

    const context = await browser.newContext({
      acceptDownloads: false,
      ignoreHTTPSErrors: false,
      serviceWorkers: "block",
    });
    const page = await context.newPage();
    page.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT_MS);
    page.setDefaultTimeout(NAVIGATION_TIMEOUT_MS);

    let preparingForm = false;
    let formMutationBlocked = false;
    await page.route("**/*", async (route) => {
      const request = route.request();
      const method = request.method().toUpperCase();
      if (!["GET", "HEAD"].includes(method)) {
        formMutationBlocked = formMutationBlocked || command.kind === "prepare_form";
        await route.abort("blockedbyclient");
        return;
      }
      if (preparingForm && request.isNavigationRequest() && request.frame() === page.mainFrame()) {
        formMutationBlocked = true;
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });

    const navigationUrls = [];
    page.on("request", (request) => {
      if (request.isNavigationRequest() && request.frame() === page.mainFrame()) {
        navigationUrls.push(request.url());
      }
    });
    page.on("download", (download) => {
      void download.cancel().catch(() => {});
    });

    await page.goto(command.target_url, { waitUntil: "domcontentloaded" });
    const preparedFields = [];
    if (command.kind === "prepare_form") {
      if (command.policy?.allow_form_submission !== false || !Array.isArray(command.policy?.fields)) {
        throw Object.assign(new Error("form_mutation_blocked"), { code: "form_mutation_blocked" });
      }
      preparingForm = true;
      for (const field of command.policy.fields) {
        await fillPreparedField(page, field);
        preparedFields.push(field.field);
        if (formMutationBlocked) {
          throw Object.assign(new Error("form_mutation_blocked"), { code: "form_mutation_blocked" });
        }
      }
      preparingForm = false;
    } else if (command.kind !== "navigate") {
      throw Object.assign(new Error("unsupported_site"), { code: "unsupported_site" });
    }
    if (interrupted) {
      throw Object.assign(new Error(interrupted.reason || "worker_interrupted"), {
        code: interrupted.reason || "worker_interrupted",
      });
    }
    const finalUrl = page.url();
    const title = (await page.title()).slice(0, 300);
    const redirectChain = navigationUrls
      .filter((url, index, values) => url !== finalUrl && values.indexOf(url) === index)
      .slice(0, 10);

    await api(`/api/v1/internal/browser-worker/commands/${command.id}/complete`, {
      worker_id: WORKER_ID,
      final_url: finalUrl,
      title,
      redirect_chain: redirectChain,
      resolved_ips: evidence,
      prepared_fields: preparedFields,
      submission_performed: false,
    });
  } catch (error) {
    const passThrough = new Set([
      "sensitive_field_requires_takeover",
      "form_field_not_found",
      "form_field_ambiguous",
      "form_field_not_editable",
      "form_mutation_blocked",
      "unsupported_site",
    ]);
    const code = ["browser_origin_not_allowed", "browser_network_blocked", "browser_dns_unresolved", "browser_dns_invalid"]
      .includes(error?.code) ? "network_blocked"
      : ["browser_worker_claim_invalid", "session_cancelled", "takeover_requested", "session_expired", "claim_lost"]
          .includes(error?.code) ? "worker_interrupted"
      : passThrough.has(error?.code) ? error.code
      : "navigation_failed";
    try {
      await api(`/api/v1/internal/browser-worker/commands/${command.id}/fail`, {
        worker_id: WORKER_ID,
        error_code: code,
      });
    } catch {}
  } finally {
    if (control) await control.finish().catch(() => {});
    if (browser) await browser.close().catch(() => {});
    if (proxy) {
      proxy.destroy();
      await new Promise((resolve) => proxy.server.close(resolve));
    }
  }
}

async function pollOnce() {
  const value = await api("/api/v1/internal/browser-worker/claim", {
    worker_id: WORKER_ID,
    limit: 1,
  });
  const command = value.commands?.[0];
  if (command) await execute(command);
}

while (!stopping) {
  try {
    await pollOnce();
  } catch (error) {
    if (error?.status === 403) {
      process.stderr.write("Browser worker authentication or policy check failed; refusing to continue.\n");
      process.exitCode = 1;
      break;
    }
  }
  if (!stopping) await new Promise((resolve) => setTimeout(resolve, POLL_MS));
}
