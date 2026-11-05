import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import CoworkerGate from "./CoworkerGate";

type AuthCallback = (event: string, session: unknown) => void;

function authFixture() {
  let listener: AuthCallback | undefined;
  const calls = { signIns: 0, oauthProviders: [] as string[] };
  const client = {
    auth: {
      getSession: async () => ({ data: { session: null }, error: null }),
      onAuthStateChange: (callback: AuthCallback) => {
        listener = callback;
        return { data: { subscription: { unsubscribe() {} } } };
      },
      signInWithPassword: async () => { calls.signIns++; return { error: null }; },
      signInWithOAuth: async ({ provider }: { provider: string }) => { calls.oauthProviders.push(provider); return { error: null }; },
      signUp: async () => ({ error: null, data: { session: null } }),
      resetPasswordForEmail: async () => ({ error: null }),
      updateUser: async () => ({ error: null }),
      signOut: async () => ({ error: null }),
    },
  };
  return { client, calls, emit: (session: unknown) => listener?.("SIGNED_IN", session) };
}

const TestableGate = CoworkerGate as unknown as React.ComponentType<{ authClientFactory?: () => unknown }>;

async function withGate(factory: (() => unknown) | undefined, run: (tree: ReactTestRenderer, auth: ReturnType<typeof authFixture> | null) => Promise<void>) {
  const previousWindow = globalThis.window;
  const sessionValues = new Map<string, string>();
  globalThis.window = {
    location: { origin: "https://rukh.test" },
    sessionStorage: {
      getItem: (key: string) => sessionValues.get(key) ?? null,
      setItem: (key: string, value: string) => { sessionValues.set(key, value); },
      removeItem: (key: string) => { sessionValues.delete(key); },
    },
    setTimeout,
    clearTimeout,
  } as unknown as Window & typeof globalThis;
  const auth = factory ? authFixture() : null;
  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => {
      tree = create(React.createElement(TestableGate, factory ? { authClientFactory: () => auth!.client } : {}));
    });
    await act(async () => { await Promise.resolve(); });
    await run(tree!, auth);
  } finally {
    if (tree) await act(async () => tree!.unmount());
    globalThis.window = previousWindow;
  }
}

test("unauthenticated Coworker entry shows a message composer before account access", async () => {
  await withGate(undefined, async tree => {
    assert.ok(tree.root.findByProps({ id: "rukh-first-message" }));
    assert.ok(tree.root.findByProps({ "aria-label": "Start a conversation" }));
    assert.ok(tree.root.findByProps({ "aria-label": "Start with a research brief" }));
  });
});

test("missing public auth configuration blocks send without clearing the draft", async () => {
  await withGate(undefined, async tree => {
    const input = tree.root.findByProps({ id: "rukh-first-message" });
    await act(async () => input.props.onChange({ target: { value: "My first Rukh message" } }));
    await act(async () => tree.root.findByProps({ "aria-label": "Start a conversation" }).props.onSubmit({ preventDefault() {} }));
    assert.equal(tree.root.findByProps({ id: "rukh-first-message" }).props.value, "My first Rukh message");
    assert.match(tree.root.findByProps({ role: "alert" }).children.join(""), /not configured/i);
  });
});

test("unsent Coworker drafts are preserved in the current tab session for OAuth returns", async () => {
  await withGate(undefined, async tree => {
    const input = tree.root.findByProps({ id: "rukh-first-message" });
    await act(async () => input.props.onChange({ target: { value: "Preserve this across Google sign-in" } }));
    assert.equal(globalThis.window.sessionStorage.getItem("rukh-coworker-entry-draft:v1"), "Preserve this across Google sign-in");
  });
});

test("configured auth opens the Figma split-screen sign-in and returning preserves the typed message", async () => {
  await withGate(() => ({}), async (tree, auth) => {
    const input = tree.root.findByProps({ id: "rukh-first-message" });
    await act(async () => input.props.onChange({ target: { value: "Keep this draft through sign-in" } }));
    await act(async () => tree.root.findByProps({ "aria-label": "Start a conversation" }).props.onSubmit({ preventDefault() {} }));
    assert.ok(tree.root.findByProps({ className: "rukh-login-page" }));
    assert.ok(tree.root.findByProps({ id: "rukh-login-title" }));
    assert.ok(tree.root.findByProps({ "aria-label": "Account access" }));
    assert.equal(tree.root.findByProps({ id: "rukh-login-email" }).props.value, "");
    await act(async () => tree.root.findByProps({ className: "rukh-login-back" }).props.onClick());
    assert.equal(tree.root.findByProps({ id: "rukh-first-message" }).props.value, "Keep this draft through sign-in");
    assert.equal(auth!.calls.signIns, 0);
  });
});

test("Google sign-in uses the configured Supabase OAuth provider", async () => {
  await withGate(() => ({}), async (tree, auth) => {
    const input = tree.root.findByProps({ id: "rukh-first-message" });
    await act(async () => input.props.onChange({ target: { value: "Open my workspace" } }));
    await act(async () => tree.root.findByProps({ "aria-label": "Start a conversation" }).props.onSubmit({ preventDefault() {} }));
    await act(async () => tree.root.findByProps({ className: "rukh-login-google" }).props.onClick());
    assert.deepEqual(auth!.calls.oauthProviders, ["google"]);
    assert.equal(tree.root.findByProps({ id: "rukh-login-email" }).props.value, "");
  });
});

test("prompt starters populate the first-message composer without sending", async () => {
  await withGate(undefined, async tree => {
    await act(async () => tree.root.findByProps({ "aria-label": "Start with a research brief" }).props.onClick());
    assert.match(tree.root.findByProps({ id: "rukh-first-message" }).props.value, /Research this topic/);
  });
});


test("signed-out Coworker uses the approved workspace navigation and New chat clears only its draft", async () => {
  await withGate(undefined, async tree => {
    assert.ok(tree.root.findByProps({ "aria-label": "Primary workspace navigation" }));
    assert.ok(tree.root.findByProps({ className: "rukh-welcome" }));
    assert.equal(tree.root.findByProps({ href: "/editor", className: "rukh-design-nav-link" }).children.length > 0, true);
    await act(async () => tree.root.findByProps({ id: "rukh-first-message" }).props.onChange({ target: { value: "Unsent draft" } }));
    await act(async () => tree.root.findByProps({ "aria-label": "New chat" }).props.onClick());
    assert.equal(tree.root.findByProps({ id: "rukh-first-message" }).props.value, "");
  });
});
