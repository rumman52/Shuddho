import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer, type ReactTestInstance } from "react-test-renderer";
import AgentWorkspace from "./AgentWorkspace";
import { type CoworkerClient } from "./client";

const email = "synthetic@example.test";
const connections = [
  { id: "google-read", email, provider: "google", capability: "email_read", active: true },
  { id: "microsoft-read", email, provider: "microsoft", capability: "calendar_read", active: true },
];

function fixture({ loseFirst = false, failFirstSync = false, delayedCreate = false } = {}) {
  const requests: Array<{ connection: string; expiresAt: string; key: string }> = [];
  const accepted = new Map<string, { connection: string; expiresAt: string; grant: object }>();
  const syncs: string[] = [];
  let lose = loseFirst;
  let failSync = failFirstSync;
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const client = {
    agentTools: async () => ({ enabled: true, tools: [] }),
    agentRuns: async () => ({ runs: [] }),
    connections: async () => ({ connections }),
    memory: async () => ({ facts: [], enabled: false }),
    memoryProposals: async () => ({ proposals: [] }),
    connectorReadGrants: async () => ({ enabled: true, grants: [] }),
    createConnectorReadGrant: async (connection: string, expiresAt: string, key: string) => {
      requests.push({ connection, expiresAt, key });
      if (delayedCreate) await gate;
      const previous = accepted.get(key);
      if (previous && (previous.connection !== connection || previous.expiresAt !== expiresAt))
        throw new Error("idempotency_conflict");
      const grant = previous?.grant ?? {
        id: "grant-" + (accepted.size + 1), connection_id: connection,
        provider: connection === "google-read" ? "google" : "microsoft",
        capability: connection === "google-read" ? "email_read" : "calendar_read",
        purpose: "agent_context", destination: "planner_context", operation: "read",
        version: "v1", state: "active", expires_at: expiresAt,
        created_at: "2026-10-24T00:00:00Z", revoked_at: null,
      };
      if (!previous) accepted.set(key, { connection, expiresAt, grant });
      if (lose) { lose = false; throw new Error("accepted grant response lost"); }
      return grant;
    },
    syncConnectorReadGrant: async (grantId: string) => {
      syncs.push(grantId);
      if (failSync) { failSync = false; throw new Error("initial sync temporarily unavailable"); }
      return { grant_id: grantId, inserted: 0, updated: 0, deleted: 0, ignored: 0, cursor_recovered: false };
    },
  };
  return { client, requests, accepted, syncs, release };
}

async function mounted(
  scenario: (tree: ReactTestRenderer, data: ReturnType<typeof fixture>) => Promise<void>,
  options?: Parameters<typeof fixture>[0],
) {
  const data = fixture(options);
  let tree!: ReactTestRenderer;
  try {
    await act(async () => {
      tree = create(<AgentWorkspace client={data.client as unknown as CoworkerClient}
        documents={[]} reviewAction={() => undefined} openActions={() => undefined} />);
    });
    await scenario(tree, data);
  } finally {
    if (tree) await act(async () => { tree.unmount(); });
  }
}

function button(root: ReactTestInstance, label: string, index = 0) {
  const buttons = root.findAllByType("button").filter(item => item.children.some(child => child === label));
  assert.ok(buttons[index], `Missing button ${label} at index ${index}`);
  return buttons[index];
}

async function authorize(tree: ReactTestRenderer, index = 0) {
  await act(async () => {
    button(tree.root, "Allow Agent context for 7 days", index).props.onClick();
    await Promise.resolve();
  });
}

test("lost connector grant response replays its original key AND expiry", async () => {
  await mounted(async (tree, data) => {
    await authorize(tree);
    assert.equal(data.accepted.size, 1);
    assert.ok(tree.root.findAllByProps({ role: "alert" }).some(item =>
      item.children.includes("accepted grant response lost")));
    await authorize(tree);
    assert.equal(data.requests.length, 2);
    assert.equal(data.requests[0].key, data.requests[1].key);
    assert.equal(data.requests[0].expiresAt, data.requests[1].expiresAt);
    assert.equal(data.accepted.size, 1);
    assert.deepEqual(data.syncs, ["grant-1"]);
    assert.equal(tree.root.findAllByType("input").filter(item => item.props.type === "checkbox" && item.props.checked).length, 1);
  }, { loseFirst: true });
});

test("confirmed grant remains visible after sync error; manual Sync does not reauthorize", async () => {
  await mounted(async (tree, data) => {
    await authorize(tree);
    assert.equal(data.accepted.size, 1);
    assert.ok(tree.root.findAllByProps({ role: "alert" }).some(item =>
      item.children.includes("initial sync temporarily unavailable")));
    assert.equal(data.requests.length, 1);
    assert.equal(tree.root.findAllByType("input").filter(item => item.props.type === "checkbox" && item.props.checked).length, 1);
    await act(async () => { button(tree.root, "Sync").props.onClick(); await Promise.resolve(); });
    assert.deepEqual(data.syncs, ["grant-1", "grant-1"]);
    assert.equal(data.requests.length, 1);
  }, { failFirstSync: true });
});

test("two same-tick Allow clicks cannot create concurrent grant admissions", async () => {
  await mounted(async (tree, data) => {
    await act(async () => {
      const allow = button(tree.root, "Allow Agent context for 7 days");
      allow.props.onClick();
      allow.props.onClick();
      data.release();
      await Promise.resolve();
    });
    assert.equal(data.requests.length, 1);
    assert.equal(data.accepted.size, 1);
    assert.deepEqual(data.syncs, ["grant-1"]);
  }, { delayedCreate: true });
});

test("pending uncertain grant key stays bound to its account after authorizing another account", async () => {
  await mounted(async (tree, data) => {
    await authorize(tree); // Google request accepted but response lost.
    await authorize(tree, 1); // Microsoft has a different identity.
    await authorize(tree); // Recover original Google grant.
    assert.deepEqual(data.requests.map(item => item.connection), ["google-read", "microsoft-read", "google-read"]);
    assert.equal(data.requests[0].key, data.requests[2].key);
    assert.equal(data.requests[0].expiresAt, data.requests[2].expiresAt);
    assert.notEqual(data.requests[0].key, data.requests[1].key);
    assert.equal(data.accepted.size, 2);
  }, { loseFirst: true });
});
