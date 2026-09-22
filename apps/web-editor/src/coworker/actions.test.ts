import test from "node:test";
import assert from "node:assert/strict";
import { CoworkerClient, type ExternalAction } from "./client";
import { googleAuthorizationURL } from "./googleCallback";
import { microsoftAuthorizationURL } from "./microsoftCallback";

test("Google redirect must match the provider, current site, callback path and returned state", () => {
  const state = "a".repeat(43);
  const base = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  base.searchParams.set("state", state);
  base.searchParams.set("redirect_uri", "https://shuddho.example.org/oauth/google/callback");
  assert.equal(googleAuthorizationURL(base.href, state, "https://shuddho.example.org"), base.href);
  for (const changed of ["https://attacker.test/?" + base.searchParams, base.href.replace("oauth2/v2/auth", "other"),
    base.href.replace("state=aaa", "state=bbb"), base.href.replace("shuddho.example.org", "attacker.test")]) {
    assert.throws(() => googleAuthorizationURL(changed, state, "https://shuddho.example.org"));
  }
});

test("approval sends only the persisted preview hash to the owned API with the current token", async () => {
  const original = globalThis.fetch;
  const requests: { url: string; init: RequestInit }[] = [];
  globalThis.fetch = (async (url, init) => {
    requests.push({ url: String(url), init: init! });
    return new Response(JSON.stringify({ state: "queued" }), { headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("https://api.test", async () => "current-account-token");
    const action = { id: "e01c54bf-c38a-4138-a2b0-649091891f10", preview_hash: "a".repeat(64), preview: { body: "Private text" } } as unknown as ExternalAction;
    await client.approveAction(action);
    assert.equal(requests[0].url, `https://api.test/api/v1/actions/${action.id}/approve`);
    assert.deepEqual(JSON.parse(requests[0].init.body as string), { preview_hash: action.preview_hash });
    assert.equal(new Headers(requests[0].init.headers).get("Authorization"), "Bearer current-account-token");
    assert.equal(requests[0].init.redirect, "error");
    assert.equal(requests[0].init.credentials, "omit");
  } finally { globalThis.fetch = original; }
});


test("Microsoft redirect must match login host, tenant path, current site, callback path and returned state", () => {
  const state = "b".repeat(43);
  const base = new URL("https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize");
  base.searchParams.set("state", state);
  base.searchParams.set("redirect_uri", "https://shuddho.example.org/oauth/microsoft/callback");
  assert.equal(
    microsoftAuthorizationURL(base.href, state, "https://shuddho.example.org"),
    base.href,
  );
  for (const changed of [
    base.href.replace("login.microsoftonline.com", "attacker.test"),
    base.href.replace("/oauth2/v2.0/authorize", "/oauth2/v2.0/token"),
    base.href.replace(state, "c".repeat(43)),
    base.href.replace("shuddho.example.org", "attacker.test"),
    base.href.replace("/oauth/microsoft/callback", "/oauth/google/callback"),
  ]) {
    assert.throws(() =>
      microsoftAuthorizationURL(changed, state, "https://shuddho.example.org"),
    );
  }
});

test("Microsoft connection client uses only fixed backend start and finish routes", async () => {
  const original = globalThis.fetch;
  const requests: string[] = [];
  globalThis.fetch = (async (url) => {
    requests.push(String(url));
    if (String(url).endsWith("/start")) {
      return new Response(JSON.stringify({
        authorization_url: "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize",
        state: "b".repeat(43),
      }), { headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({
      id: "11111111-1111-1111-1111-111111111111",
      provider: "microsoft",
      capability: "email",
      email: "user@example.test",
      active: true,
    }), { headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    const client = new CoworkerClient("https://api.test", async () => "token");
    await client.connectMicrosoft("email");
    await client.finishMicrosoft("code", "b".repeat(43));
    assert.deepEqual(requests, [
      "https://api.test/api/v1/connections/microsoft/start",
      "https://api.test/api/v1/connections/microsoft/finish",
    ]);
  } finally {
    globalThis.fetch = original;
  }
});
