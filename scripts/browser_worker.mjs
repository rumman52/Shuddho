import http from "node:http";
import net from "node:net";
import { createHash } from "node:crypto";
import dns from "node:dns/promises";
import os from "node:os";
import { chromium } from "playwright";
import { browserContextOptions, browserRequestAllowed, formFieldPolicy, normalizedBaseUrl, parseConnectAuthority, safeWorkerId, takeoverFieldPolicy } from "./browser_worker_policy.mjs";

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
const liveTakeovers = new Map();
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

async function createPinnedProxy(state) {
  const sockets = new Set();
  const server = http.createServer((_req, res) => {
    res.writeHead(403, { "Content-Type": "text/plain", "Connection": "close" });
    res.end("HTTPS CONNECT only");
  });

  server.on("connect", async (req, clientSocket, head) => {
    let target;
    try {
      if (!state.commandId || !state.evidence) throw new Error("browser_command_not_active");
      target = parseConnectAuthority(req.url || "");
      const checked = await validateHost(state.commandId, target.host);
      state.evidence[checked.hostname] = checked.resolved_ips;
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
  function closeSockets() {
    for (const socket of sockets) socket.destroy();
    sockets.clear();
  }
  return {
    server,
    url: `http://127.0.0.1:${address.port}`,
    setCommand(commandId, evidence) {
      state.commandId = commandId;
      state.evidence = evidence;
    },
    pause() {
      state.commandId = null;
      state.evidence = null;
      closeSockets();
    },
    destroy() {
      state.commandId = null;
      state.evidence = null;
      closeSockets();
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

async function fillTakeoverField(page, spec) {
  const locator = await resolveFormField(page, spec);
  const metadata = await locator.evaluate((element) => ({
    tag: element.tagName.toLowerCase(),
    type: (element.getAttribute("type") || "text").toLowerCase(),
    autocomplete: (element.getAttribute("autocomplete") || "").toLowerCase(),
    disabled: Boolean(element.disabled),
    readOnly: Boolean(element.readOnly),
  }));
  if (takeoverFieldPolicy(metadata) !== "fillable") {
    throw Object.assign(new Error("form_field_not_editable"), { code: "form_field_not_editable" });
  }
  await locator.fill(spec.value);
  if (spec.submit) {
    await locator.press("Enter");
  }
}

async function captureTakeoverFrame(page) {
  const frame = await page.screenshot({
    type: "jpeg",
    quality: 55,
    fullPage: false,
    animations: "disabled",
    caret: "hide",
  });
  if (!frame?.length || frame.length > 350000) {
    throw Object.assign(new Error("takeover_frame_too_large"), { code: "takeover_frame_too_large" });
  }
  return frame;
}

function frameSha256(frame) {
  return createHash("sha256").update(frame).digest("hex");
}

async function performTakeoverInteraction(page, policy, armInteraction) {
  if (policy?.human_only !== true || !policy?.interaction || typeof policy?.expected_frame_sha256 !== "string") {
    throw Object.assign(new Error("takeover_context_missing"), { code: "takeover_context_missing" });
  }
  const before = await captureTakeoverFrame(page);
  if (frameSha256(before) !== policy.expected_frame_sha256) {
    throw Object.assign(new Error("takeover_frame_stale"), { code: "takeover_frame_stale" });
  }
  const interaction = policy.interaction;
  armInteraction();
  if (interaction.kind === "click") {
    const viewport = page.viewportSize();
    if (
      !viewport
      || !Number.isFinite(interaction.x)
      || !Number.isFinite(interaction.y)
      || interaction.x < 0 || interaction.x > 1
      || interaction.y < 0 || interaction.y > 1
    ) {
      throw Object.assign(new Error("takeover_interaction_failed"), { code: "takeover_interaction_failed" });
    }
    await page.mouse.click(
      Math.max(0, Math.min(viewport.width - 1, interaction.x * viewport.width)),
      Math.max(0, Math.min(viewport.height - 1, interaction.y * viewport.height)),
    );
  } else if (interaction.kind === "key") {
    const allowedKeys = new Set(["Tab", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);
    if (!allowedKeys.has(interaction.key)) {
      throw Object.assign(new Error("takeover_interaction_failed"), { code: "takeover_interaction_failed" });
    }
    await page.keyboard.press(interaction.key);
  } else {
    throw Object.assign(new Error("takeover_interaction_failed"), { code: "takeover_interaction_failed" });
  }
  await page.waitForTimeout(250);
  await page.waitForLoadState("domcontentloaded", { timeout: 1500 }).catch(() => {});
  try {
    return await captureTakeoverFrame(page);
  } catch {
    throw Object.assign(new Error("takeover_interaction_uncertain"), { code: "takeover_interaction_uncertain" });
  }
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
  const policy = formFieldPolicy(metadata);
  if (policy === "not_editable") {
    throw Object.assign(new Error("form_field_not_editable"), { code: "form_field_not_editable" });
  }
  if (policy === "sensitive") {
    throw Object.assign(new Error("sensitive_field_requires_takeover"), { code: "sensitive_field_requires_takeover" });
  }
  await locator.fill(spec.value);
}

async function createRuntime(command, evidence) {
  const state = {
    commandId: command.id,
    evidence,
    kind: command.kind,
    preparingForm: false,
    humanInteractionArmed: false,
    formMutationBlocked: false,
    navigationUrls: [],
  };
  const proxy = await createPinnedProxy(state);
  const browser = await chromium.launch({
    headless: true,
    proxy: { server: proxy.url },
    env: { HOME: process.env.HOME || "/tmp" },
  });
  const context = await browser.newContext(browserContextOptions(command.storage_state));
  const page = await context.newPage();
  page.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT_MS);
  page.setDefaultTimeout(NAVIGATION_TIMEOUT_MS);

  await page.route("**/*", async (route) => {
    const request = route.request();
    const allowed = browserRequestAllowed({
      kind: state.kind,
      method: request.method(),
      preparingForm: state.preparingForm,
      humanInteractionArmed: state.humanInteractionArmed,
      navigationRequest: request.isNavigationRequest(),
      mainFrame: request.frame() === page.mainFrame(),
    });
    if (!allowed) {
      state.formMutationBlocked = state.formMutationBlocked || state.kind === "prepare_form";
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  page.on("request", (request) => {
    if (request.isNavigationRequest() && request.frame() === page.mainFrame()) {
      state.navigationUrls.push(request.url());
    }
  });
  page.on("download", (download) => {
    void download.cancel().catch(() => {});
  });

  return { state, proxy, browser, context, page, sessionId: command.session_id };
}

function activateRuntime(runtime, command, evidence) {
  runtime.state.commandId = command.id;
  runtime.state.evidence = evidence;
  runtime.state.kind = command.kind;
  runtime.state.preparingForm = false;
  runtime.state.humanInteractionArmed = false;
  runtime.state.formMutationBlocked = false;
  runtime.state.navigationUrls = [];
  runtime.proxy.setCommand(command.id, evidence);
}

function pauseRuntime(runtime) {
  runtime.state.kind = "idle";
  runtime.state.preparingForm = false;
  runtime.state.humanInteractionArmed = false;
  runtime.state.navigationUrls = [];
  runtime.proxy.pause();
}

async function closeRuntime(runtime) {
  if (!runtime) return;
  runtime.proxy.destroy();
  await runtime.browser.close().catch(() => {});
  await new Promise((resolve) => runtime.proxy.server.close(() => resolve())).catch(() => {});
}

async function releaseLiveTakeover(sessionId) {
  const runtime = liveTakeovers.get(sessionId);
  if (!runtime) return;
  liveTakeovers.delete(sessionId);
  await closeRuntime(runtime);
}

async function heartbeatLiveTakeovers() {
  const sessionIds = [...liveTakeovers.keys()];
  if (!sessionIds.length) return;
  const response = await api("/api/v1/internal/browser-worker/takeover-heartbeat", {
    worker_id: WORKER_ID,
    session_ids: sessionIds,
  });
  for (const sessionId of response.release_session_ids || []) {
    await releaseLiveTakeover(sessionId);
  }
}

async function revalidateCurrentPage(command, runtime, evidence) {
  let parsed;
  try {
    parsed = new URL(runtime.page.url());
  } catch {
    throw Object.assign(new Error("takeover_context_missing"), { code: "takeover_context_missing" });
  }
  if (parsed.protocol !== "https:" || !parsed.hostname) {
    throw Object.assign(new Error("takeover_context_missing"), { code: "takeover_context_missing" });
  }
  const checked = await validateHost(command.id, parsed.hostname);
  evidence[checked.hostname] = checked.resolved_ips;
}

function workerFailureCode(error) {
  const passThrough = new Set([
    "sensitive_field_requires_takeover",
    "form_field_not_found",
    "form_field_ambiguous",
    "form_field_not_editable",
    "form_mutation_blocked",
    "takeover_frame_too_large",
    "takeover_frame_capture_failed",
    "takeover_frame_stale",
    "takeover_context_missing",
    "takeover_interaction_failed",
    "takeover_interaction_uncertain",
    "unsupported_site",
  ]);
  if (["browser_origin_not_allowed", "browser_network_blocked", "browser_dns_unresolved", "browser_dns_invalid"].includes(error?.code)) {
    return "network_blocked";
  }
  if (["browser_worker_claim_invalid", "session_cancelled", "takeover_requested", "session_expired", "claim_lost"].includes(error?.code)) {
    return "worker_interrupted";
  }
  return passThrough.has(error?.code) ? error.code : "navigation_failed";
}

async function execute(command) {
  const evidence = {};
  const affinityKind = command.kind === "takeover_frame" || command.kind === "takeover_interaction";
  let runtime = affinityKind ? liveTakeovers.get(command.session_id) : null;
  let createdRuntime = false;
  let control;
  let interrupted = null;
  let completed = false;
  let retainAfterFailure = false;

  try {
    if (command.kind === "takeover_interaction" && !runtime) {
      throw Object.assign(new Error("takeover_context_missing"), { code: "takeover_context_missing" });
    }
    if (command.kind === "takeover_frame" && command.policy?.require_live_context === true && !runtime) {
      throw Object.assign(new Error("takeover_context_missing"), { code: "takeover_context_missing" });
    }

    if (!runtime) {
      runtime = await createRuntime(command, evidence);
      createdRuntime = true;
    } else {
      activateRuntime(runtime, command, evidence);
    }

    control = await monitorControl(command.id, async (value) => {
      interrupted = value;
      if (affinityKind) {
        await releaseLiveTakeover(command.session_id);
      } else {
        await closeRuntime(runtime);
      }
    });

    if (createdRuntime) {
      await runtime.page.goto(command.target_url, { waitUntil: "domcontentloaded" });
    } else {
      await revalidateCurrentPage(command, runtime, evidence);
    }

    const preparedFields = [];
    let takeoverFrameB64 = null;
    if (command.kind === "prepare_form") {
      if (command.policy?.allow_form_submission !== false || !Array.isArray(command.policy?.fields)) {
        throw Object.assign(new Error("form_mutation_blocked"), { code: "form_mutation_blocked" });
      }
      runtime.state.preparingForm = true;
      for (const field of command.policy.fields) {
        await fillPreparedField(runtime.page, field);
        preparedFields.push(field.field);
        if (runtime.state.formMutationBlocked) {
          throw Object.assign(new Error("form_mutation_blocked"), { code: "form_mutation_blocked" });
        }
      }
      runtime.state.preparingForm = false;
    } else if (command.kind === "takeover_input") {
      if (!command.takeover_input || typeof command.takeover_input.value !== "string") {
        throw Object.assign(new Error("sensitive_field_requires_takeover"), { code: "sensitive_field_requires_takeover" });
      }
      await fillTakeoverField(runtime.page, command.takeover_input);
      preparedFields.push(command.takeover_input.field);
      if (command.takeover_input.submit) {
        await runtime.page.waitForLoadState("domcontentloaded").catch(() => {});
      }
    } else if (command.kind === "takeover_frame") {
      try {
        takeoverFrameB64 = (await captureTakeoverFrame(runtime.page)).toString("base64");
      } catch (error) {
        if (error?.code === "takeover_frame_too_large") throw error;
        throw Object.assign(new Error("takeover_frame_capture_failed"), { code: "takeover_frame_capture_failed" });
      }
    } else if (command.kind === "takeover_interaction") {
      try {
        takeoverFrameB64 = (await performTakeoverInteraction(
          runtime.page,
          command.policy,
          () => { runtime.state.humanInteractionArmed = true; },
        )).toString("base64");
      } catch (error) {
        if (["takeover_frame_too_large", "takeover_frame_stale", "takeover_context_missing", "takeover_interaction_failed"].includes(error?.code)) {
          throw error;
        }
        throw Object.assign(new Error("takeover_interaction_uncertain"), { code: "takeover_interaction_uncertain" });
      }
    } else if (command.kind !== "navigate") {
      throw Object.assign(new Error("unsupported_site"), { code: "unsupported_site" });
    }

    if (interrupted) {
      throw Object.assign(new Error(interrupted.reason || "worker_interrupted"), {
        code: interrupted.reason || "worker_interrupted",
      });
    }

    const finalUrl = runtime.page.url();
    const title = (await runtime.page.title()).slice(0, 300);
    const redirectChain = runtime.state.navigationUrls
      .filter((url, index, values) => url !== finalUrl && values.indexOf(url) === index)
      .slice(0, 10);
    const storageState = await runtime.context.storageState();

    await api(`/api/v1/internal/browser-worker/commands/${command.id}/complete`, {
      worker_id: WORKER_ID,
      final_url: finalUrl,
      title,
      redirect_chain: redirectChain,
      resolved_ips: evidence,
      prepared_fields: preparedFields,
      submission_performed: command.kind === "takeover_input" ? Boolean(command.takeover_input?.submit) : false,
      storage_state: storageState,
      takeover_frame_b64: takeoverFrameB64,
      takeover_frame_content_type: takeoverFrameB64 ? "image/jpeg" : null,
      interaction_performed: command.kind === "takeover_interaction",
    });
    completed = true;

    if (affinityKind) {
      liveTakeovers.set(command.session_id, runtime);
      pauseRuntime(runtime);
    }
  } catch (error) {
    retainAfterFailure = affinityKind && runtime && ["takeover_frame_stale", "takeover_interaction_failed"].includes(error?.code);
    const code = workerFailureCode(error);
    try {
      await api(`/api/v1/internal/browser-worker/commands/${command.id}/fail`, {
        worker_id: WORKER_ID,
        error_code: code,
      });
    } catch {}
    if (retainAfterFailure && runtime) {
      liveTakeovers.set(command.session_id, runtime);
      pauseRuntime(runtime);
    } else if (affinityKind && liveTakeovers.get(command.session_id) === runtime) {
      await releaseLiveTakeover(command.session_id);
    }
  } finally {
    if (control) await control.finish().catch(() => {});
    if (!affinityKind && runtime) {
      await closeRuntime(runtime);
    } else if (affinityKind && runtime && !completed && !retainAfterFailure && liveTakeovers.get(command.session_id) !== runtime) {
      await closeRuntime(runtime);
    }
  }
}

async function pollOnce() {
  await heartbeatLiveTakeovers();
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

for (const sessionId of [...liveTakeovers.keys()]) {
  await releaseLiveTakeover(sessionId);
}
