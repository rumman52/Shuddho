import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer, type ReactTestInstance } from "react-test-renderer";
import CoworkerWorkspace from "./CoworkerWorkspace";
import { type CoworkerClient } from "./client";

const timestamp = "2026-10-19T00:00:00Z";
const oldRun = {
  id: "linked-old-run", goal: "Exact older conversation result", state: "completed", final_state: "completed",
  message: "Verified result", runtime_version: 3, planner_calls: 1, planner_tokens: 10,
  planner_actual_tokens: 10, planner_cost_microusd: 0, decisions: [], steps: [], action_proposals: [], created_at: timestamp,
};

function fixture() {
  const conversation = { id: "conversation", title: "Project", message_sequence: 1, created_at: timestamp, updated_at: timestamp };
  const messages = [{ id: "message", conversation_id: conversation.id, sequence: 1, text: "Original brief",
    selected_sources: [], resource_links: [{ resource_type: "agent_run", resource_id: oldRun.id }], created_at: timestamp }];
  const messagesByKey = new Map<string, string>();
  const titlesByKey = new Map<string, string>();
  const requests = { messages: [] as Array<{ key: string; text: string }>, titles: [] as Array<{ key: string; title: string }>, runs: [] as string[] };
  const client = {
    me: async () => ({ account_id: "owner", usage: { tasks_today: 0 }, limits: { daily_tasks: 10 } }),
    list: async () => ({ tasks: [] }), documents: async () => ({ documents: [] }),
    skills: async () => ({ skills: [], upload_formats: ["txt"] }),
    conversations: async () => ({ items: [conversation] }),
    conversationHistory: async () => ({ items: messages }),
    conversationActivityHistory: async () => ({ items: [] }),
    workspaceManifest: async () => ({ revision_sha256: "a".repeat(64), documents: [], artifacts: [], memory: [],
      truncated: { documents: false, artifacts: false, memory: false } }),
    memory: async () => ({ enabled: false, facts: [] }),
    memoryProposals: async () => ({ proposals: [] }),
    agentTools: async () => ({ enabled: true, tools: [] }),
    agentRuns: async () => ({ runs: Array.from({ length: 30 }, (_, i) => ({ ...oldRun, id: `recent-${i}`, goal: `Unrelated newer run ${i}` })) }),
    agentRun: async (id: string) => { requests.runs.push(id); return oldRun; },
    agentContext: async () => ({ enabled: false }),
    connections: async () => ({ connections: [] }),
    connectorReadGrants: async () => ({ grants: [] }),
    reviewableCodeProposals: async () => ({ proposals: [], generation_enabled: false }),
    appendConversationMessage: async (_id: string, text: string, key: string) => {
      requests.messages.push({ key, text });
      if (messagesByKey.has(key) && messagesByKey.get(key) !== text) throw new Error("idempotency_conflict");
      messagesByKey.set(key, text);
      if (requests.messages.length === 1) throw new Error("response lost after commit");
      return messages[0];
    },
    createConversation: async (title: string, key: string) => {
      requests.titles.push({ key, title });
      if (titlesByKey.has(key) && titlesByKey.get(key) !== title) throw new Error("idempotency_conflict");
      titlesByKey.set(key, title);
      if (requests.titles.length === 1) throw new Error("response lost after commit");
      return conversation;
    },
  };
  return { client, requests, messagesByKey, titlesByKey };
}

function button(root: ReactTestInstance, label: string) {
  return root.findAllByType("button").find(item => item.children.some(child => child === label))!;
}

async function mounted(run: (tree: ReactTestRenderer, data: ReturnType<typeof fixture>) => Promise<void>, configure?: (data: ReturnType<typeof fixture>) => void) {
  const previous = globalThis.window;
  globalThis.window = { location: { search: "" }, setInterval, clearInterval } as unknown as Window & typeof globalThis;
  const data = fixture();
  configure?.(data);
  let tree!: ReactTestRenderer;
  try {
    await act(async () => { tree = create(<CoworkerWorkspace client={data.client as unknown as CoworkerClient} email="owner@example.test" signOut={async () => undefined} />); });
    await act(async () => { button(tree.root, "Conversations").props.onClick(); });
    await run(tree, data);
  } finally {
    if (tree) await act(async () => { tree.unmount(); });
    globalThis.window = previous;
  }
}

async function submit(tree: ReactTestRenderer, inputId: string, text: string) {
  await act(async () => { tree.root.findByProps({ id: inputId }).props.onChange({ target: { value: text } }); });
  const field = tree.root.findByProps({ id: inputId });
  let parent = field.parent;
  while (parent?.type !== "form") parent = parent!.parent;
  await act(async () => { await parent!.props.onSubmit({ preventDefault() {} }); });
}

test("conversation link opens the exact owned run beyond the thirty-run history", async () => {
  await mounted(async (tree, data) => {
    await act(async () => { button(tree.root, "View Agent runs").props.onClick(); });
    const details = tree.root.findByProps({ "aria-label": "Agent run details" });
    assert.equal(details.findByType("h2").children.join(""), "Exact older conversation result");
    assert.deepEqual(data.requests.runs, ["linked-old-run"]);
  });
});

test("unchanged lost-response message retry reuses the saved request identity", async () => {
  await mounted(async (tree, data) => {
    await submit(tree, "cw-conversation-message", "My brief");
    await submit(tree, "cw-conversation-message", "My brief");
    assert.equal(data.requests.messages[0].key, data.requests.messages[1].key);
    assert.equal(data.messagesByKey.size, 1);
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.value, "");
  });
});

test("editing a lost-response message creates a new payload-bound request", async () => {
  await mounted(async (tree, data) => {
    await submit(tree, "cw-conversation-message", "My original brief");
    await submit(tree, "cw-conversation-message", "My revised brief");
    assert.notEqual(data.requests.messages[0].key, data.requests.messages[1].key);
    assert.equal(data.messagesByKey.size, 2);
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.value, "");
  });
});

test("editing a lost-response title creates a new payload-bound request", async () => {
  await mounted(async (tree, data) => {
    await submit(tree, "cw-conversation-title", "Original title");
    await submit(tree, "cw-conversation-title", "Revised title");
    assert.notEqual(data.requests.titles[0].key, data.requests.titles[1].key);
    assert.equal(data.titlesByKey.size, 2);
    assert.equal(tree.root.findByProps({ id: "cw-conversation-title" }).props.value, "");
  });
});


test("a rejected linked run never falls back to unrelated recent work", async () => {
  await mounted(async (tree, data) => {
    await act(async () => { button(tree.root, "View Agent runs").props.onClick(); });
    assert.equal(tree.root.findAllByProps({ "aria-label": "Agent run details" }).length, 0);
    assert.ok(tree.root.findAllByProps({ role: "alert" }).some(item => item.children.includes("Linked run unavailable")));
    assert.deepEqual(data.requests.runs, ["linked-old-run"]);
  }, data => {
    data.client.agentRun = async (id: string) => {
      data.requests.runs.push(id);
      throw new Error("Linked run unavailable");
    };
  });
});

test("an unchanged lost-response title retry preserves the original identity", async () => {
  await mounted(async (tree, data) => {
    await submit(tree, "cw-conversation-title", "Original title");
    await submit(tree, "cw-conversation-title", "  Original title  ");
    assert.equal(data.requests.titles[0].key, data.requests.titles[1].key);
    assert.equal(data.titlesByKey.size, 1);
    assert.equal(tree.root.findByProps({ id: "cw-conversation-title" }).props.value, "");
  });
});
