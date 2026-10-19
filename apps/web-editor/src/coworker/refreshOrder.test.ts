import test from "node:test";
import assert from "node:assert/strict";
import { RefreshOrder } from "./refreshOrder";

test("later poll wins even if an older HTTP response arrives last", async () => {
  const gate = new RefreshOrder();
  const applied: string[] = [];
  let resolveOld!: (value: string) => void;
  let resolveNew!: (value: string) => void;
  const old = new Promise<string>(resolve => { resolveOld = resolve; });
  const newer = new Promise<string>(resolve => { resolveNew = resolve; });
  const oldRevision = gate.start();
  const oldRead = old.then(value => { if (gate.isCurrent(oldRevision)) applied.push(value); });
  const newRevision = gate.start();
  const newRead = newer.then(value => { if (gate.isCurrent(newRevision)) applied.push(value); });
  resolveNew("completed");
  await newRead;
  resolveOld("running");
  await oldRead;
  assert.deepEqual(applied, ["completed"]);
});

test("switching conversations invalidates outstanding refreshes", () => {
  const gate = new RefreshOrder();
  const revision = gate.start();
  gate.invalidate();
  assert.equal(gate.isCurrent(revision), false);
  assert.equal(gate.isCurrent(gate.start()), true);
});

test("a post-dispatch refresh cannot be overwritten by a preceding poll", () => {
  const gate = new RefreshOrder();
  const polling = gate.start();
  const explicit = gate.start();
  assert.equal(gate.isCurrent(polling), false);
  assert.equal(gate.isCurrent(explicit), true);
});
