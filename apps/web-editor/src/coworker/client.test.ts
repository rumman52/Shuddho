import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { CoworkerClient, WorkspaceError, parseProgress, sourceLink, trustedBase } from "./client";
import { publicAuthConfig } from "./authConfig";

test("notification digest client uses authenticated bounded inbox routes and exact members", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; options?: RequestInit }[] = [];
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    return new Response(JSON.stringify({ enabled: true, digests: [] }), { headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "digest-test-token");
    const digest = "a".repeat(64);
    const members = ["00000001-0000-4000-8000-000000000000", "00000002-0000-4000-8000-000000000000"];
    await client.notificationDigests();
    await client.readNotificationDigest(digest, members);
    assert.equal(seen[0].url, "/backend/api/v1/notification-digests");
    assert.equal(seen[1].url, `/backend/api/v1/notification-digests/${digest}/read`);
    assert.equal(seen[1].options?.method, "POST");
    assert.deepEqual(JSON.parse(String(seen[1].options?.body)), { notification_ids: members });
    assert.equal(new Headers(seen[1].options?.headers).get("Authorization"), "Bearer digest-test-token");
    assert.equal(new Headers(seen[1].options?.headers).get("Content-Type"), "application/json");
    assert.equal(seen[1].options?.credentials, "omit");
    assert.equal(seen[1].options?.redirect, "error");
    assert.throws(() => client.readNotificationDigest("../another-owner", members));
    assert.equal(seen.length, 2);
  } finally { globalThis.fetch = original; }
});

test("source uploads accept all six advertised formats without accepting unknown extensions", async () => {
  const original = globalThis.fetch;
  const seen: Array<{ url: string; options?: RequestInit }> = [];
  const id = "00000000-0000-4000-8000-000000000001";
  const bytes = Uint8Array.from([65, 44, 66, 10]);
  const file = (name: string, size = bytes.byteLength) => ({
    name, size, arrayBuffer: async () => bytes.buffer,
  }) as unknown as File;
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    return new Response(JSON.stringify({ id }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "owner-test-token");
    for (const extension of ["txt", "docx", "pdf", "csv", "xlsx", "pptx"]) {
      const name = "sample." + extension;
      const result = await client.upload(file(name));
      assert.equal(result.id, id);
      const creation = seen[seen.length - 2];
      const content = seen[seen.length - 1];
      assert.equal(creation.url, "/backend/api/v1/documents");
      assert.equal(creation.options?.method, "POST");
      const metadata = JSON.parse(String(creation.options?.body));
      assert.equal(metadata.filename, name);
      assert.equal(metadata.byte_size, bytes.byteLength);
      assert.equal(metadata.sha256, createHash("sha256").update(bytes).digest("hex"));
      assert.equal(content.url, `/backend/api/v1/documents/${id}/content`);
      assert.equal(content.options?.method, "PUT");
      assert.equal(content.options?.body instanceof Object, true);
      assert.equal(new Headers(content.options?.headers).get("Authorization"), "Bearer owner-test-token");
    }
    assert.equal(seen.length, 12);
    for (const name of ["sample.csv.exe", "sample.svg", "sample.xlsm"]) {
      await assert.rejects(client.upload(file(name)), error => error instanceof WorkspaceError);
    }
    await assert.rejects(client.upload(file("sample.csv", 0)), error => error instanceof WorkspaceError);
    await assert.rejects(client.upload(file("sample.csv", 8 * 1024 * 1024 + 1)), error => error instanceof WorkspaceError);
    assert.equal(seen.length, 12, "rejected sources never request upload credentials");
  } finally {
    globalThis.fetch = original;
  }
});

test("research links cannot become script, local, credential-bearing, or nonstandard-port links", () => {
  assert.equal(sourceLink("https://example.org/research?q=বাংলা"), "https://example.org/research?q=%E0%A6%AC%E0%A6%BE%E0%A6%82%E0%A6%B2%E0%A6%BE");
  for (const value of [undefined, "javascript:alert(1)", "data:text/html,bad", "file:///etc/passwd", "http://127.0.0.1/", "http://[::1]/",
    "http://2130706433/", "https://user:secret@example.org/", "https://example.org:8443/", "https://localhost/", "https://api.internal/", "https://example.org\\@localhost/", "https://example.org/%0aheader"]) {
    assert.equal(sourceLink(value), undefined);
  }
});

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

test("conversation rename uses an authenticated PATCH and the exact optimistic revision", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; options?: RequestInit }[] = [];
  const id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    return new Response(JSON.stringify({
      id, title: "Renamed", message_sequence: 3,
      created_at: "2026-11-04T00:00:00Z", updated_at: "2026-11-04T00:01:00Z",
    }), { headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "rename-owner-token");
    const updated = await client.renameConversation(id, "Renamed", "2026-11-04T00:00:00Z");
    assert.equal(updated.title, "Renamed");
    assert.equal(seen.length, 1);
    assert.equal(seen[0].url, `/backend/api/v1/conversations/${id}`);
    assert.equal(seen[0].options?.method, "PATCH");
    assert.deepEqual(JSON.parse(String(seen[0].options?.body)), {
      title: "Renamed", expected_updated_at: "2026-11-04T00:00:00Z",
    });
    assert.equal(new Headers(seen[0].options?.headers).get("Authorization"), "Bearer rename-owner-token");
    assert.equal(seen[0].options?.credentials, "omit");
    assert.equal(seen[0].options?.redirect, "error");
    assert.throws(() => client.renameConversation("../another-owner", "Foreign", "revision"));
    assert.equal(seen.length, 1);
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


test("browser workspace client keeps commands owner-authenticated and bounded to API routes", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; options?: RequestInit }[] = [];
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    if (String(url).endsWith("/commands")) return new Response(JSON.stringify({ commands: [] }), { headers: { "Content-Type": "application/json" } });
    return new Response(JSON.stringify({ id: "a".repeat(8) + "-" + "a".repeat(4) + "-" + "a".repeat(4) + "-" + "a".repeat(4) + "-" + "a".repeat(12), state: "prepared" }), { headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("https://api.test", async () => "browser-token");
    const id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
    await client.createBrowserSession("research", "https://example.com/", "browser-session-key");
    await client.browserCommands(id);
    await client.navigateBrowser(id, "https://example.com/results");
    await client.requestBrowserTakeover(id, "login");
    await client.requestBrowserTakeoverFrame(id);
    await client.interactBrowserTakeover(id, { frame_version: 1, kind: "click", x: 0.25, y: 0.5 });
    await client.prepareBrowserTakeoverInput(id, { by: "label", field: "Password", value: "not-logged", submit: true });

    assert.equal(seen[0].url, "https://api.test/api/v1/browser-sessions");
    assert.equal(new Headers(seen[0].options?.headers).get("Idempotency-Key"), "browser-session-key");
    assert.equal(seen[1].url, "https://api.test/api/v1/browser-sessions/" + id + "/commands");
    assert.equal(seen[2].url, "https://api.test/api/v1/browser-sessions/" + id + "/navigate");
    assert.equal(seen[3].url, "https://api.test/api/v1/browser-sessions/" + id + "/takeover");
    assert.equal(seen[4].url, "https://api.test/api/v1/browser-sessions/" + id + "/takeover-frame");
    assert.equal(seen[5].url, "https://api.test/api/v1/browser-sessions/" + id + "/takeover-interaction");
    assert.deepEqual(JSON.parse(String(seen[5].options?.body)), { frame_version: 1, kind: "click", x: 0.25, y: 0.5 });
    assert.equal(seen[6].url, "https://api.test/api/v1/browser-sessions/" + id + "/takeover-input");
    assert.deepEqual(JSON.parse(String(seen[6].options?.body)), { by: "label", field: "Password", value: "not-logged", submit: true });
    for (const request of seen) {
      assert.equal(new Headers(request.options?.headers).get("Authorization"), "Bearer browser-token");
      assert.equal(request.options?.credentials, "omit");
      assert.equal(request.options?.redirect, "error");
    }
  } finally { globalThis.fetch = original; }
});

test("CW-10 code review client uses owner-authenticated exact identity without execution route", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; options?: RequestInit }[] = [];
  const run = "00000001-0000-4000-8000-000000000000";
  const proposal = "00000002-0000-4000-8000-000000000000";
  const digest = "a".repeat(64);
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    return new Response(JSON.stringify({ proposals: [], execution_authorized: false }), {
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "code-review-bearer");
    await client.reviewableCodeProposals(run);
    await client.codeProposal(run, proposal);
    await client.reviewCodeProposal(run, proposal, digest, "approve", "2026-10-16T05:00:00Z");
    await client.revokeCodeProposal(run, proposal, digest);
    assert.equal(seen.length, 4);
    assert.equal(seen[0].url, `/backend/api/v1/agent-runs/${run}/code-proposals`);
    assert.equal(seen[0].options?.method ?? "GET", "GET");
    assert.equal(seen[1].url, `/backend/api/v1/agent-runs/${run}/code-proposals/${proposal}`);
    assert.equal(seen[2].url, `/backend/api/v1/agent-runs/${run}/code-proposals/${proposal}/review`);
    assert.deepEqual(JSON.parse(String(seen[2].options?.body)), {
      review_sha256: digest, decision: "approve", expires_at: "2026-10-16T05:00:00Z",
    });
    assert.equal(seen[3].url, `/backend/api/v1/agent-runs/${run}/code-proposals/${proposal}/revoke`);
    assert.deepEqual(JSON.parse(String(seen[3].options?.body)), { review_sha256: digest });
    assert.ok(seen.every(item => new Headers(item.options?.headers).get("Authorization") === "Bearer code-review-bearer"));
    assert.ok(seen.every(item => item.options?.credentials === "omit"));
    assert.ok(seen.every(item => !item.url.includes("/executions")));
    assert.throws(() => client.codeProposal(run, "../other-owner"));
    assert.equal(seen.length, 4);
  } finally { globalThis.fetch = original; }
});
test("CW-10 model source drafts are explicit owner requests, not sandbox dispatch", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; options?: RequestInit }[] = [];
  const runId = "00000001-0000-4000-8000-000000000000";
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    return new Response(JSON.stringify({ id: "saved-draft", code_executed: false }), {
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "owner-token");
    const draft = await client.generateModelCodeProposal(runId, "model-review-key-01");
    assert.equal(draft.code_executed, false);
    assert.equal(seen.length, 1);
    assert.equal(seen[0].url, `/backend/api/v1/agent-runs/${runId}/code-proposals/generate`);
    assert.equal(seen[0].options?.method, "POST");
    assert.equal(new Headers(seen[0].options?.headers).get("Authorization"), "Bearer owner-token");
    assert.equal(new Headers(seen[0].options?.headers).get("Idempotency-Key"), "model-review-key-01");
    assert.equal(seen[0].options?.credentials, "omit");
    assert.ok(!seen[0].url.includes("/dispatch"));
    assert.ok(!seen[0].url.includes("/sandbox"));
    assert.equal(seen[0].options?.body, undefined);
    await assert.rejects(client.generateModelCodeProposal(runId, "../injected"));
    assert.equal(seen.length, 1);
  } finally { globalThis.fetch = original; }
});

test("text artifact reader fetches only the authenticated owner-bound content route and verifies its digest", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; options?: RequestInit }[] = [];
  const id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  const content = "# Reviewed draft\nবাংলা text";
  const bytes = new TextEncoder().encode(content);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    if (String(url).endsWith(`/artifacts/${id}/download`)) {
      return new Response(JSON.stringify({ url: null, content_path: `/api/v1/artifacts/${id}/content` }), {
        headers: { "Content-Type": "application/json" },
      });
    }
    if (String(url).endsWith(`/artifacts/${id}/content`)) {
      return new Response(content, { headers: { "Content-Type": "text/markdown; charset=utf-8" } });
    }
    throw new Error("Unexpected artifact route");
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "owner-artifact-token");
    const result = await client.readTextArtifact({
      id, filename: "review.md", content_type: "text/markdown", byte_size: bytes.byteLength, sha256,
    });
    assert.equal(result, content);
    assert.equal(seen.length, 2);
    assert.equal(seen[0].url, `/backend/api/v1/artifacts/${id}/download`);
    assert.equal(seen[1].url, `/backend/api/v1/artifacts/${id}/content`);
    for (const request of seen) {
      assert.equal(new Headers(request.options?.headers).get("Authorization"), "Bearer owner-artifact-token");
      assert.equal(request.options?.credentials, "omit");
      assert.equal(request.options?.redirect, "error");
    }
  } finally { globalThis.fetch = original; }
});

test("text artifact reader ignores signed storage URLs and still uses the owner-authenticated content route", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; options?: RequestInit }[] = [];
  const id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const content = "A plain text result";
  const bytes = new TextEncoder().encode(content);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    if (String(url).endsWith(`/artifacts/${id}/download`)) {
      return new Response(JSON.stringify({ url: "https://objects.example/signed-download", content_path: null }), {
        headers: { "Content-Type": "application/json" },
      });
    }
    if (String(url).endsWith(`/artifacts/${id}/content`)) {
      return new Response(content, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
    }
    throw new Error("Unexpected artifact route");
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "owner-artifact-token");
    assert.equal(await client.readTextArtifact({
      id, filename: "notes.txt", content_type: "text/plain", byte_size: bytes.byteLength, sha256,
    }), content);
    assert.deepEqual(seen.map(request => request.url), [
      `/backend/api/v1/artifacts/${id}/download`,
      `/backend/api/v1/artifacts/${id}/content`,
    ]);
    assert.ok(seen.every(request => new Headers(request.options?.headers).get("Authorization") === "Bearer owner-artifact-token"));
  } finally { globalThis.fetch = original; }
});

test("text artifact reader rejects content whose digest does not match saved metadata", async () => {
  const original = globalThis.fetch;
  const id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
  const content = "tampered text";
  const bytes = new TextEncoder().encode(content);
  globalThis.fetch = (async url => String(url).endsWith("/download")
    ? new Response(JSON.stringify({ url: null, content_path: `/api/v1/artifacts/${id}/content` }), { headers: { "Content-Type": "application/json" } })
    : new Response(content, { headers: { "Content-Type": "text/plain" } })) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "owner-artifact-token");
    await assert.rejects(client.readTextArtifact({
      id, filename: "notes.txt", content_type: "text/plain", byte_size: bytes.byteLength, sha256: "d".repeat(64),
    }), error => error instanceof WorkspaceError);
  } finally { globalThis.fetch = original; }
});

test("text artifact reader rejects binary files before making a request", async () => {
  const original = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = (async () => { requests += 1; throw new Error("must not fetch binary content"); }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "owner-artifact-token");
    await assert.rejects(client.readTextArtifact({
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", filename: "report.pdf",
      content_type: "application/pdf", byte_size: 100, sha256: "b".repeat(64),
    }), error => error instanceof WorkspaceError);
    assert.equal(requests, 0);
  } finally { globalThis.fetch = original; }
});


test("conversation reply stream uses authenticated fetch and publishes partial replies", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; options?: RequestInit }[] = [];
  const encoder = new TextEncoder();
  const snapshot = { state: "generating", text: "", context_truncated: false, started_at: "2026-11-04T10:00:00Z" };
  const completed = { state: "completed", text: "বাংলা উত্তর", context_truncated: false, completed_at: "2026-11-04T10:00:02Z" };
  const frames = [
    `event: snapshot\r\ndata: ${JSON.stringify(snapshot)}\r\n\r\n`,
    `event: delta\r\ndata: ${JSON.stringify({ delta: "বাংলা " })}\r\n\r\n`,
    `event: delta\r\ndata: ${JSON.stringify({ delta: "উত্তর" })}\r\n\r\n`,
    `event: final\r\ndata: ${JSON.stringify(completed)}\r\n\r\n`,
  ];
  const bytes = encoder.encode(frames.join(""));
  const chunks = [bytes.slice(0, 9), bytes.slice(9, 41), bytes.slice(41, 79), bytes.slice(79)];
  const body = new ReadableStream<Uint8Array>({
    start(controller) { for (const chunk of chunks) controller.enqueue(chunk); controller.close(); },
  });
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    return new Response(body, { headers: { "Content-Type": "text/event-stream; charset=utf-8" } });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "stream-test-token");
    const updates: { state: string; text: string }[] = [];
    const projectId = "00000003-0000-4000-8000-000000000000";
    const reply = await client.replyToConversationMessageStream(
      "00000001-0000-4000-8000-000000000000",
      "00000002-0000-4000-8000-000000000000",
      3,
      value => updates.push({ state: value.state, text: value.text }),
      undefined,
      projectId,
    );
    assert.equal(reply.state, "completed");
    assert.equal(reply.text, "বাংলা উত্তর");
    assert.deepEqual(updates, [
      { state: "generating", text: "" },
      { state: "generating", text: "বাংলা " },
      { state: "generating", text: "বাংলা উত্তর" },
      { state: "completed", text: "বাংলা উত্তর" },
    ]);
    assert.equal(seen[0].url, "/backend/api/v1/conversations/00000001-0000-4000-8000-000000000000/messages/00000002-0000-4000-8000-000000000000/reply/stream");
    assert.equal(seen[0].options?.method, "POST");
    const headers = new Headers(seen[0].options?.headers);
    assert.equal(headers.get("Authorization"), "Bearer stream-test-token");
    assert.equal(headers.get("Accept"), "text/event-stream");
    assert.equal(headers.get("Content-Type"), "application/json");
    assert.equal(seen[0].options?.credentials, "omit");
    assert.equal(seen[0].options?.redirect, "error");
    assert.equal(seen[0].options?.cache, "no-store");
    assert.deepEqual(JSON.parse(String(seen[0].options?.body)), {
      expected_sequence: 3, project_id: projectId,
    });
  } finally { globalThis.fetch = original; }
});

test("conversation reply stream rejects malformed or incomplete events", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => new Response(
    ["event: delta", 'data: {"delta":"orphan"}', "", ""].join("\n"),
    { headers: { "Content-Type": "text/event-stream" } },
  )) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "stream-test-token");
    await assert.rejects(client.replyToConversationMessageStream(
      "00000001-0000-4000-8000-000000000000",
      "00000002-0000-4000-8000-000000000000",
      1,
      () => undefined,
    ));
  } finally { globalThis.fetch = original; }
});


test("conversation reply stream enforces the 16 KB UTF-8 response limit", async () => {
  const original = globalThis.fetch;
  const snapshot = { state: "generating", text: "", context_truncated: false };
  const body = [
    "event: snapshot",
    `data: ${JSON.stringify(snapshot)}`,
    "",
    "event: delta",
    `data: ${JSON.stringify({ delta: "x".repeat(16001) })}`,
    "",
    "",
  ].join("\n");
  globalThis.fetch = (async () => new Response(body, {
    headers: { "Content-Type": "text/event-stream" },
  })) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "stream-test-token");
    await assert.rejects(client.replyToConversationMessageStream(
      "00000001-0000-4000-8000-000000000000",
      "00000002-0000-4000-8000-000000000000",
      1,
      () => undefined,
    ));
  } finally { globalThis.fetch = original; }
});



test("source text documents reject a response with a mismatched SHA-256 digest", async () => {
  const original = globalThis.fetch;
  const bytes = new TextEncoder().encode("tampered body");
  globalThis.fetch = (async () => new Response(bytes)) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "owner-document-token");
    const document = {
      id: "00000000-0000-4000-8000-000000000000",
      filename: "notes.txt",
      kind: "txt",
      state: "uploaded",
      byte_size: bytes.byteLength,
      sha256: "0".repeat(64),
    };
    const read = (client as unknown as { readTextDocument: (value: typeof document) => Promise<string> }).readTextDocument;
    await assert.rejects(read.call(client, document), /failed its integrity check/i);
  } finally {
    globalThis.fetch = original;
  }
});


test("source text documents are read through the owner-authenticated content route and SHA-256 is verified", async () => {
  const original = globalThis.fetch;
  const seen: { url: string; options?: RequestInit }[] = [];
  const body = "A saved writing draft. বাংলা লেখা।";
  const bytes = new TextEncoder().encode(body);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  const id = "00000000-0000-4000-8000-000000000000";
  globalThis.fetch = (async (url, options) => {
    seen.push({ url: String(url), options });
    return new Response(bytes, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "owner-document-token");
    const document = { id, filename: "notes.txt", kind: "txt", state: "uploaded", byte_size: bytes.byteLength, sha256 };
    const read = (client as unknown as { readTextDocument: (value: typeof document) => Promise<string> }).readTextDocument;
    assert.equal(await read.call(client, document), body);
    assert.equal(seen.length, 1);
    assert.equal(seen[0].url, `/backend/api/v1/documents/${id}/content`);
    assert.equal(new Headers(seen[0].options?.headers).get("Authorization"), "Bearer owner-document-token");
    assert.equal(seen[0].options?.credentials, "omit");
    assert.equal(seen[0].options?.redirect, "error");
  } finally {
    globalThis.fetch = original;
  }
});

test("task dispatch binds exact memory versions, including an explicit empty selection", async () => {
  const original = globalThis.fetch;
  const bodies: Record<string, unknown>[] = [];
  const conversation = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const message = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  globalThis.fetch = (async (_url, options) => {
    bodies.push(JSON.parse(String(options?.body)) as Record<string, unknown>);
    return new Response(JSON.stringify({ run_id: "run", state: "queued", replayed: false }), {
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("/backend", async () => "day5-test-token");
    const pin = { fact_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", expected_version: 3 };
    await client.dispatchConversationMessage(conversation, message, 1, null, [pin]);
    await client.dispatchConversationMessage(conversation, message, 1, null, []);
    await client.dispatchConversationMessage(conversation, message, 1);
    assert.deepEqual(bodies[0].memory_pins, [pin]);
    assert.deepEqual(bodies[1].memory_pins, []);
    assert.equal(Object.hasOwn(bodies[2], "memory_pins"), false);
  } finally {
    globalThis.fetch = original;
  }
});
