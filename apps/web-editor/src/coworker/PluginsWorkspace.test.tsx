import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import PluginsWorkspace from "./PluginsWorkspace";
import { type CoworkerClient } from "./client";

const client = {
  connections: async () => ({
    enabled: true, social_publishing_enabled: false, connections: [],
  }),
} as unknown as CoworkerClient;

function view(openForReview: boolean) {
  return <PluginsWorkspace client={client} openForReview={openForReview}>
    {() => <section aria-label="Action review"><h2>Needs your approval</h2></section>}
  </PluginsWorkspace>;
}

test("Agent proposal navigation exposes its approval preview without granting approval", async () => {
  // Test the real component's ref/effect contract: the rendered preview
  // remains in the native details disclosure and opens only on focused entry.
  const management = { open: false };
  let tree!: ReactTestRenderer;
  try {
    await act(async () => {
      tree = create(view(true), {
        createNodeMock: node =>
          node.type === "details" && node.props.className === "rukh-plugin-management"
            ? management : null,
      });
    });
    assert.equal(management.open, true);
    assert.equal(
      tree.root.findByProps({ "aria-label": "Action review" }).findByType("h2").children.join(""),
      "Needs your approval",
    );
    // Clearing the focused action after loading must not collapse the preview.
    await act(async () => { tree.update(view(false)); });
    assert.equal(management.open, true);
    // The user can still close the disclosure manually; no controlled
    // open={true} prop prevents closing and no action is approved or sent.
    management.open = false;
    await act(async () => { tree.update(view(false)); });
    assert.equal(management.open, false);
  } finally {
    if (tree) await act(async () => { tree.unmount(); });
  }
});

test("ordinary Plugins navigation leaves approvals collapsed", async () => {
  const management = { open: false };
  let tree!: ReactTestRenderer;
  try {
    await act(async () => {
      tree = create(view(false), {
        createNodeMock: node =>
          node.type === "details" && node.props.className === "rukh-plugin-management"
            ? management : null,
      });
    });
    assert.equal(management.open, false);
    // A focused Agent review navigates into a newly mounted Plugins workspace.
    // This intentionally opens on entry; a later prop update cannot override
    // a user's choice to close the native details disclosure.
    await act(async () => { tree.unmount(); });
    await act(async () => {
      tree = create(view(true), {
        createNodeMock: node =>
          node.type === "details" && node.props.className === "rukh-plugin-management"
            ? management : null,
      });
    });
    assert.equal(management.open, true);
  } finally {
    if (tree) await act(async () => { tree.unmount(); });
  }
});
