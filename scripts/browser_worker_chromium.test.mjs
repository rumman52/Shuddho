import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import https from "node:https";
import net from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";

import { createPinnedProxy } from "./browser_pinned_proxy.mjs";
import {
  browserChromiumLaunchOptions,
  browserContextOptions,
  installAgentReadOnlyBrowserGuards,
  installBrowserRequestFence,
} from "./browser_worker_policy.mjs";

async function createTlsFixture(handler) {
  const directory = await mkdtemp(join(tmpdir(), "rukh-browser-qualification-"));
  const keyPath = join(directory, "key.pem");
  const certPath = join(directory, "cert.pem");
  execFileSync("openssl", [
    "req", "-x509", "-newkey", "rsa:2048", "-nodes",
    "-keyout", keyPath, "-out", certPath, "-days", "1",
    "-subj", "/CN=example.test",
    "-addext", "subjectAltName=DNS:example.test,DNS:rebind.test",
  ], { stdio: "ignore" });
  const server = https.createServer({
    key: await readFile(keyPath),
    cert: await readFile(certPath),
  }, handler);
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return { directory, server, port: server.address().port };
}

async function closeTlsFixture(fixture) {
  if (!fixture) return;
  await new Promise((resolve) => fixture.server.close(resolve)).catch(() => {});
  await rm(fixture.directory, { recursive: true, force: true });
}

async function closeProxy(proxy) {
  if (!proxy) return;
  proxy.destroy();
  await new Promise((resolve) => proxy.server.close(resolve)).catch(() => {});
}

function makeProxy(fixture, validateHost, stats) {
  const state = {
    commandId: "chromium-qualification-command",
    proxyClaimEpoch: 0,
    evidence: {},
  };
  return createPinnedProxy(state, {
    validateHost,
    dial: ({ host, port }) => {
      // Record before assertions: createPinnedProxy intentionally catches
      // dial failures, so a private-IP dial attempt must remain observable.
      stats.dials += 1;
      stats.targets ||= [];
      stats.targets.push({ host, port });
      assert.equal(host, "93.184.216.34", "only the approved public fixture IP may be dialed");
      assert.equal(port, 443);
      // The test-only dialer maps the synthetic public IP to a local TLS
      // fixture. Production always uses the actual broker-approved IP.
      return net.connect({ host: "127.0.0.1", port: fixture.port });
    },
    navigationTimeoutMs: 5000,
  }).then((proxy) => ({ proxy, state }));
}

test("real Chromium sends loopback redirects through the pinned proxy and blocks them", {
  timeout: 30000,
}, async () => {
  const fixture = await createTlsFixture((_request, response) => {
    response.writeHead(302, {
      Location: "https://localhost/private",
      Connection: "close",
    });
    response.end("redirecting to a private destination");
  });
  const stats = { dials: 0, targets: [] };
  const checkedHosts = [];
  let privateCheckDialCount = null;
  let browser;
  let proxy;
  try {
    const created = await makeProxy(fixture, async (_commandId, host) => {
      checkedHosts.push(host);
      if (host === "example.test") {
        return { hostname: host, resolved_ips: ["93.184.216.34"] };
      }
      if (host === "localhost") {
        privateCheckDialCount = stats.dials;
        return { hostname: host, resolved_ips: ["127.0.0.1"] };
      }
      throw new Error(`unexpected CONNECT hostname: ${host}`);
    }, stats);
    proxy = created.proxy;
    browser = await chromium.launch(browserChromiumLaunchOptions(proxy.url));
    const context = await browser.newContext({
      ...browserContextOptions(null),
      // Only the local self-signed fixture is exempted from certificate
      // validation. Production browser contexts keep ignoreHTTPSErrors=false.
      ignoreHTTPSErrors: true,
    });
    const page = await context.newPage();
    await assert.rejects(
      page.goto("https://example.test/redirect", { waitUntil: "domcontentloaded", timeout: 8000 }),
    );
    assert.ok(checkedHosts.includes("example.test"));
    assert.ok(checkedHosts.includes("localhost"));
    assert.ok(checkedHosts.every((host) => ["example.test", "localhost"].includes(host)));
    assert.equal(privateCheckDialCount, stats.dials, "the private redirect must be rejected before a TCP dial");
    assert.ok(stats.targets.length >= 1);
    assert.ok(stats.targets.every((target) => target.host === "93.184.216.34" && target.port === 443));
    assert.deepEqual(created.state.evidence, {
      "example.test": ["93.184.216.34"],
    });
    await context.close();
  } finally {
    if (browser) await browser.close().catch(() => {});
    await closeProxy(proxy);
    await closeTlsFixture(fixture);
  }
});

test("real Chromium revalidates a hostname after a public-to-private DNS answer change", {
  timeout: 30000,
}, async () => {
  const fixture = await createTlsFixture((_request, response) => {
    response.writeHead(200, { "Content-Type": "text/plain", Connection: "close" });
    response.end("public fixture response");
  });
  const stats = { dials: 0, targets: [] };
  let firstBrowserProcess = true;
  let firstProcessResolutions = 0;
  let secondProcessResolutions = 0;
  let dialsBeforePrivateResolution = null;
  let browser;
  let proxy;
  try {
    const created = await makeProxy(fixture, async (_commandId, host) => {
      assert.equal(host, "rebind.test");
      if (firstBrowserProcess) {
        firstProcessResolutions += 1;
        return { hostname: host, resolved_ips: ["93.184.216.34"] };
      }
      secondProcessResolutions += 1;
      dialsBeforePrivateResolution ??= stats.dials;
      return { hostname: host, resolved_ips: ["127.0.0.1"] };
    }, stats);
    proxy = created.proxy;

    browser = await chromium.launch(browserChromiumLaunchOptions(proxy.url));
    let context = await browser.newContext({
      ...browserContextOptions(null),
      ignoreHTTPSErrors: true,
    });
    let page = await context.newPage();
    const first = await page.goto("https://rebind.test/first", {
      waitUntil: "domcontentloaded",
      timeout: 8000,
    });
    assert.equal(first.status(), 200);
    assert.ok(firstProcessResolutions >= 1);
    const dialsBeforeRebind = stats.dials;
    assert.ok(dialsBeforeRebind >= 1);
    await context.close();
    await browser.close();
    browser = null;
    firstBrowserProcess = false;

    // A fresh Chromium process forces a new CONNECT and therefore a fresh
    // broker DNS decision for the same hostname.
    browser = await chromium.launch(browserChromiumLaunchOptions(proxy.url));
    context = await browser.newContext({
      ...browserContextOptions(null),
      ignoreHTTPSErrors: true,
    });
    page = await context.newPage();
    await assert.rejects(
      page.goto("https://rebind.test/second", { waitUntil: "domcontentloaded", timeout: 8000 }),
    );
    assert.ok(secondProcessResolutions >= 1);
    assert.equal(dialsBeforePrivateResolution, dialsBeforeRebind);
    assert.equal(stats.dials, dialsBeforeRebind, "the rebound private answer must not open another TCP connection");
    assert.ok(stats.targets.every((target) => target.host === "93.184.216.34" && target.port === 443));
    assert.deepEqual(created.state.evidence, {
      "rebind.test": ["93.184.216.34"],
    });
    await context.close();
  } finally {
    if (browser) await browser.close().catch(() => {});
    await closeProxy(proxy);
    await closeTlsFixture(fixture);
  }
});


test("real Chromium Agent read-only context blocks WebSockets and realtime transports", {
  timeout: 30000,
}, async () => {
  const receivedRequests = [];
  const fixture = await createTlsFixture((request, response) => {
    receivedRequests.push({ method: request.method, url: request.url });
    response.writeHead(200, { "Content-Type": "text/html", Connection: "close" });
    response.end("<!doctype html><title>read-only fixture</title>");
  });
  const stats = { dials: 0, targets: [] };
  const state = {
    surfaceViolation: null,
    kind: "agent_read_only",
    agentReadOnly: true,
    allowedOrigin: "https://example.test",
    preparingForm: false,
    humanInteractionArmed: false,
    formMutationBlocked: false,
  };
  let browser;
  let proxy;
  try {
    const created = await makeProxy(fixture, async (_commandId, host) => {
      assert.equal(host, "example.test");
      return { hostname: host, resolved_ips: ["93.184.216.34"] };
    }, stats);
    proxy = created.proxy;
    browser = await chromium.launch(browserChromiumLaunchOptions(proxy.url));
    const context = await browser.newContext({
      ...browserContextOptions(null),
      ignoreHTTPSErrors: true,
    });
    await installAgentReadOnlyBrowserGuards(context, state);
    const page = await context.newPage();
    await installBrowserRequestFence(context, page, state);
    await page.goto("https://example.test/", {
      waitUntil: "domcontentloaded",
      timeout: 8000,
    });
    const workerMutation = await page.evaluate(() => new Promise((resolve) => {
      const workerSource = `self.onmessage = async () => {
        try {
          await fetch("https://example.test/mutate", {
            method: "POST",
            body: "must-not-reach-server",
          });
          self.postMessage("sent");
        } catch {
          self.postMessage("blocked");
        }
      };`;
      const workerUrl = URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" }));
      const worker = new Worker(workerUrl);
      const timeout = setTimeout(() => {
        worker.terminate();
        URL.revokeObjectURL(workerUrl);
        resolve("timeout");
      }, 3000);
      worker.addEventListener("message", (event) => {
        clearTimeout(timeout);
        worker.terminate();
        URL.revokeObjectURL(workerUrl);
        resolve(event.data);
      }, { once: true });
      worker.postMessage("start");
    }));
    assert.equal(workerMutation, "blocked");
    assert.equal(receivedRequests.some((request) => request.method === "POST"), false);

    const dialsBeforeWebSocket = stats.dials;
    const targetsBeforeWebSocket = stats.targets.length;
    const transportApis = await page.evaluate(() => ({
      rtc: typeof globalThis.RTCPeerConnection,
      webkitRtc: typeof globalThis.webkitRTCPeerConnection,
      webTransport: typeof globalThis.WebTransport,
    }));
    const webSocketOutcome = await page.evaluate(() => new Promise((resolve) => {
      const socket = new WebSocket("wss://example.test/socket");
      const timeout = setTimeout(() => resolve("timeout"), 2000);
      for (const eventName of ["open", "error", "close"]) {
        socket.addEventListener(eventName, () => {
          clearTimeout(timeout);
          resolve(eventName);
        }, { once: true });
      }
    }));
    assert.deepEqual(transportApis, {
      rtc: "undefined",
      webkitRtc: "undefined",
      webTransport: "undefined",
    });
    assert.notEqual(webSocketOutcome, "open");
    assert.equal(state.surfaceViolation, "browser_websocket_blocked");
    assert.equal(stats.dials, dialsBeforeWebSocket, "the WebSocket must not create a new proxied TCP connection");
    assert.equal(stats.targets.length, targetsBeforeWebSocket);
    assert.ok(stats.targets.every((target) => target.host === "93.184.216.34" && target.port === 443));
    await context.close();
  } finally {
    if (browser) await browser.close().catch(() => {});
    await closeProxy(proxy);
    await closeTlsFixture(fixture);
  }
});
