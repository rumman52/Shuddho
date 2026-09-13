import test from "node:test";
import assert from "node:assert/strict";
import { CoworkerClient, WorkspaceError, parseProgress, trustedBase } from "./client";
import { publicAuthConfig } from "./authConfig";

test("browser identity rejects secret keys and credential-bearing origins", () => {
  assert.equal(publicAuthConfig("https://identity.test", "sb_publishable_test"), true);
  assert.equal(publicAuthConfig("https://identity.test", "sb_secret_test"), false);
  assert.equal(publicAuthConfig("https://user:secret@identity.test", "sb_publishable_test"), false);
  const token = role => "header." + btoa(JSON.stringify({ role })) + ".signature";
  assert.equal(publicAuthConfig("https://identity.test", token("anon")), true);
  assert.equal(publicAuthConfig("https://identity.test", token("service_role")), false);
});

test("workspace base accepts configured endpoints and rejects token-exposing URLs", () => {
  assert.equal(trustedBase("/backend"), "/backend");
  assert.equal(trustedBase("https://api.example.test/"), "https://api.example.test");
  assert.equal(trustedBase("http://127.0.0.1:8000"), "http://127.0.0.1:8000");
  for (const value of ["//evil.test", "https://user:password@api.test", "http://remote.test", "https://api.test?token=secret", "javascript:alert(1)"]) {
    assert.throws(() => trustedBase(value));
  }
});

test("owned API uses a fresh token, forbids redirects, and preserves the submission key", async () => {
  const original = globalThis.fetch;
  const seen: RequestInit[] = [];
  globalThis.fetch = (async (_url, options) => {
    seen.push(options!);
    return new Response(JSON.stringify({ id: "task" }), { headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  let token = "test-token-alice";
  try {
    const client = new CoworkerClient("https://api.test", async () => token);
    const body = { instruction: "Create a report", notes: "Notes", document_ids: [], output_language: "bn" };
    await client.create(body, "same-submission-key");
    token = "test-refreshed-token";
    await client.create(body, "same-submission-key");
    assert.equal(new Headers(seen[0].headers).get("Authorization"), "Bearer test-token-alice");
    assert.equal(new Headers(seen[1].headers).get("Authorization"), "Bearer test-refreshed-token");
    assert.equal(new Headers(seen[1].headers).get("Idempotency-Key"), "same-submission-key");
    assert.equal(seen[0].redirect, "error");
    assert.equal(seen[0].credentials, "omit");
  } finally { globalThis.fetch = original; }
});

test("signed-out requests never reach the network", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => { throw new Error("must not reach fetch"); }) as typeof fetch;
  try {
    await assert.rejects(new CoworkerClient("/backend", async () => null).me(), error => error instanceof WorkspaceError && error.status === 401);
  } finally { globalThis.fetch = original; }
});

test("resumable progress parses Unicode safely and rejects invalid events", () => {
  assert.equal(parseProgress(": keepalive"), null);
  assert.deepEqual(parseProgress('id: 3\nevent: progress\ndata: {"sequence":3,"state":"running","phase":"draft","message":"বাংলা"}'),
    { sequence: 3, state: "running", phase: "draft", message: "বাংলা" });
  assert.throws(() => parseProgress('data: {"sequence":1,"state":"sent","phase":"done","message":"Sent"}'));
});

test("watch falls back to snapshots after an SSE failure and stops at completion", async () => {
  const client = new CoworkerClient("/backend", async () => "test-token");
  const controller = new AbortController();
  const original = globalThis.fetch;
  let polls = 0;
  const states: string[] = [];
  globalThis.fetch = (async url => {
    if (String(url).includes("events?")) return new Response("unsupported", { status: 502 });
    polls++;
    return new Response(JSON.stringify({ id: "a".repeat(36), state: polls === 1 ? "running" : "completed", event_sequence: polls }), { headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    await client.watch("a".repeat(36), controller.signal, task => states.push(task.state), () => undefined, () => undefined);
    assert.deepEqual(states, ["running", "completed"]);
  } finally { globalThis.fetch = original; controller.abort(); }
});

test("aborting an event stream stops updates and closes the pending read", async () => {
  const original = globalThis.fetch;
  const controller = new AbortController();
  let cancelled = false;
  let snapshotCount = 0;
  globalThis.fetch = (async (url, options) => {
    if (!String(url).includes("events?")) return new Response(JSON.stringify({ id: "b".repeat(36), state: "running", event_sequence: 1 }));
    return new Response(new ReadableStream({ start(stream) {
      options?.signal?.addEventListener("abort", () => { cancelled = true; stream.error(new DOMException("Aborted", "AbortError")); });
      setTimeout(() => controller.abort(), 5);
    } }), { headers: { "Content-Type": "text/event-stream" } });
  }) as typeof fetch;
  try {
    await new CoworkerClient("/backend", async () => "test-token").watch("b".repeat(36), controller.signal,
      () => { snapshotCount++; }, () => assert.fail("must not update after abort"), () => undefined);
    assert.equal(cancelled, true);
    assert.equal(snapshotCount, 1);
  } finally { globalThis.fetch = original; }
});
