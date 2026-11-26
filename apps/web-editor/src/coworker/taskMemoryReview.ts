import type { MemoryFact, MemoryPin, TaskBriefPreview } from "./client";

// Keep compatibility with older API revisions, but never exceed the schema cap.
export function memorySelectionLimit(configured?: number): number {
  if (configured === undefined) return 20;
  return Number.isSafeInteger(configured) && configured >= 0 ? Math.min(20, configured) : 0;
}

export function memorySelectionCurrent(
  pins: readonly MemoryPin[], facts: readonly Pick<MemoryFact, "id" | "version" | "active">[], limit: number,
): boolean {
  return pins.length <= limit && pins.every(pin => facts.some(fact =>
    fact.id === pin.fact_id && fact.version === pin.expected_version && fact.active));
}

export function reviewedMemoryDigest(
  preview: Pick<TaskBriefPreview, "canonical_digest" | "memory_pins"> | null,
  previewUsesMemorySelection: boolean, memoryEnabled: boolean, selectedPins: readonly MemoryPin[],
): string | null {
  // Omitted legacy selection and explicit [] are different server identities.
  if (!preview || previewUsesMemorySelection !== memoryEnabled) return null;
  const reviewedPins = preview.memory_pins ?? [];
  const taskPins = memoryEnabled ? selectedPins : [];
  if (reviewedPins.length !== taskPins.length || !reviewedPins.every((pin, index) =>
    pin.fact_id === taskPins[index].fact_id && pin.expected_version === taskPins[index].expected_version)) return null;
  return preview.canonical_digest;
}
