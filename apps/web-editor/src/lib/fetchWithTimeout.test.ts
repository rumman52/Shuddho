import assert from "node:assert/strict";
import test from "node:test";
import { createServer, type RequestListener } from "node:http";
import { once } from "node:events";
import type { AddressInfo } from "node:net";
import { fetchWithTimeout, FetchTimeoutError } from "./fetchWithTimeout";

async function withServer(handler: RequestListener, run: (url: string) => Promise<void>) {
  const server = createServer(handler);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address() as AddressInfo;
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
}

test("deadline continues after headers even while body bytes arrive", async () => {
  let headersSent = false;
  await withServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/json" });
    response.flushHeaders();
    headersSent = true;
    const timer = setInterval(() => response.write(" "), 5);
    response.on("close", () => clearInterval(timer));
  }, async (url) => {
    await assert.rejects(() => fetchWithTimeout(url, {}, 100), FetchTimeoutError);
    assert.equal(headersSent, true);
  });
});

test("upstream cancellation remains connected while reading the body", async () => {
  const controller = new AbortController();
  await withServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/json" });
    response.flushHeaders();
    const timer = setTimeout(() => controller.abort(), 20);
    response.on("close", () => clearTimeout(timer));
  }, async (url) => {
    await assert.rejects(
      () => fetchWithTimeout(url, { signal: controller.signal }, 1000),
      (error: unknown) => error instanceof Error && error.name === "AbortError",
    );
  });
});

test("successful response stays readable and keeps its metadata", async () => {
  await withServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/json", "x-check": "complete" });
    response.end(JSON.stringify({ text: "বাংলা 🙂" }));
  }, async (url) => {
    const response = await fetchWithTimeout(url, {}, 1000);
    assert.equal(response.bodyUsed, false);
    assert.equal(response.url, `${url}/`);
    assert.equal(response.headers.get("x-check"), "complete");
    assert.deepEqual(await response.json(), { text: "বাংলা 🙂" });
  });
});
