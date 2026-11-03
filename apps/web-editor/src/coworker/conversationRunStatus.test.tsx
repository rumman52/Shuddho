import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import ConversationRunStatus from "./ConversationRunStatus";
import type { AgentRun, CoworkerClient } from "./client";
const run = (id = "run-1", override = {}) => ({ id, state: "completed", final_state: "completed", message: "The requested draft is ready.", plan: [], tool_results: [], ...override } as unknown as AgentRun);
async function mount(client: object, exercise: (tree: ReactTestRenderer) => Promise<void>) {
  let tree!: ReactTestRenderer;
  try {
    await act(async () => { tree = create(<ConversationRunStatus client={client as CoworkerClient} runId="run-1" />); });
    await exercise(tree);
  } finally { if (tree) await act(async () => tree.unmount()); }
}
const content = (tree: ReactTestRenderer) => JSON.stringify(tree.toJSON());
test("shows returned Agent message and tool summaries inline without invented assistant text", async () => {
  await mount({ agentRun: async () => run("run-1", { tool_results: [{ invocation_id: "i", tool: "document.create", status: "completed", summary: { title: "বাংলা নথি" } }] }) }, async tree => {
    assert.match(content(tree), /The requested draft is ready/);
    assert.match(content(tree), /বাংলা নথি/);
    assert.match(content(tree), /document.create/);
  });
});
test("partial completion is labelled partial even when the run state is completed", async () => {
  await mount({ agentRun: async () => run("run-1", { final_state: "partially_completed", message: "One source was unavailable." }) }, async tree => {
    assert.match(content(tree), /Partially completed/);
    assert.match(content(tree), /One source was unavailable/);
  });
});
test("failed run read shows an error and retry recovers without dispatch", async () => {
  let reads = 0;
  await mount({ agentRun: async () => { if (++reads === 1) throw new Error("Run temporarily unavailable"); return run(); } }, async tree => {
    assert.match(content(tree), /Run temporarily unavailable/);
    await act(async () => tree.root.findByProps({ "aria-label": "Retry Agent progress" }).props.onClick());
    assert.match(content(tree), /The requested draft is ready/); assert.equal(reads, 2);
  });
});
test("an old run response cannot replace the current run after navigation", async () => {
  let resolveOld!: (value: AgentRun) => void;
  const client = { agentRun: async (id: string) => id === "run-1" ? new Promise<AgentRun>(resolve => { resolveOld = resolve; }) : run(id, { message: "New result" }) } as unknown as CoworkerClient;
  await mount(client, async tree => {
    await act(async () => tree.update(<ConversationRunStatus client={client} runId="run-2" />));
    await act(async () => resolveOld(run("run-1", { message: "Stale result" })));
    assert.match(content(tree), /New result/); assert.doesNotMatch(content(tree), /Stale result/);
  });
});
test("rejects a response for an unrelated run", async () => {
  await mount({ agentRun: async () => run("unrelated", { message: "Other conversation" }) }, async tree => {
    assert.doesNotMatch(content(tree), /Other conversation/);
    assert.match(content(tree), /does not match/);
  });
});
