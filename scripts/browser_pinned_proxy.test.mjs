import test from "node:test";
import assert from "node:assert/strict";
import net from "node:net";
import { once } from "node:events";
import { createPinnedProxy } from "./browser_pinned_proxy.mjs";

const CHECKED = { hostname: "example.com", resolved_ips: ["93.184.216.34"] };

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function activeState() {
  return { commandId: "owned-command", proxyClaimEpoch: 0, evidence: {} };
}

async function openConnect(proxy) {
  const port = Number(new URL(proxy.url).port);
  const client = net.connect({ host: "127.0.0.1", port });
  client.on("error", () => {});
  // Drain rejected CONNECT responses so a TCP FIN reliably reaches "close".
  // Keep a bounded copy for the successful tunnel assertion so response bytes
  // cannot be lost between connect() and attaching that assertion.
  client.received = "";
  client.on("data", (chunk) => {
    client.received = (client.received + chunk.toString()).slice(-8192);
    client.emit("proxy-data", client.received);
  });
  await once(client, "connect");
  client.write("CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n");
  return client;
}

async function stopProxy(proxy, clients = []) {
  for (const client of clients) client.destroy();
  proxy.destroy();
  await new Promise((resolve) => proxy.server.close(resolve));
}

function closedWithin(socket, timeoutMs) {
  return new Promise((resolve) => {
    const onClose = () => { clearTimeout(timer); resolve(true); };
    const timer = setTimeout(() => {
      socket.off("close", onClose);
      resolve(false);
    }, timeoutMs);
    socket.once("close", onClose);
  });
}

// Exercise timer ordering after a busy event loop: expiry must be checked at
// the side-effect boundary, even if its timer callback has not run yet.
function elapseWithoutTimers(milliseconds) {
  const until = performance.now() + milliseconds;
  while (performance.now() < until) { /* Deliberately hold timer callbacks. */ }
}

test("real CONNECT rejects elapsed authorization before the timeout callback runs", { timeout: 3000 }, async () => {
  const started = deferred();
  const network = deferred();
  const state = activeState();
  let dials = 0;
  const proxy = await createPinnedProxy(state, {
    validateHost: async () => { started.resolve(); return network.promise; },
    dial: () => { dials += 1; throw new Error("authorization arrived after its deadline"); },
    navigationTimeoutMs: 40,
  });
  let client;
  try {
    client = await openConnect(proxy);
    await started.promise;
    elapseWithoutTimers(80);
    network.resolve(CHECKED);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(dials, 0, "elapsed authorization must not beat an overdue timer");
    assert.deepEqual(state.evidence, {});
  } finally {
    await stopProxy(proxy, client ? [client] : []);
    network.resolve(CHECKED);
  }
});

test("real CONNECT rejects elapsed TCP readiness before the timeout callback runs", { timeout: 3000 }, async () => {
  const dialing = deferred();
  let upstream;
  const proxy = await createPinnedProxy(activeState(), {
    validateHost: async () => CHECKED,
    dial: () => {
      upstream = new net.Socket();
      dialing.resolve();
      return upstream;
    },
    navigationTimeoutMs: 40,
  });
  let client;
  try {
    client = await openConnect(proxy);
    await dialing.promise;
    const closed = closedWithin(client, 600);
    elapseWithoutTimers(80);
    upstream.emit("connect"); // Readiness can precede its overdue timeout callback.
    assert.equal(upstream.destroyed, true, "late TCP readiness must not acknowledge CONNECT");
    assert.equal(await closed, true);
    assert.ok(!client.received.includes("200 Connection Established"));
  } finally {
    await stopProxy(proxy, client ? [client] : []);
  }
});

test("real CONNECT expires stalled authorization and rejects its late result", { timeout: 3000 }, async () => {
  const started = deferred();
  const network = deferred();
  const state = activeState();
  let dials = 0;
  const proxy = await createPinnedProxy(state, {
    validateHost: async () => { started.resolve(); return network.promise; },
    dial: () => { dials += 1; throw new Error("expired authorization must not dial"); },
    navigationTimeoutMs: 40,
  });
  let client;
  try {
    client = await openConnect(proxy);
    const closed = closedWithin(client, 600);
    await started.promise;
    assert.equal(await closed, true, "broker wait must have a CONNECT deadline");
    network.resolve(CHECKED);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(dials, 0, "expired authorization must not open a socket");
    assert.deepEqual(state.evidence, {});
    assert.ok(!client.received.includes("200 Connection Established"));
  } finally {
    await stopProxy(proxy, client ? [client] : []);
    network.resolve(CHECKED);
  }
});

test("real CONNECT shares one deadline across authorization and upstream handshake", { timeout: 3000 }, async () => {
  const started = deferred();
  const network = deferred();
  const dialing = deferred();
  let upstream;
  const proxy = await createPinnedProxy(activeState(), {
    validateHost: async () => { started.resolve(); return network.promise; },
    dial: ({ host, port }) => {
      assert.equal(host, "93.184.216.34");
      assert.equal(port, 443);
      upstream = new net.Socket(); // A TCP connect that has not completed.
      dialing.resolve();
      return upstream;
    },
    navigationTimeoutMs: 300,
  });
  let client;
  try {
    client = await openConnect(proxy);
    await started.promise;
    await new Promise((resolve) => setTimeout(resolve, 200));
    network.resolve(CHECKED);
    await dialing.promise;
    const closed = closedWithin(client, 200);
    assert.equal(await closed, true, "pre-connect wait must share the handshake deadline");
    assert.equal(upstream.destroyed, true);
    upstream.emit("connect"); // A late TCP event must not acknowledge the tunnel.
    assert.ok(!client.received.includes("200 Connection Established"));
  } finally {
    await stopProxy(proxy, client ? [client] : []);
    network.resolve(CHECKED);
  }
});

test("real CONNECT clears the handshake deadline for an active authorized tunnel", { timeout: 3000 }, async () => {
  const upstream = net.createServer((socket) => {
    socket.resume(); // Observe peer FIN while the server sends keepalives.
    const pulse = setInterval(() => socket.write("keepalive"), 10);
    socket.once("close", () => clearInterval(pulse));
    socket.on("error", () => {});
  });
  await new Promise((resolve) => upstream.listen(0, "127.0.0.1", resolve));
  const address = upstream.address();
  const proxy = await createPinnedProxy(activeState(), {
    validateHost: async () => CHECKED,
    dial: ({ host, port }) => {
      assert.equal(host, "93.184.216.34");
      assert.equal(port, 443);
      return net.connect({ host: "127.0.0.1", port: address.port });
    },
    navigationTimeoutMs: 100,
  });
  let client;
  try {
    client = await openConnect(proxy);
    await new Promise((resolve) => setTimeout(resolve, 240));
    assert.ok(client.received.includes("200 Connection Established"));
    assert.ok(client.received.includes("keepalive"));
    assert.equal(client.destroyed, false, "handshake timer must not close an active tunnel");
  } finally {
    await stopProxy(proxy, client ? [client] : []);
    await new Promise((resolve) => upstream.close(resolve));
  }
});

test("real CONNECT cannot dial after command is revoked during broker network check", { timeout: 4000 }, async () => {
  const started = deferred();
  const network = deferred();
  let outboundDials = 0;
  const state = activeState();
  const proxy = await createPinnedProxy(state, {
    validateHost: async (commandId, host) => {
      assert.equal(commandId, "owned-command");
      assert.equal(host, "example.com");
      started.resolve();
      return network.promise;
    },
    dial: () => { outboundDials += 1; throw new Error("stale dial"); },
    navigationTimeoutMs: 1000,
  });
  let client;
  try {
    client = await openConnect(proxy);
    const closed = new Promise((resolve) => client.once("close", resolve));
    await started.promise;
    proxy.pause();
    await closed; // Must close even before pending authorization resolves.
    network.resolve(CHECKED);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(outboundDials, 0, "late authorized DNS must not dial after pause");
    assert.equal(state.commandId, null);
  } finally {
    network.resolve(CHECKED);
    await stopProxy(proxy, client ? [client] : []);
  }
});

test("real CONNECT cannot reuse a prior permission after same command is resumed", { timeout: 4000 }, async () => {
  const started = deferred();
  const network = deferred();
  const state = activeState();
  let dials = 0;
  const proxy = await createPinnedProxy(state, {
    validateHost: async () => {
      started.resolve();
      return network.promise;
    },
    dial: () => { dials += 1; throw new Error("old generation dial"); },
    navigationTimeoutMs: 1000,
  });
  let client;
  try {
    client = await openConnect(proxy);
    const closed = new Promise((resolve) => client.once("close", resolve));
    await started.promise;
    proxy.pause();
    await closed;
    proxy.setCommand("owned-command", {});
    network.resolve(CHECKED);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(dials, 0, "ABA command id cannot reuse old network permission");
    assert.equal(state.commandId, "owned-command");
  } finally {
    network.resolve(CHECKED);
    await stopProxy(proxy, client ? [client] : []);
  }
});

test("real CONNECT will not dial if client disconnects during network check", { timeout: 4000 }, async () => {
  const started = deferred();
  const network = deferred();
  let dials = 0;
  const proxy = await createPinnedProxy(activeState(), {
    validateHost: async () => { started.resolve(); return network.promise; },
    dial: () => { dials += 1; throw new Error("disconnected client dial"); },
    navigationTimeoutMs: 1000,
  });
  let client;
  try {
    // Capture the server-side transport so this test explicitly observes
    // teardown even when the network-check promise suspends socket reads.
    let serverSocket;
    const connected = new Promise((resolve) => {
      proxy.server.once("connect", (_request, socket) => {
        serverSocket = socket;
        resolve();
      });
    });
    client = await openConnect(proxy);
    await connected;
    const closed = new Promise((resolve) => client.once("close", resolve));
    await started.promise;
    client.destroy();
    serverSocket.destroy(); // Observed transport teardown, no live claim.
    await closed;
    network.resolve(CHECKED);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(dials, 0);
  } finally {
    network.resolve(CHECKED);
    await stopProxy(proxy, client ? [client] : []);
  }
});

test("real CONNECT rejects a paused claim before upstream TCP acknowledgement", { timeout: 4000 }, async () => {
  const dialing = deferred();
  let upstream;
  let response = "";
  const proxy = await createPinnedProxy(activeState(), {
    validateHost: async () => CHECKED,
    dial: () => {
      upstream = new net.Socket(); // Controlled, unconnected TCP handshake
      dialing.resolve();
      return upstream;
    },
    navigationTimeoutMs: 1000,
  });
  let client;
  try {
    client = await openConnect(proxy);
    client.on("data", (chunk) => { response += chunk.toString(); });
    const closed = new Promise((resolve) => client.once("close", resolve));
    await dialing.promise;
    proxy.pause();
    upstream.emit("connect");
    await closed;
    assert.ok(!response.includes("200 Connection Established"), "revoked claim must not acknowledge CONNECT");
    assert.equal(upstream.destroyed, true);
  } finally {
    await stopProxy(proxy, client ? [client] : []);
  }
});

test("real CONNECT allows only an owned authorized HTTPS tunnel to pinned IP", { timeout: 4000 }, async () => {
  const upstream = net.createServer((socket) => {
    socket.on("data", (chunk) => { socket.write(chunk); });
  });
  await new Promise((resolve) => upstream.listen(0, "127.0.0.1", resolve));
  const address = upstream.address();
  assert.ok(address && typeof address !== "string");
  const state = activeState();
  let validated = 0;
  let dialed = 0;
  const proxy = await createPinnedProxy(state, {
    validateHost: async (commandId, hostname) => {
      assert.equal(commandId, "owned-command");
      assert.equal(hostname, "example.com");
      validated += 1;
      return CHECKED;
    },
    dial: ({ host, port }) => {
      assert.equal(host, "93.184.216.34");
      assert.equal(port, 443);
      dialed += 1;
      return net.connect({ host: "127.0.0.1", port: address.port });
    },
    navigationTimeoutMs: 1000,
  });
  let client;
  try {
    client = await openConnect(proxy);
    const established = new Promise((resolve) => {
      if (client.received.includes("200 Connection Established")) return resolve();
      client.on("proxy-data", function listener(body) {
        if (body.includes("200 Connection Established")) {
          client.off("proxy-data", listener);
          resolve();
        }
      });
    });
    await established;
    assert.equal(dialed, 1);
    assert.equal(validated, 1);
    assert.deepEqual(state.evidence["example.com"], CHECKED.resolved_ips);
    // No outbound connection is allowed until broker verification succeeds.
  } finally {
    await stopProxy(proxy, client ? [client] : []);
    await new Promise((resolve) => upstream.close(resolve));
  }
});


test("real CONNECT fails closed on malformed or mismatched broker DNS results", { timeout: 6000 }, async () => {
  const cases = [
    ["missing result", null],
    ["wrong hostname", { hostname: "other.example", resolved_ips: ["93.184.216.34"] }],
    ["empty resolved address list", { hostname: "example.com", resolved_ips: [] }],
    ["non-array address list", { hostname: "example.com", resolved_ips: "93.184.216.34" }],
    ["invalid IP literal", { hostname: "example.com", resolved_ips: ["localhost"] }],
    ["too many resolved addresses", { hostname: "example.com", resolved_ips: Array(17).fill("93.184.216.34") }],
  ];

  for (const [label, checked] of cases) {
    const state = activeState();
    let outboundDials = 0;
    const proxy = await createPinnedProxy(state, {
      validateHost: async () => checked,
      dial: () => {
        outboundDials += 1;
        throw new Error("malformed network-check result must not dial");
      },
      navigationTimeoutMs: 1000,
    });
    let client;
    try {
      client = await openConnect(proxy);
      const closed = new Promise((resolve) => client.once("close", resolve));
      if (!client.destroyed) await closed;
      assert.equal(outboundDials, 0, label);
      assert.ok(!client.received.includes("200 Connection Established"), label);
      assert.deepEqual(state.evidence, {}, label);
    } finally {
      await stopProxy(proxy, client ? [client] : []);
    }
  }
});
