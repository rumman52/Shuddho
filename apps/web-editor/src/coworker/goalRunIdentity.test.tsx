import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer, type ReactTestInstance } from "react-test-renderer";
import GoalWorkspace from "./GoalWorkspace";
import { type CoworkerClient } from "./client";

const timestamp = "2026-10-24T00:00:00Z";
function fixture({ lostResponse = false, failedRefresh = false } = {}) {
  const one = {
    id: "goal-one", objective: "Prepare the study brief", success_criteria: [], constraints: [],
    deadline_at: null, timezone: "UTC", revision: 3, state: "active", milestones: [],
    budget: { max_runs: 20, max_planner_tokens: null }, authorized_resources: [],
    next_review_at: null, created_at: timestamp, updated_at: timestamp, run_links: [],
  };
  const two = { ...one, id: "goal-two", objective: "Review the second project", revision: 4 };
  const goals = [one, two];
  const requests: Array<{ id: string; revision: number; language: string; key: string }> = [];
  const accepted = new Map<string, { id: string; revision: number; language: string; run: { id: string; persistent_goal_revision: number } }>();
  let lose = lostResponse;
  let failRefresh = failedRefresh;
  const client = {
    goals: async () => ({ enabled: true, goals }),
    personalSuggestionPreferences: async () => ({
      available: false, enabled: false, delivery_available: false, delivery_enabled: false,
      event_delivery_available: false, event_delivery_enabled: false, event_timezone: "UTC",
      model_relevance_available: false, dismissed_count: 0,
    }),
    personalSuggestions: async () => ({ suggestions: [] }),
    runGoal: async (id: string, revision: number, language: string, key: string) => {
      requests.push({ id, revision, language, key });
      const replay = accepted.get(key);
      if (replay && (replay.id !== id || replay.revision !== revision || replay.language !== language)) {
        throw new Error("idempotency_conflict");
      }
      const run = replay?.run ?? { id: `run-${accepted.size + 1}`, persistent_goal_revision: revision };
      if (!replay) accepted.set(key, { id, revision, language, run });
      if (lose) {
        lose = false;
        throw new Error("admitted goal run response lost");
      }
      return run;
    },
    goal: async (id: string) => {
      if (failRefresh) {
        failRefresh = false;
        throw new Error("goal refresh unavailable");
      }
      return goals.find(goal => goal.id === id)!;
    },
  };
  return { client, requests, accepted };
}

async function mounted(
  action: (tree: ReactTestRenderer, data: ReturnType<typeof fixture>) => Promise<void>,
  options?: Parameters<typeof fixture>[0],
) {
  const data = fixture(options);
  let tree!: ReactTestRenderer;
  try {
    await act(async () => {
      tree = create(<GoalWorkspace client={data.client as unknown as CoworkerClient}
        openAgent={() => undefined} openAutomations={() => undefined} />);
    });
    await action(tree, data);
  } finally {
    if (tree) await act(async () => { tree.unmount(); });
  }
}

function button(root: ReactTestInstance, label: string) {
  const found = root.findAllByType("button").find(item => item.children.some(child => child === label));
  assert.ok(found, `Missing button: ${label}`);
  return found;
}
async function runNow(tree: ReactTestRenderer) {
  await act(async () => { await button(tree.root, "Run bounded work now").props.onClick(); });
}

test("two separately confirmed starts of one goal admit two distinct Agent runs", async () => {
  await mounted(async (tree, data) => {
    await runNow(tree);
    await runNow(tree);
    assert.equal(data.requests.length, 2);
    assert.notEqual(data.requests[0].key, data.requests[1].key);
    assert.equal(data.accepted.size, 2);
    assert.deepEqual(data.requests.map(item => item.revision), [3, 3]);
  });
});

test("after a lost goal-admission response retry recovers one existing run", async () => {
  await mounted(async (tree, data) => {
    await runNow(tree);
    assert.equal(data.accepted.size, 1);
    assert.ok(tree.root.findAllByProps({ role: "alert" }).some(item =>
      item.children.includes("admitted goal run response lost")));
    await runNow(tree);
    assert.equal(data.requests[0].key, data.requests[1].key);
    assert.equal(data.accepted.size, 1);
    await runNow(tree);
    assert.notEqual(data.requests[1].key, data.requests[2].key);
    assert.equal(data.accepted.size, 2);
  }, { lostResponse: true });
});

test("uncertain run of an old goal never reuses the key for another goal", async () => {
  await mounted(async (tree, data) => {
    await runNow(tree);
    await act(async () => {
      const choice = tree.root.findAllByType("button").find(item =>
        item.findAllByType("strong").some(label => label.children.includes("Review the second project")));
      assert.ok(choice);
      choice.props.onClick();
    });
    await runNow(tree);
    assert.deepEqual(data.requests.map(item => item.id), ["goal-one", "goal-two"]);
    assert.notEqual(data.requests[0].key, data.requests[1].key);
    assert.equal(data.accepted.size, 2);
  }, { lostResponse: true });
});

test("confirmed run admission rotates key even if the goal refresh fails", async () => {
  await mounted(async (tree, data) => {
    await runNow(tree);
    assert.ok(tree.root.findAllByProps({ role: "alert" }).some(item =>
      item.children.includes("goal refresh unavailable")));
    await runNow(tree);
    assert.notEqual(data.requests[0].key, data.requests[1].key);
    assert.equal(data.accepted.size, 2);
  }, { failedRefresh: true });
});
