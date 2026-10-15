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
  await once(client, "connect");
  client.write("CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n");
  return client;
}

async function stopProxy(proxy, clients = []) {
  for (const client of clients) client.destroy();
  proxy.destroy();
  await new Promise((resolve) => proxy.server.close(resolve));
}

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
    const closed = once(client, "close");
    await started.promise;
    proxy.pause();
    network.resolve(CHECKED);
    await closed;
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
    const closed = once(client, "close");
    await started.promise;
    proxy.pause();
    proxy.setCommand("owned-command", {});
    network.resolve(CHECKED);
    await closed;
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
    client = await openConnect(proxy);
    const closed = once(client, "close");
    await started.promise;
    client.destroy();
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
    const closed = once(client, "close");
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
    let output = "";
    const established = new Promise((resolve) => {
      client.on("data", function listener(chunk) {
        output += chunk.toString();
        if (output.includes("200 Connection Established")) {
          client.off("data", listener);
          resolve();
        }
      });
    });
    await established;
    assert.equal(dialed, 1);
    assert.equal(validated, 1);
    assert.deepEqual(state.evidence.example.com, CHECKED.resolved_ips);
    // No outbound connection is allowed until broker verification succeeds.
  } finally {
    await stopProxy(proxy, client ? [client] : []);
    await new Promise((resolve) => upstream.close(resolve));
  }
});
