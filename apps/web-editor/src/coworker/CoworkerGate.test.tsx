import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import CoworkerGate from "./CoworkerGate";

type AuthCallback = (event: string, session: unknown) => void;

function authFixture() {
  let listener: AuthCallback | undefined;
  const calls = { signIns: 0 };
  const client = {
    auth: {
      getSession: async () => ({ data: { session: null }, error: null }),
      onAuthStateChange: (callback: AuthCallback) => {
        listener = callback;
        return { data: { subscription: { unsubscribe() {} } } };
      },
      signInWithPassword: async () => { calls.signIns++; return { error: null }; },
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
  globalThis.window = {
    location: { origin: "https://rukh.test" },
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

test("configured auth opens a sign-in dialog and closing it preserves the typed message", async () => {
  await withGate(() => ({}), async (tree, auth) => {
    const input = tree.root.findByProps({ id: "rukh-first-message" });
    await act(async () => input.props.onChange({ target: { value: "Keep this draft through sign-in" } }));
    await act(async () => tree.root.findByProps({ "aria-label": "Start a conversation" }).props.onSubmit({ preventDefault() {} }));
    const dialog = tree.root.findByProps({ role: "dialog" });
    assert.equal(dialog.props["aria-modal"], true);
    assert.equal(tree.root.findByProps({ id: "rukh-first-message" }).props.value, "Keep this draft through sign-in");
    await act(async () => tree.root.findByProps({ "aria-label": "Close sign-in" }).props.onClick());
    assert.equal(tree.root.findByProps({ id: "rukh-first-message" }).props.value, "Keep this draft through sign-in");
    assert.equal(auth!.calls.signIns, 0);
  });
});

test("prompt starters populate the first-message composer without sending", async () => {
  await withGate(undefined, async tree => {
    await act(async () => tree.root.findByProps({ "aria-label": "Start with a research brief" }).props.onClick());
    assert.match(tree.root.findByProps({ id: "rukh-first-message" }).props.value, /Research this topic/);
  });
});
