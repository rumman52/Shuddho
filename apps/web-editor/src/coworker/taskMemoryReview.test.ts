import assert from "node:assert/strict";
import test from "node:test";
import { memorySelectionLimit, memorySelectionCurrent, reviewedMemoryDigest } from "./taskMemoryReview";

const pin = { fact_id: "fact-a", expected_version: 2 };
const fact = { id: "fact-a", version: 2, active: true };
const preview = { canonical_digest: "reviewed-digest", memory_pins: [] };

test("legacy proposal digest cannot confirm an explicit empty memory selection", () => {
  assert.equal(reviewedMemoryDigest(preview, false, true, []), null);
  assert.equal(reviewedMemoryDigest(preview, true, false, []), null);
  assert.equal(reviewedMemoryDigest(preview, true, true, []), "reviewed-digest");
  assert.equal(reviewedMemoryDigest(preview, false, false, []), "reviewed-digest");
});

test("reviewed digest compares exact memory ID, version and order", () => {
  const selected = { ...preview, memory_pins: [pin] };
  assert.equal(reviewedMemoryDigest(selected, true, true, [pin]), "reviewed-digest");
  assert.equal(reviewedMemoryDigest(selected, true, true, [{ ...pin, expected_version: 3 }]), null);
  assert.equal(reviewedMemoryDigest(selected, true, true, [{ ...pin, fact_id: "fact-b" }]), null);
  assert.equal(reviewedMemoryDigest(selected, true, true, []), null);
  const second = { fact_id: "fact-b", expected_version: 1 };
  assert.equal(reviewedMemoryDigest({ ...preview, memory_pins: [pin, second] }, true, true, [second, pin]), null);
});

test("selection cap respects a lower server limit and the schema ceiling", () => {
  assert.equal(memorySelectionLimit(2), 2);
  assert.equal(memorySelectionLimit(100), 20);
  assert.equal(memorySelectionLimit(undefined), 20);
  assert.equal(memorySelectionLimit(0), 0);
  assert.equal(memorySelectionLimit(-1), 0);
  assert.equal(memorySelectionLimit(2.5), 0);
});

test("current memory selection rejects missing, stale, expired or excess pins", () => {
  assert.equal(memorySelectionCurrent([], [], 0), true);
  assert.equal(memorySelectionCurrent([pin], [fact], 1), true);
  assert.equal(memorySelectionCurrent([pin], [fact], 0), false);
  assert.equal(memorySelectionCurrent([pin], [], 1), false);
  assert.equal(memorySelectionCurrent([pin], [{ ...fact, version: 3 }], 1), false);
  assert.equal(memorySelectionCurrent([pin], [{ ...fact, active: false }], 1), false);
});
