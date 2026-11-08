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
      assert.equal(host, "93.184.216.34", "only the approved public fixture IP may be dialed");
      assert.equal(port, 443);
      stats.dials += 1;
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
  const stats = { dials: 0 };
  const checkedHosts = [];
  let browser;
  let proxy;
  try {
    const created = await makeProxy(fixture, async (_commandId, host) => {
      checkedHosts.push(host);
      return host === "example.test"
        ? { hostname: host, resolved_ips: ["93.184.216.34"] }
        : { hostname: host, resolved_ips: ["127.0.0.1"] };
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
    assert.deepEqual(checkedHosts, ["example.test", "localhost"]);
    assert.equal(stats.dials, 1, "the private redirect must be rejected before a second TCP dial");
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
  const stats = { dials: 0 };
  let resolutionCount = 0;
  let browser;
  let proxy;
  try {
    const created = await makeProxy(fixture, async (_commandId, host) => {
      assert.equal(host, "rebind.test");
      resolutionCount += 1;
      return {
        hostname: host,
        resolved_ips: resolutionCount === 1
          ? ["93.184.216.34"]
          : ["127.0.0.1"],
      };
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
    assert.equal(resolutionCount, 1);
    assert.equal(stats.dials, 1);
    await context.close();
    await browser.close();
    browser = null;

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
    assert.equal(resolutionCount, 2);
    assert.equal(stats.dials, 1, "the rebound private answer must not open another TCP connection");
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
