import test from "node:test";
import assert from "node:assert/strict";
import { normalizedBaseUrl, parseConnectAuthority, safeWorkerId } from "./browser_worker_policy.mjs";

test("browser worker policy accepts only HTTPS CONNECT on named hosts", () => {
  assert.deepEqual(parseConnectAuthority("example.com:443"), { host: "example.com", port: 443 });
  assert.throws(() => parseConnectAuthority("example.com:80"), /blocked_connect_authority/);
  assert.throws(() => parseConnectAuthority("127.0.0.1:443"), /blocked_connect_authority/);
  assert.throws(() => parseConnectAuthority("localhost"), /invalid_connect_authority/);
});

test("browser worker identity and API base are bounded", () => {
  assert.equal(safeWorkerId("browser-worker.1"), "browser-worker.1");
  assert.throws(() => safeWorkerId("x"), /invalid_worker_id/);
  assert.equal(normalizedBaseUrl("http://127.0.0.1:8000/"), "http://127.0.0.1:8000");
  assert.throws(() => normalizedBaseUrl("https://user:secret@example.com"), /invalid_worker_api_base_url/);
});
