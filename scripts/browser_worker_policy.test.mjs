import test from "node:test";
import assert from "node:assert/strict";
import { browserContextOptions, browserRequestAllowed, formFieldPolicy, normalizedBaseUrl, parseConnectAuthority, safeWorkerId } from "./browser_worker_policy.mjs";

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
  assert.equal(normalizedBaseUrl("https://browser-api.example.com/"), "https://browser-api.example.com");
  assert.throws(() => normalizedBaseUrl("http://browser-api.example.com"), /invalid_worker_api_base_url/);
  assert.throws(() => normalizedBaseUrl("https://user:secret@example.com"), /invalid_worker_api_base_url/);
});


test("browser form policy blocks sensitive and non-editable fields", () => {
  assert.equal(formFieldPolicy({ tag: "input", type: "text", autocomplete: "", disabled: false, readOnly: false }), "fillable");
  assert.equal(formFieldPolicy({ tag: "input", type: "password", autocomplete: "", disabled: false, readOnly: false }), "not_editable");
  assert.equal(formFieldPolicy({ tag: "input", type: "text", autocomplete: "one-time-code", disabled: false, readOnly: false }), "sensitive");
  assert.equal(formFieldPolicy({ tag: "select", type: "text", autocomplete: "", disabled: false, readOnly: false }), "not_editable");
});

test("browser form policy prevents mutations and navigation while filling", () => {
  assert.equal(browserRequestAllowed({
    kind: "prepare_form", method: "POST", preparingForm: false, navigationRequest: false, mainFrame: false,
  }), false);
  assert.equal(browserRequestAllowed({
    kind: "prepare_form", method: "GET", preparingForm: true, navigationRequest: true, mainFrame: true,
  }), false);
  assert.equal(browserRequestAllowed({
    kind: "prepare_form", method: "GET", preparingForm: true, navigationRequest: false, mainFrame: false,
  }), true);
  assert.equal(browserRequestAllowed({
    kind: "navigate", method: "POST", preparingForm: false, navigationRequest: false, mainFrame: false,
  }), true);
});


test("browser context continuity never relaxes isolation options", () => {
  const state = {
    cookies: [{ name: "session", value: "opaque", domain: "example.com", path: "/" }],
    origins: [],
  };
  assert.deepEqual(browserContextOptions(undefined), {
    acceptDownloads: false,
    ignoreHTTPSErrors: false,
    serviceWorkers: "block",
  });
  assert.deepEqual(browserContextOptions(state), {
    acceptDownloads: false,
    ignoreHTTPSErrors: false,
    serviceWorkers: "block",
    storageState: state,
  });
});
