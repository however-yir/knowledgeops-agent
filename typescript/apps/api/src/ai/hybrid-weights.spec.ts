import { describe, expect, it } from "vitest";

import { HYBRID_WEIGHT_PRESETS, hybridWeights, normalizeHybridWeights } from "./hybrid-weights.js";

describe("hybrid weights", () => {
  it("ships presets that already sum to 1.0", () => {
    for (const preset of Object.values(HYBRID_WEIGHT_PRESETS)) {
      const sum = preset.vectorWeight + preset.keywordWeight + preset.graphWeight + preset.webWeight;
      expect(Math.abs(sum - 1)).toBeLessThan(1e-9);
    }
    expect(HYBRID_WEIGHT_PRESETS.DEFAULT).toEqual(hybridWeights(0.4, 0.25, 0.2, 0.15));
  });

  it("normalizes custom weights to sum to 1.0", () => {
    const normalized = normalizeHybridWeights(hybridWeights(2, 1, 0.5, 0.5));
    const sum = normalized.vectorWeight + normalized.keywordWeight + normalized.graphWeight + normalized.webWeight;
    expect(Math.abs(sum - 1)).toBeLessThan(1e-9);
    expect(normalized.vectorWeight).toBeCloseTo(0.5, 9);
    expect(normalized.keywordWeight).toBeCloseTo(0.25, 9);
  });

  it("falls back to BALANCED on a zero or negative weight sum", () => {
    expect(normalizeHybridWeights(hybridWeights(0, 0, 0, 0))).toEqual(HYBRID_WEIGHT_PRESETS.BALANCED);
    expect(normalizeHybridWeights(hybridWeights(-1, -1, -1, -1))).toEqual(HYBRID_WEIGHT_PRESETS.BALANCED);
  });

  it("returns already-normalized weights untouched", () => {
    const weights = hybridWeights(0.5, 0.3, 0.1, 0.1);
    expect(normalizeHybridWeights(weights)).toBe(weights);
  });
});
