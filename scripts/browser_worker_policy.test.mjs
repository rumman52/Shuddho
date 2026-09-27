import test from "node:test";
import assert from "node:assert/strict";
import { browserContextOptions, browserRequestAllowed, formFieldPolicy, normalizedBaseUrl, parseConnectAuthority, safeWorkerId, takeoverFieldPolicy } from "./browser_worker_policy.mjs";

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


test("browser takeover policy permits password and OTP fields but not unsafe controls", () => {
  assert.equal(takeoverFieldPolicy({ tag: "input", type: "password", autocomplete: "current-password", disabled: false, readOnly: false }), "fillable");
  assert.equal(takeoverFieldPolicy({ tag: "input", type: "text", autocomplete: "one-time-code", disabled: false, readOnly: false }), "fillable");
  assert.equal(takeoverFieldPolicy({ tag: "input", type: "file", autocomplete: "", disabled: false, readOnly: false }), "not_editable");
  assert.equal(takeoverFieldPolicy({ tag: "input", type: "hidden", autocomplete: "", disabled: false, readOnly: false }), "not_editable");
});


test("visual takeover frame policy is strictly read-only", () => {
  assert.equal(browserRequestAllowed({
    kind: "takeover_frame", method: "GET", preparingForm: false, navigationRequest: true, mainFrame: true,
  }), true);
  assert.equal(browserRequestAllowed({
    kind: "takeover_frame", method: "HEAD", preparingForm: false, navigationRequest: false, mainFrame: false,
  }), true);
  assert.equal(browserRequestAllowed({
    kind: "takeover_frame", method: "POST", preparingForm: false, navigationRequest: false, mainFrame: false,
  }), false);
  assert.equal(browserRequestAllowed({
    kind: "takeover_frame", method: "PUT", preparingForm: false, navigationRequest: false, mainFrame: false,
  }), false);
});


test("human takeover interaction stays read-only until the exact frame is verified", () => {
  assert.equal(browserRequestAllowed({
    kind: "takeover_interaction", method: "GET", preparingForm: false, humanInteractionArmed: false, navigationRequest: true, mainFrame: true,
  }), true);
  assert.equal(browserRequestAllowed({
    kind: "takeover_interaction", method: "POST", preparingForm: false, humanInteractionArmed: false, navigationRequest: false, mainFrame: false,
  }), false);
  assert.equal(browserRequestAllowed({
    kind: "takeover_interaction", method: "POST", preparingForm: false, humanInteractionArmed: true, navigationRequest: false, mainFrame: false,
  }), true);
  assert.equal(browserRequestAllowed({
    kind: "takeover_frame", method: "POST", preparingForm: false, navigationRequest: false, mainFrame: false,
  }), false);
});


test("retained takeover context is network-silent while idle", () => {
  for (const method of ["GET", "HEAD", "POST", "PUT"]) {
    assert.equal(browserRequestAllowed({
      kind: "idle",
      method,
      preparingForm: false,
      humanInteractionArmed: false,
      navigationRequest: method === "GET",
      mainFrame: true,
    }), false);
  }
});
