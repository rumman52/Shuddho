import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import AgentWorkspace from "./AgentWorkspace";
import { type CoworkerClient } from "./client";

const createdAt = "2026-10-24T00:00:00Z";

function fixture(loseFirstResponse = false) {
  const requests: Array<{ key: string; goal: string }> = [];
  const accepted = new Map<string, { id: string; goal: string }>();
  let lose = loseFirstResponse;
  const client = {
    agentTools: async () => ({ enabled: true, tools: [] }),
    agentRuns: async () => ({ runs: [] }),
    connections: async () => ({ connections: [] }),
    memory: async () => ({ facts: [], enabled: false }),
    memoryProposals: async () => ({ proposals: [] }),
    connectorReadGrants: async () => ({ grants: [] }),
    agentContext: async () => ({ enabled: false, items: [], invalidated: [] }),
    reviewableCodeProposals: async () => ({ proposals: [], generation_enabled: false }),
    createAgentRun: async (input: { goal: string }, key: string) => {
      requests.push({ key, goal: input.goal });
      const existing = accepted.get(key);
      if (existing && existing.goal !== input.goal) throw new Error("idempotency_conflict");
      const saved = existing ?? { id: `run-${accepted.size + 1}`, goal: input.goal };
      accepted.set(key, saved);
      if (lose) {
        lose = false;
        throw new Error("accepted run response was lost");
      }
      return {
        ...saved, state: "completed", final_state: "completed", message: "Done",
        runtime_version: 3, planner_calls: 0, planner_tokens: 0, planner_actual_tokens: 0,
        planner_cost_microusd: 0, decisions: [], steps: [], action_proposals: [], created_at: createdAt,
      };
    },
  };
  return { client, requests, accepted };
}

async function mounted(
  scenario: (tree: ReactTestRenderer, data: ReturnType<typeof fixture>) => Promise<void>,
  loseFirstResponse = false,
) {
  const data = fixture(loseFirstResponse);
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

async function send(tree: ReactTestRenderer, goal: string) {
  await act(async () => {
    tree.root.findAllByType("textarea").find(item => item.props.rows === 7)!.props.onChange({
      target: { value: goal },
    });
  });
  await act(async () => {
    await tree.root.findAllByType("form")[0].props.onSubmit({ preventDefault() {} });
  });
}

test("successful repeated Agent goal requests create distinct runs and request keys", async () => {
  await mounted(async (tree, data) => {
    await send(tree, "Research the same topic again");
    await send(tree, "Research the same topic again");
    assert.equal(data.requests.length, 2);
    assert.notEqual(data.requests[0].key, data.requests[1].key);
    assert.equal(data.accepted.size, 2);
    assert.equal(tree.root.findByProps({ "aria-label": "Agent run details" })
      .findByType("h2").children.join(""), "Research the same topic again");
  });
});

test("lost Agent creation response retries the same exact request key and run", async () => {
  await mounted(async (tree, data) => {
    await send(tree, "Draft the weekly update");
    assert.equal(data.accepted.size, 1);
    assert.ok(tree.root.findAllByProps({ role: "alert" })
      .some(item => item.children.includes("accepted run response was lost")));
    await send(tree, "Draft the weekly update");
    assert.equal(data.requests[0].key, data.requests[1].key);
    assert.equal(data.accepted.size, 1);
    await send(tree, "Draft the weekly update");
    assert.notEqual(data.requests[1].key, data.requests[2].key);
    assert.equal(data.accepted.size, 2);
  }, true);
});

test("changing a failed Agent submission rotates the key for the new payload", async () => {
  await mounted(async (tree, data) => {
    await send(tree, "Original task description");
    await send(tree, "Revised task description");
    assert.notEqual(data.requests[0].key, data.requests[1].key);
    assert.equal(data.accepted.size, 2);
  }, true);
});
